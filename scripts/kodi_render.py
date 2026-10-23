"""Helpers for the headless Kodi render workflow (.github/workflows/render.yml).

Subcommands:
  deps       install the skin's add-on dependencies from the official Kodi repository, stubbing the rest
  profile    write a minimal Kodi profile (guisettings, skin settings that skip Bingie's first-run windows)
  set-skin   select a skin in an existing guisettings.xml while Kodi is not running
  rpc        talk to a running Kodi over JSON-RPC (TCP 9090) or the EventServer (UDP 9777)
  check-log  fail on skin XML errors in kodi.log that are not in the recorded baseline

Only the standard library is used so the module runs on any runner Python and in the unit tests.
"""
import argparse
import codecs
import gzip
import io
import json
import os
import re
import socket
import struct
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIRROR = 'https://mirrors.kodi.tv/addons'
# Kodi 21 reads add-ons from these repository branches (newest first).
BRANCHES = ('omega', 'nexus', 'matrix')
# ABI/core add-ons ship with Kodi itself.
CORE_PREFIXES = ('xbmc.', 'kodi.')
HOME_WINDOW = 10000


# ---------------------------------------------------------------- dependencies

def version_key(version):
    """Comparable key for Kodi add-on versions such as 2.0.3, 1.1.1+matrix.2 or 1.0.0~beta1."""
    main, _, suffix = version.partition('+')
    main, tilde, pre = main.partition('~')
    numbers = tuple(int(part) if part.isdigit() else 0 for part in re.split(r'[.\-]', main))
    numbers = numbers + (0,) * (4 - len(numbers)) if len(numbers) < 4 else numbers
    return numbers, 0 if tilde else 1, suffix


def requirements(addon_xml):
    """[(id, min_version, optional)] imported by an addon.xml element or file."""
    root = addon_xml if isinstance(addon_xml, ET.Element) else ET.parse(str(addon_xml)).getroot()
    found = []
    for node in root.iter('import'):
        found.append((node.get('addon'), node.get('version') or '0.0.0', node.get('optional') == 'true'))
    return found


def parse_repository(xml_bytes, branch):
    """{id: [(version, branch, element)]} from an addons.xml document."""
    index = {}
    for addon in ET.fromstring(xml_bytes).findall('addon'):
        index.setdefault(addon.get('id'), []).append((addon.get('version'), branch, addon))
    return index


def load_repository(branches=BRANCHES, mirror=MIRROR, opener=urllib.request.urlopen):
    index = {}
    for branch in branches:
        with opener('%s/%s/addons.xml.gz' % (mirror, branch), timeout=60) as response:
            data = response.read()
        data = gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data
        for addon_id, entries in parse_repository(data, branch).items():
            index.setdefault(addon_id, []).extend(entries)
    return index


def stub_addon(dest, addon_id, version):
    """Write a do-nothing add-on so Kodi can resolve the skin's dependency; returns its folder."""
    folder = Path(dest) / addon_id
    folder.mkdir(parents=True, exist_ok=True)
    root = ET.Element('addon', id=addon_id, version=version, name=addon_id + ' (render stub)',
                      **{'provider-name': 'skin.bingie render CI'})
    parts = addon_id.split('.')
    if parts[0] == 'resource':
        extension = ET.SubElement(root, 'extension', point='kodi.resource.%s' % parts[1], compile='false')
        if len(parts) > 2:
            extension.set('type', parts[2])
        (folder / 'resources').mkdir(exist_ok=True)
        (folder / 'resources' / 'README').write_text('Render stub: no images.\n')
    else:
        requires = ET.SubElement(root, 'requires')
        ET.SubElement(requires, 'import', addon='xbmc.python', version='3.0.0')
        if addon_id.startswith('script.module.'):
            ET.SubElement(root, 'extension', point='xbmc.python.module', library='lib')
            (folder / 'lib').mkdir(exist_ok=True)
            (folder / 'lib' / '__init__.py').write_text('')
        elif parts[0] == 'plugin':
            extension = ET.SubElement(root, 'extension', point='xbmc.python.pluginsource', library='default.py')
            ET.SubElement(extension, 'provides').text = 'video'
            # Answer widget/plugin paths with an empty listing instead of a timeout.
            (folder / 'default.py').write_text(
                'import sys\nimport xbmcplugin\n'
                'if len(sys.argv) > 1 and sys.argv[1].lstrip("-").isdigit():\n'
                '    xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=True)\n')
        else:
            ET.SubElement(root, 'extension', point='xbmc.python.script', library='default.py')
            (folder / 'default.py').write_text('# Render stub: RunScript calls do nothing.\n')
    metadata = ET.SubElement(root, 'extension', point='xbmc.addon.metadata')
    ET.SubElement(metadata, 'summary', lang='en_GB').text = 'Stub for headless skin rendering'
    ET.SubElement(metadata, 'platform').text = 'all'
    ET.ElementTree(root).write(str(folder / 'addon.xml'), encoding='utf-8', xml_declaration=True)
    return folder


def extract_addon(data, dest, addon_id):
    """Unpack an add-on ZIP whose entries must all sit under <addon_id>/."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            parts = Path(name).parts
            if name.startswith('/') or '..' in parts or not parts or parts[0] != addon_id:
                raise ValueError('unexpected entry %r in %s zip' % (name, addon_id))
        archive.extractall(str(dest))


def install_dependencies(addon_xml, dest, index, fetch=None, mirror=MIRROR):
    """Install every required (non-core) add-on recursively. Returns {id: (version, 'official'|'stub')}.

    An official build is used when the repository has one at or above the required version;
    otherwise a stub with the required version is written. Optional imports are skipped."""
    fetch = fetch or (lambda url: urllib.request.urlopen(url, timeout=120).read())
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    installed, queue = {}, [r for r in requirements(addon_xml) if not r[2]]
    while queue:
        addon_id, minimum, _ = queue.pop(0)
        if addon_id.startswith(CORE_PREFIXES):
            continue
        if addon_id in installed:
            if version_key(installed[addon_id][0]) < version_key(minimum):
                print('warning: %s %s installed but %s requires >= %s' % (
                    addon_id, installed[addon_id][0], 'a dependency', minimum), file=sys.stderr)
            continue
        candidates = sorted((e for e in index.get(addon_id, []) if version_key(e[0]) >= version_key(minimum)),
                            key=lambda e: version_key(e[0]), reverse=True)
        if candidates:
            version, branch, element = candidates[0]
            url = '%s/%s/%s/%s-%s.zip' % (mirror, branch, addon_id, addon_id, version)
            try:
                extract_addon(fetch(url), dest, addon_id)
            except Exception as error:  # network or archive problem: fall back to a stub
                print('warning: %s: %s; using a stub' % (url, error), file=sys.stderr)
            else:
                installed[addon_id] = (version, 'official')
                queue += [r for r in requirements(element) if not r[2]]
                continue
        stub_addon(dest, addon_id, minimum)
        installed[addon_id] = (minimum, 'stub')
    return installed


# ---------------------------------------------------------------- profile

GUI_SETTINGS = {
    # TCP JSON-RPC (9090) and the EventServer (9777) on localhost only, no web server.
    'services.esenabled': 'true',
    'services.esallinterfaces': 'false',
    'services.webserver': 'false',
    'services.zeroconf': 'false',
    'services.upnp': 'false',
    'services.airplay': 'false',
    # Keep the screen static: no screensaver, add-on updates or notification popups.
    'screensaver.mode': '',
    'general.addonupdates': '2',
    'general.addonnotifications': 'false',
    'addons.unknownsources': 'true',
    'videoplayer.usevaapi': 'false',
    'videoplayer.usevdpau': 'false',
}
# Skip Bingie's first-run wizard (windows 1101/1102) and the splash video so startup ends on Home.
SKIN_SETTINGS = {
    'BingieFirstStartupDone': ('bool', 'true'),
    'BingieSecondStartupDone': ('bool', 'true'),
    'splash_screen': ('string', 'none'),
}


def write_settings(path, values, skin=None):
    """Merge Kodi settings into a guisettings.xml (version 2), keeping anything Kodi already wrote."""
    path = Path(path)
    root = ET.parse(str(path)).getroot() if path.exists() else ET.Element('settings', version='2')
    if skin:
        values = dict(values, **{'lookandfeel.skin': skin})
    existing = {node.get('id'): node for node in root.findall('setting')}
    for key, value in values.items():
        node = existing.get(key)
        if node is None:
            node = ET.SubElement(root, 'setting', id=key)
        node.attrib.pop('default', None)  # Kodi drops values still marked default="true"
        node.text = value
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(str(path), encoding='utf-8', xml_declaration=True)


def write_profile(data_dir, skin_id='skin.bingie'):
    """Write userdata files for a fresh Kodi data directory (special://home)."""
    userdata = Path(data_dir) / 'userdata'
    write_settings(userdata / 'guisettings.xml', GUI_SETTINGS)
    root = ET.Element('settings', version='1')
    for key, (kind, value) in SKIN_SETTINGS.items():
        ET.SubElement(root, 'setting', id=key, type=kind).text = value
    target = userdata / 'addon_data' / skin_id / 'settings.xml'
    target.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(str(target), encoding='utf-8', xml_declaration=True)
    advanced = ET.Element('advancedsettings', version='1.0')
    ET.SubElement(advanced, 'loglevel').text = '1'  # debug: include skin load details in kodi.log
    ET.SubElement(ET.SubElement(advanced, 'jsonrpc'), 'tcpport').text = '9090'
    ET.ElementTree(advanced).write(str(userdata / 'advancedsettings.xml'), encoding='utf-8', xml_declaration=True)


# ---------------------------------------------------------------- JSON-RPC / EventServer

class JsonRpc:
    """Minimal JSON-RPC client for Kodi's raw TCP interface; skips interleaved notifications."""

    def __init__(self, host='127.0.0.1', port=9090, timeout=10):
        self.address, self.timeout, self.next_id = (host, port), timeout, 0

    def call(self, method, params=None):
        self.next_id += 1
        request = {'jsonrpc': '2.0', 'id': self.next_id, 'method': method}
        if params is not None:
            request['params'] = params
        with socket.create_connection(self.address, timeout=self.timeout) as connection:
            connection.sendall(json.dumps(request).encode('utf-8'))
            buffer, decoder = '', json.JSONDecoder()
            # TCP may split a Unicode character across recv() calls.
            utf8 = codecs.getincrementaldecoder('utf-8')()
            while True:
                chunk = connection.recv(65536)
                if not chunk:
                    raise ConnectionError('Kodi closed the connection before answering ' + method)
                buffer += utf8.decode(chunk)
                while buffer.strip():
                    try:
                        message, end = decoder.raw_decode(buffer.lstrip())
                    except ValueError:
                        break  # incomplete object; read more
                    buffer = buffer.lstrip()[end:]
                    if message.get('id') == self.next_id:
                        if 'error' in message:
                            raise RuntimeError('%s: %s' % (method, message['error']))
                        return message.get('result')


def wait_until(predicate, timeout, interval=2.0, clock=time.monotonic, sleep=time.sleep):
    """Return the first truthy predicate() value, or None after timeout; exceptions count as falsy."""
    deadline = clock() + timeout
    while True:
        try:
            value = predicate()
            if value:
                return value
        except (OSError, RuntimeError, ValueError):
            pass
        if clock() >= deadline:
            return None
        sleep(interval)


def eventserver_packet(packet_type, payload, uid=0x4B4D):
    """One single-part EventServer v2.0 packet (see Kodi's tools/EventClients/lib/python/xbmcclient.py)."""
    header = b'XBMC' + bytes([2, 0]) + struct.pack('!HIIHI', packet_type, 1, 1, len(payload), uid) + b'\0' * 10
    return header + payload


def eventserver_builtin(command, host='127.0.0.1', port=9777):
    """Run a Kodi builtin (e.g. ActivateWindow(1171)) through the EventServer, like kodi-send --action."""
    helo = b'skin-render\0' + bytes([0]) + struct.pack('!HII', 0, 0, 0)
    action = bytes([1]) + command.encode('utf-8') + b'\0'  # ACTION_EXECBUILTIN
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        for packet in (eventserver_packet(0x01, helo), eventserver_packet(0x0A, action), eventserver_packet(0x02, b'')):
            sender.sendto(packet, (host, port))
            time.sleep(0.2)


def rpc_main(args):
    rpc = JsonRpc(port=args.port)
    if args.action == 'wait':
        ok = wait_until(lambda: rpc.call('JSONRPC.Ping') == 'pong', args.timeout)
        print('JSON-RPC ready' if ok else 'JSON-RPC not reachable after %ss' % args.timeout)
        return 0 if ok else 1
    if args.action == 'wait-window':
        target = int(args.value[0]) if args.value else HOME_WINDOW
        state = {}

        def current():
            state.update(rpc.call('GUI.GetProperties', {'properties': ['currentwindow']})['currentwindow'])
            return state.get('id') == target
        ok = wait_until(current, args.timeout)
        print('window %s reached' % target if ok else 'window %s not reached; current %s' % (target, state))
        return 0 if ok else 1
    if args.action == 'enable':
        failed = 0
        for addon_id in args.value:
            try:
                rpc.call('Addons.SetAddonEnabled', {'addonid': addon_id, 'enabled': True})
                print('enabled ' + addon_id)
            except (RuntimeError, OSError) as error:
                failed += 1
                print('could not enable %s: %s' % (addon_id, error))
        return 1 if failed else 0
    if args.action == 'skin':
        skin = rpc.call('Settings.GetSettingValue', {'setting': 'lookandfeel.skin'})['value']
        print('active skin: ' + skin)
        return 0 if not args.value or skin == args.value[0] else 1
    if args.action == 'window':
        params = {'window': args.value[0]}
        if len(args.value) > 1:
            params['parameters'] = args.value[1:]
        rpc.call('GUI.ActivateWindow', params)
        return 0
    if args.action == 'builtin':
        eventserver_builtin(' '.join(args.value))
        return 0
    if args.action == 'action':
        rpc.call('Input.ExecuteAction', {'action': args.value[0]})
        return 0
    if args.action == 'quit':
        try:
            rpc.call('Application.Quit')
        except (OSError, ConnectionError):
            pass  # Kodi may close the socket while quitting
        return 0
    raise ValueError(args.action)


# ---------------------------------------------------------------- kodi.log

LOG_LINE = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+ T:\d+\s+(\w+) <[^>]+>: (.*)$')
SKIN_ERROR = re.compile(r'error loading|skin has invalid include|failed to load|invalid include'
                        r'|unable to load window xml', re.I)
SKIN_CONTEXT = re.compile(r'skin|\.xml\b|include|window', re.I)
# Kodi's condition parser (InfoExpression) logs these without naming a file, so they skip SKIN_CONTEXT.
CONDITION_ERROR = re.compile(r'error parsing boolean expression|malformed expression'
                             r'|^(?:[\w:]+(?: -)?:? )?(?:misplaced|unmatched|missing) [\[\]()]', re.I)


def skin_errors(log_text):
    """Normalised (timestamp-free) skin XML error messages in a kodi.log, in first-seen order."""
    found = []
    for line in log_text.splitlines():
        match = LOG_LINE.match(line)
        message = (match.group(2) if match else line).strip()
        message = re.sub(r'\b0x[0-9a-f]+\b', '0x?', message, flags=re.I)
        # The install folder depends on the machine and Kodi packaging; the baseline names skin files
        # as special://skin/<path>.
        message = re.sub(r'\S*/addons/skin\.bingie/', 'special://skin/', message)
        skin = SKIN_ERROR.search(message) and SKIN_CONTEXT.search(message) or CONDITION_ERROR.search(message)
        if skin and message not in found:
            found.append(message)
    return found


def read_baseline(path, unresolved=ROOT / 'tests' / 'upstream-unresolved.json'):
    """Accepted messages: the baseline file plus Kodi's warning for every allowlisted upstream include."""
    path, known = Path(path), []
    if path.exists():
        known = [line.rstrip('\n') for line in path.read_text(encoding='utf-8').splitlines()
                 if line.strip() and not line.startswith('#')]
    if unresolved and Path(unresolved).exists():
        names = json.loads(Path(unresolved).read_text(encoding='utf-8'))['includes']
        known += ['Skin has invalid include: ' + name for name in names]
    return known


def check_log(log_path, baseline_path, summary=None):
    """0 when every skin error is in the baseline, 1 when new ones appear, 2 without a log."""
    log_path = Path(log_path)
    if not log_path.exists():
        print('::error::%s not found; Kodi did not run' % log_path)
        return 2
    errors = skin_errors(log_path.read_text(encoding='utf-8', errors='replace'))
    listed = read_baseline(baseline_path, unresolved=None)
    known = set(read_baseline(baseline_path))
    new = [e for e in errors if e not in known]
    gone = sorted(set(listed) - set(errors))
    lines = ['### kodi.log skin errors', '',
             '%d found, %d new, %d baseline entries no longer seen' % (len(errors), len(new), len(gone)), '']
    lines += ['- NEW: `%s`' % e for e in new] + ['- known: `%s`' % e for e in errors if e in known]
    lines += ['- fixed (remove from baseline): `%s`' % e for e in gone]
    report = '\n'.join(lines) + '\n'
    print(report)
    if summary:
        with open(summary, 'a', encoding='utf-8') as handle:
            handle.write(report)
    for error in new:
        print('::error title=New skin error in kodi.log::%s' % error)
    return 1 if new else 0


# ---------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description='Headless Kodi render helpers')
    commands = parser.add_subparsers(dest='command')
    commands.required = True
    deps = commands.add_parser('deps', help='install the skin dependencies into an addons folder')
    deps.add_argument('--addon-xml', default=str(ROOT / 'addon.xml'))
    deps.add_argument('--dest', required=True)
    deps.add_argument('--manifest', help='write {id: [version, source]} JSON here')
    deps.add_argument('--offline', action='store_true', help='stub everything without contacting the mirror')
    profile = commands.add_parser('profile', help='write a fresh Kodi profile')
    profile.add_argument('--data', required=True, help='Kodi data directory (special://home)')
    set_skin = commands.add_parser('set-skin', help='select a skin in guisettings.xml (Kodi must be stopped)')
    set_skin.add_argument('--data', required=True)
    set_skin.add_argument('--skin', default='skin.bingie')
    rpc = commands.add_parser('rpc', help='JSON-RPC/EventServer actions on a running Kodi')
    rpc.add_argument('action', choices=['wait', 'wait-window', 'enable', 'skin', 'window', 'builtin', 'action', 'quit'])
    rpc.add_argument('value', nargs='*')
    rpc.add_argument('--timeout', type=float, default=120)
    rpc.add_argument('--port', type=int, default=9090)
    log = commands.add_parser('check-log', help='compare kodi.log skin errors with the baseline')
    log.add_argument('--log', required=True)
    log.add_argument('--baseline', default=str(ROOT / 'tests' / 'render-known-log-errors.txt'))
    log.add_argument('--summary', default=os.environ.get('GITHUB_STEP_SUMMARY'))
    args = parser.parse_args(argv)

    if args.command == 'deps':
        index = {}
        if not args.offline:
            try:
                index = load_repository()
            except Exception as error:
                print('::warning::Kodi add-on repository unavailable (%s); stubbing all dependencies' % error)
        installed = install_dependencies(args.addon_xml, args.dest, index)
        for addon_id, (version, source) in sorted(installed.items()):
            print('%-40s %-16s %s' % (addon_id, version, source))
        if args.manifest:
            Path(args.manifest).write_text(json.dumps(installed, indent=2, sort_keys=True) + '\n')
        return 0
    if args.command == 'profile':
        write_profile(args.data)
        return 0
    if args.command == 'set-skin':
        write_settings(Path(args.data) / 'userdata' / 'guisettings.xml', {}, skin=args.skin)
        return 0
    if args.command == 'rpc':
        return rpc_main(args)
    return check_log(args.log, args.baseline, args.summary)


if __name__ == '__main__':
    sys.exit(main())
