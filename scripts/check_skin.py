"""Validate all XML and reject unresolved includes introduced by this fork."""
import json
import re
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


def unguarded_autoplay(folder=ROOT / '1080i'):
    """Deferred previews must not replace media the user is already watching or listening to."""
    found = []
    for path in sorted(folder.glob('*.xml')):
        for node in ET.parse(path).iter():
            if node.tag in HANDLERS and AUTOPLAY.search(node.text or ''):
                if '$EXP[KM_PreviewMayStart]' not in (node.get('condition') or ''):
                    found.append('%s: %s' % (path.name, (node.text or '').strip()[:60]))
    return found


def check():
    files = list(ROOT.rglob('*.xml'))
    for path in files:
        if '.git' not in path.parts:
            ET.parse(path)
    allowed = set(json.loads((ROOT / 'tests/upstream-unresolved.json').read_text()))
    missing = unresolved(ROOT / '1080i') - allowed
    if missing:
        raise ValueError('New unresolved includes: ' + ', '.join(sorted(missing)))
    autoplay = unguarded_autoplay()
    if autoplay:
        raise ValueError('Auto-preview without playback guard: ' + '; '.join(autoplay))
    for path in (ROOT / '1080i').glob('*.xml'):
        if re.search(r'markglasgow@|8k-pro-iptvstore|192\.168\.', path.read_text(), re.I):
            raise ValueError('Household configuration in ' + path.name)
    print('Validated %d XML files; no new unresolved includes or household identifiers' % len(files))


if __name__ == '__main__':
    check()
