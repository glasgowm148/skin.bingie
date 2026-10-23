import io
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
import zipfile
from contextlib import redirect_stdout
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import kodi_render as kr


def repo_addon(addon_id, version, imports=()):
    xml = '<addon id="%s" version="%s"><requires>%s</requires></addon>' % (addon_id, version, ''.join(
        '<import addon="%s" version="%s"%s/>' % (i, v, ' optional="true"' if o else '') for i, v, o in imports))
    return ET.fromstring(xml)


def addon_zip(addon_id, extra=None):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr(extra or addon_id + '/addon.xml', '<addon id="%s"/>' % addon_id)
    return data.getvalue()


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.tmp))


class DependencyTests(TempDir):
    def test_versions_compare_like_kodi(self):
        self.assertLess(kr.version_key('2.1.2'), kr.version_key('2.1.3'))
        self.assertLess(kr.version_key('1.1.1'), kr.version_key('1.1.1+matrix.2'))
        self.assertLess(kr.version_key('1.0.0~beta1'), kr.version_key('1.0.0'))
        self.assertEqual(kr.version_key('2.0'), kr.version_key('2.0.0'))

    def test_official_builds_recursive_and_stubs_for_the_rest(self):
        skin = repo_addon('skin.x', '1', [('xbmc.gui', '5.17.0', False), ('script.skinshortcuts', '2.0.3', False),
                                          ('plugin.program.autocompletion', '2.1.3', False),
                                          ('script.bingie.helper', '1.1.2', False), ('script.opt', '1', True),
                                          ('resource.images.studios.coloured', '1.0.0', False)])
        index = {'script.skinshortcuts': [('2.0.3', 'matrix', repo_addon('script.skinshortcuts', '2.0.3', [
                     ('xbmc.python', '3.0.0', False), ('script.module.unidecode', '1.1.1', False)]))],
                 'script.module.unidecode': [('1.3.6', 'matrix', repo_addon('script.module.unidecode', '1.3.6')),
                                             ('1.1.1', 'leia', repo_addon('script.module.unidecode', '1.1.1'))],
                 'plugin.program.autocompletion': [('2.1.2', 'matrix', repo_addon('x', '2.1.2'))]}
        fetched = []

        def fetch(url):
            fetched.append(url)
            return addon_zip(url.rsplit('/', 2)[1])
        with redirect_stdout(io.StringIO()):
            installed = kr.install_dependencies(skin, self.tmp, index, fetch, mirror='https://m')
        self.assertEqual(installed, {
            'script.skinshortcuts': ('2.0.3', 'official'), 'script.module.unidecode': ('1.3.6', 'official'),
            'plugin.program.autocompletion': ('2.1.3', 'stub'),  # repository build is too old
            'script.bingie.helper': ('1.1.2', 'stub'), 'resource.images.studios.coloured': ('1.0.0', 'stub')})
        self.assertIn('https://m/matrix/script.module.unidecode/script.module.unidecode-1.3.6.zip', fetched)
        self.assertFalse((self.tmp / 'script.opt').exists())
        for addon_id, (version, source) in installed.items():
            root = ET.parse(str(self.tmp / addon_id / 'addon.xml')).getroot()
            self.assertEqual(root.get('id'), addon_id)
            if source == 'stub':
                self.assertEqual(root.get('version'), version)
        helper = ET.parse(str(self.tmp / 'script.bingie.helper/addon.xml')).getroot()
        self.assertEqual(helper.find('requires/import').get('addon'), 'xbmc.python')
        self.assertTrue((self.tmp / 'script.bingie.helper/default.py').exists())
        plugin = ET.parse(str(self.tmp / 'plugin.program.autocompletion/addon.xml')).getroot()
        self.assertEqual(plugin.find('extension').get('point'), 'xbmc.python.pluginsource')
        resource = ET.parse(str(self.tmp / 'resource.images.studios.coloured/addon.xml')).getroot()
        self.assertEqual(resource.find('extension').attrib,
                         {'point': 'kodi.resource.images', 'compile': 'false', 'type': 'studios'})

    def test_unsafe_or_failed_download_falls_back_to_stub(self):
        skin = repo_addon('skin.x', '1', [('script.a', '1.0.0', False)])
        index = {'script.a': [('1.0.0', 'omega', repo_addon('script.a', '1.0.0'))]}
        with self.assertRaises(ValueError):
            kr.extract_addon(addon_zip('script.a', '../evil.py'), self.tmp, 'script.a')
        with redirect_stdout(io.StringIO()), mock.patch('sys.stderr', io.StringIO()):
            installed = kr.install_dependencies(skin, self.tmp, index, lambda url: addon_zip('script.a', 'x/y'))
        self.assertEqual(installed, {'script.a': ('1.0.0', 'stub')})
        self.assertFalse((self.tmp.parent / 'evil.py').exists())

    def test_skin_dependencies_resolve_offline(self):
        with redirect_stdout(io.StringIO()):
            installed = kr.install_dependencies(ROOT / 'addon.xml', self.tmp, {})
        self.assertIn('script.skinshortcuts', installed)
        self.assertFalse(any(i.startswith(('xbmc.', 'kodi.')) for i in installed))


class ProfileTests(TempDir):
    def test_profile_skips_first_run_and_selects_skin_later(self):
        kr.write_profile(self.tmp)
        gui = self.tmp / 'userdata/guisettings.xml'
        settings = {n.get('id'): n.text for n in ET.parse(str(gui)).getroot()}
        self.assertEqual(settings['services.esenabled'], 'true')
        self.assertNotIn('lookandfeel.skin', settings)
        skin = ET.parse(str(self.tmp / 'userdata/addon_data/skin.bingie/settings.xml')).getroot()
        self.assertEqual({n.get('id'): n.text for n in skin}['BingieFirstStartupDone'], 'true')
        # Kodi rewrites guisettings.xml with defaults marked; set-skin must override them.
        gui.write_text('<settings version="2"><setting id="lookandfeel.skin" default="true">skin.estuary</setting>'
                       '<setting id="other">1</setting></settings>')
        kr.main(['set-skin', '--data', str(self.tmp)])
        nodes = {n.get('id'): n for n in ET.parse(str(gui)).getroot()}
        self.assertEqual((nodes['lookandfeel.skin'].text, nodes['lookandfeel.skin'].get('default')),
                         ('skin.bingie', None))
        self.assertEqual(nodes['other'].text, '1')


class LogTests(TempDir):
    LOG = '\n'.join([
        '2026-10-11 10:00:00.100 T:123     info <general>: Loading skin file: Home.xml',
        '2026-10-11 10:00:01.200 T:123  warning <general>: Skin has invalid include: Header_Align_Left',
        '2026-10-11 10:00:01.300 T:123  warning <general>: Skin has invalid include: Brand_New',
        '2026-10-11 10:00:01.400 T:124    error <general>: Error loading skin file Custom_9.xml at 0x7f12',
        '2026-10-11 10:00:01.500 T:124    error <general>: CPythonInvoker: failed to load module foo',
        '2026-10-11 10:00:01.600 T:124    error <general>: Error loading skin file Custom_9.xml at 0x7f99',
    ])

    def test_errors_are_normalised_and_deduplicated(self):
        self.assertEqual(kr.skin_errors(self.LOG), [
            'Skin has invalid include: Header_Align_Left', 'Skin has invalid include: Brand_New',
            'Error loading skin file Custom_9.xml at 0x?'])

    def test_skin_install_folder_is_normalised(self):
        for folder in ('/home/runner/.var/app/tv.kodi.Kodi/data', '/storage/emulated/0/Android/data/org.xbmc.kodi/files/.kodi'):
            line = ('2026-10-11 10:00:01.700 T:124    error <general>: Error loading include file '
                    + folder + '/addons/skin.bingie/1080i/x.xml: Failed to open file (row: 0, col: 0)')
            self.assertEqual(kr.skin_errors(line), [
                'Error loading include file special://skin/1080i/x.xml: Failed to open file (row: 0, col: 0)'])

    def test_condition_parser_errors_are_reported(self):
        log = '\n'.join('2026-10-11 10:00:02.%03d T:124    error <general>: %s' % (i, m) for i, m in enumerate([
            'Misplaced ]', 'Unmatched [', 'Missing )', 'Error parsing boolean expression [a | b',
            'Unable to load window XML: Custom_1.xml. Line 3', 'Unmatched track id 5', 'Missing subtitle']))
        self.assertEqual(kr.skin_errors(log), [
            'Misplaced ]', 'Unmatched [', 'Missing )', 'Error parsing boolean expression [a | b',
            'Unable to load window XML: Custom_1.xml. Line 3'])

    def test_only_new_errors_fail(self):
        log, baseline = self.tmp / 'kodi.log', self.tmp / 'baseline.txt'
        log.write_text(self.LOG)
        baseline.write_text('# comment\nError loading skin file Custom_9.xml at 0x?\nGone error\n')
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(kr.check_log(log, baseline), 1)
        self.assertIn('NEW: `Skin has invalid include: Brand_New`', out.getvalue())
        self.assertIn('known: `Skin has invalid include: Header_Align_Left`', out.getvalue())  # allowlisted upstream
        self.assertIn('fixed (remove from baseline): `Gone error`', out.getvalue())
        baseline.write_text(baseline.read_text() + 'Skin has invalid include: Brand_New\n')
        with redirect_stdout(io.StringIO()):
            self.assertEqual(kr.check_log(log, baseline, summary=str(self.tmp / 'summary.md')), 0)
            self.assertEqual(kr.check_log(self.tmp / 'missing.log', baseline), 2)
        self.assertIn('kodi.log skin errors', (self.tmp / 'summary.md').read_text())

    def test_recorded_baseline_is_clean_text(self):
        for line in kr.read_baseline(ROOT / 'tests/render-known-log-errors.txt', unresolved=None):
            self.assertEqual(line, line.strip())


class RemoteTests(unittest.TestCase):
    def test_json_rpc_preserves_unicode_across_every_byte_boundary(self):
        label = 'Café 日本 🎬'
        notification = json.dumps({'jsonrpc': '2.0', 'method': 'GUI.OnNotification',
                                   'params': {'label': label}}, ensure_ascii=False)
        reply = json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'label': label}}, ensure_ascii=False)
        wire = (notification + reply).encode('utf-8')
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        connection.recv.side_effect = [wire[i:i + 1] for i in range(len(wire))] + [b'']
        with mock.patch.object(kr.socket, 'create_connection', return_value=connection):
            self.assertEqual(kr.JsonRpc().call('GUI.GetProperties'), {'label': label})

    def test_eventserver_packet_layout(self):
        packet = kr.eventserver_packet(0x0A, b'\x01ActivateWindow(1171)\x00')
        self.assertEqual(packet[:6], b'XBMC\x02\x00')
        self.assertEqual(len(packet) - 32, 22)
        packet_type, seq, maxseq, size = kr.struct.unpack('!HIIH', packet[6:18])
        self.assertEqual((packet_type, seq, maxseq, size), (0x0A, 1, 1, 22))

    def test_json_rpc_skips_notifications_and_joins_chunks(self):
        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        self.addCleanup(server.close)
        received = []

        def serve():
            connection, _ = server.accept()
            with connection:
                received.append(json.loads(connection.recv(65536).decode()))
                reply = json.dumps({'jsonrpc': '2.0', 'id': received[0]['id'],
                                    'result': {'currentwindow': {'id': 10000, 'label': 'Home'}}})
                connection.sendall(b'{"jsonrpc":"2.0","method":"GUI.OnScreensaverDeactivated","params":{}}')
                connection.sendall(reply[:15].encode())
                connection.sendall(reply[15:].encode())
        thread = threading.Thread(target=serve)
        thread.start()
        result = kr.JsonRpc(port=server.getsockname()[1]).call('GUI.GetProperties', {'properties': ['currentwindow']})
        thread.join(5)
        self.assertEqual(result['currentwindow']['id'], 10000)
        self.assertEqual(received[0]['method'], 'GUI.GetProperties')

    def test_wait_until_retries_errors_until_timeout(self):
        now, calls = [0.0], []

        def predicate():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionRefusedError()
            return len(calls) >= 4 and 'ready'
        sleep = lambda seconds: now.__setitem__(0, now[0] + seconds)
        self.assertEqual(kr.wait_until(predicate, 100, 1, clock=lambda: now[0], sleep=sleep), 'ready')
        self.assertIsNone(kr.wait_until(lambda: False, 5, 2, clock=lambda: now[0], sleep=sleep))


class WorkflowTests(unittest.TestCase):
    def test_workflows_pin_actions_and_stay_read_only(self):
        for path in sorted((ROOT / '.github/workflows').glob('*.yml')):
            text = path.read_text()
            for ref in re.findall(r'uses:\s*(\S+)', text):
                self.assertRegex(ref, r'^[\w.-]+/[\w.-]+@[0-9a-f]{40}$', path.name)
            self.assertRegex(text, r'\npermissions:\n  contents: read\n', path.name)
            block = re.split(r'\n\S', text.split('\npermissions:', 1)[1], maxsplit=1)[0]
            self.assertNotIn('write', re.sub(r'#.*', '', block), path.name)

    @unittest.skipUnless(shutil.which('bash'), 'bash is required')
    def test_render_script_parses(self):
        subprocess.run(['bash', '-n', str(ROOT / 'scripts/render_kodi.sh')], check=True)


if __name__ == '__main__':
    unittest.main()
