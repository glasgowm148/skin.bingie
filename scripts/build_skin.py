"""Create a deterministic skin ZIP without profiles, secrets or development files."""
import hashlib
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = {'1080i', 'colors', 'extras', 'fonts', 'language', 'media', 'playlists', 'resources', 'shortcuts'}


def build(destination=None):
    addon = ET.parse(ROOT / 'addon.xml').getroot()
    target = Path(destination or ROOT / 'dist')
    target.mkdir(parents=True, exist_ok=True)
    target = target / (addon.get('id') + '-' + addon.get('version') + '.zip')
    entries = []
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if not (relative.parts[0] in RUNTIME or relative.as_posix() in {'addon.xml', 'LICENSE'}):
            continue
        if path.is_symlink() or any(part.startswith('.') for part in relative.parts):
            raise ValueError('Linked/hidden artifact in runtime tree: ' + str(relative))
        if not path.is_file():
            continue
        if '__pycache__' in relative.parts or path.suffix.lower() in {'.pyc', '.db', '.log', '.key'}:
            raise ValueError('Private/development artifact in runtime tree: ' + str(relative))
        entries.append((path, relative))
    # A failed build must not replace the last complete release ZIP.
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        staged = Path(temporary) / target.name
        with ZipFile(staged, 'w', ZIP_DEFLATED) as archive:
            for path, relative in entries:
                info = ZipInfo(addon.get('id') + '/' + relative.as_posix(), (2026, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        # A published version number must always name the same bytes.
        if target.exists() and target.read_bytes() != staged.read_bytes():
            raise ValueError('%s already exists with different contents; bump the addon.xml version' % target.name)
        os.replace(staged, target)
    target.with_suffix('.zip.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest() + '  ' + target.name + '\n')
    return target


if __name__ == '__main__':
    from check_skin import check
    check()
    print(build())
