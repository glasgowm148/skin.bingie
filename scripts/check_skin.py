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


def check():
    files = list(ROOT.rglob('*.xml'))
    for path in files:
        if '.git' not in path.parts:
            ET.parse(path)
    allowed = set(json.loads((ROOT / 'tests/upstream-unresolved.json').read_text()))
    missing = unresolved(ROOT / '1080i') - allowed
    if missing:
        raise ValueError('New unresolved includes: ' + ', '.join(sorted(missing)))
    for path in (ROOT / '1080i').glob('*.xml'):
        if re.search(r'markglasgow@|8k-pro-iptvstore|192\.168\.', path.read_text(), re.I):
            raise ValueError('Household configuration in ' + path.name)
    print('Validated %d XML files; no new unresolved includes or household identifiers' % len(files))


if __name__ == '__main__':
    check()
