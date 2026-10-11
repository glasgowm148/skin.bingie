"""Validate all XML and reject unresolved includes and broken references introduced by this fork."""
import json
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def unresolved(folder):
    definitions, references = set(), set()
    for path in folder.glob('*.xml'):
        tree = ET.parse(path)
        for node in tree.iter('include'):
            if node.get('name'):
                definitions.add(node.get('name'))
            name = node.get('content') or (node.text or '').strip()
            if name and '$' not in name:
                references.add(name)
    return references - definitions


AUTOPLAY = re.compile(r'AlarmClock\([^,]+,\s*(?:PlayMedia\(|RunScript\(script\.bingie\.helper,action=playtrailer)', re.I)
HANDLERS = ('onload', 'onunload', 'onfocus', 'onunfocus')


PREVIEW_GUARD = '$EXP[KM_PreviewMayStart]'


def top_level_and_terms(condition):
    """Terms ANDed at the top level of a Kodi condition, or [] when the top level has an OR.

    Kodi binds ! tighter than + and + tighter than |; only [] groups ($EXP[...] is one operand)."""
    condition = condition.strip()
    while True:
        depth, inner = 0, False
        if condition.startswith('[') and condition.endswith(']'):
            inner = True
            for index, char in enumerate(condition):
                depth += {'[': 1, ']': -1}.get(char, 0)
                if depth == 0 and index < len(condition) - 1:
                    inner = False
                    break
        if not inner:
            break
        condition = condition[1:-1].strip()
    terms, depth, current, index = [], 0, '', 0
    while index < len(condition):
        if condition.startswith('$EXP[', index):
            end = condition.index(']', index)
            current += condition[index:end + 1]
            index = end + 1
            continue
        char = condition[index]
        depth += {'[': 1, ']': -1}.get(char, 0)
        if depth == 0 and char == '|':
            return []
        if depth == 0 and char == '+':
            terms.append(current.strip())
            current = ''
        else:
            current += char
        index += 1
    return terms + [current.strip()]


def unguarded_autoplay(folder=ROOT / '1080i'):
    """Deferred previews must not replace media the user is already watching or listening to."""
    found = []
    for path in sorted(folder.glob('*.xml')):
        for node in ET.parse(path).iter():
            guarded = PREVIEW_GUARD in top_level_and_terms(node.get('condition') or '')
            if node.tag in HANDLERS and AUTOPLAY.search(node.text or '') and not guarded:
                found.append('%s: %s' % (path.name, (node.text or '').strip()[:60]))
    return found


def xbt_names(path):
    """Texture paths packed in a Textures.xbt (XBTF v2) bundle, lower-cased as Kodi looks them up."""
    data = path.read_bytes()
    if data[:4] != b'XBTF':
        raise ValueError('Not an XBT texture bundle: ' + str(path))
    count, offset, names = struct.unpack_from('<I', data, 5)[0], 9, set()
    for _ in range(count):
        names.add(data[offset:offset + 256].split(b'\0')[0].decode('utf-8').lower())
        frames = struct.unpack_from('<I', data, offset + 260)[0]
        offset += 264 + frames * 40
    return names


def broken_references(root=ROOT, allowed_textures=()):
    """Skin strings, variables, expressions, fonts, custom windows and packed textures that do not exist."""
    folder = root / '1080i'
    texts = {path.name: path.read_text(encoding='utf-8') for path in sorted(folder.glob('*.xml'))}
    po = (root / 'language/resource.language.en_gb/strings.po').read_text(encoding='utf-8')
    strings = {int(i) for i in re.findall(r'^msgctxt "#(\d+)"', po, re.M)}
    fontsets = [{(f.findtext('name') or '').strip().lower() for f in fontset.iter('font')}
                for fontset in ET.parse(folder / 'Font.xml').getroot().iter('fontset')]
    windows = {int(m) for text in texts.values() for m in re.findall(r'<window[^>]*\bid="(\d+)"', text)}
    textures = xbt_names(root / 'media/Textures.xbt') | {t.lower() for t in allowed_textures}
    defined = {kind: {n for text in texts.values() for n in re.findall(r'<%s name="([^"]+)"' % kind, text)}
               for kind in ('variable', 'expression')}
    errors = set()
    for name, text in texts.items():
        for kind, token in (('variable', 'VAR'), ('expression', 'EXP')):
            for ref in re.findall(r'\$%s\[([^\],$]+)' % token, text):
                if ref.strip() not in defined[kind]:
                    errors.add('%s: undefined $%s[%s]' % (name, token, ref))
        ids = re.findall(r'\$LOCALIZE\[(\d+)\]', text) + re.findall(r'<(?:label|label2|altlabel|hinttext)>(\d+)</', text)
        for ref in ids:
            if 31000 <= int(ref) < 33000 and int(ref) not in strings:
                errors.add('%s: skin string %s missing from en_gb strings.po' % (name, ref))
        if name != 'Font.xml':
            for ref in re.findall(r'<font>\s*([^<$\s]+)\s*</font>', text):
                if any(ref.lower() not in fontset for fontset in fontsets):
                    errors.add('%s: font %s missing from a fontset' % (name, ref))
        for ref in re.findall(r'(?:ActivateWindow|ReplaceWindow|Dialog\.Close|Window\.Is\w+)\((11\d\d)\b', text, re.I):
            if int(ref) not in windows:
                errors.add('%s: custom window %s does not exist' % (name, ref))
        for ref in re.findall(r'[>"]\s*([\w\-/ ]+\.(?:png|jpg|gif))\s*[<"]', text, re.I):
            if ref.lower() not in textures:
                errors.add('%s: texture %s missing from Textures.xbt' % (name, ref))
    return sorted(errors)


RUNTIME_TEXT = {'.xml', '.xsp', '.po', '.theme', '.txt', '.json'}
HOUSEHOLD = re.compile(r'markglasgow@|8k-pro-iptvstore|192\.168\.|\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', re.I)


def household_identifiers(root=ROOT):
    """Runtime text that would ship in the ZIP must not carry household addresses or accounts."""
    found = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        runtime = relative.parts[0] in {'1080i', 'colors', 'extras', 'language', 'shortcuts'} or relative.name == 'addon.xml'
        if runtime and path.is_file() and path.suffix.lower() in RUNTIME_TEXT:
            if HOUSEHOLD.search(path.read_text(encoding='utf-8', errors='replace')):
                found.append(relative.as_posix())
    return found


def check():
    files = list(ROOT.rglob('*.xml'))
    for path in files:
        if '.git' not in path.parts:
            ET.parse(path)
    known = json.loads((ROOT / 'tests/upstream-unresolved.json').read_text())
    missing = unresolved(ROOT / '1080i') - set(known['includes'])
    if missing:
        raise ValueError('New unresolved includes: ' + ', '.join(sorted(missing)))
    broken = broken_references(allowed_textures=known['textures'])
    if broken:
        raise ValueError('Broken references: ' + '; '.join(broken))
    autoplay = unguarded_autoplay()
    if autoplay:
        raise ValueError('Auto-preview without playback guard: ' + '; '.join(autoplay))
    private = household_identifiers()
    if private:
        raise ValueError('Household configuration in ' + ', '.join(private))
    print('Validated %d XML files; no new unresolved includes, broken references or household identifiers' % len(files))


if __name__ == '__main__':
    check()
