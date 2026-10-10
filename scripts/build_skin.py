"""Create a deterministic skin ZIP without profiles, secrets or development files."""
import hashlib
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
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob('*')):
            relative = path.relative_to(ROOT)
            if not path.is_file() or not (relative.parts[0] in RUNTIME or relative.as_posix() in {'addon.xml', 'LICENSE'}):
                continue
            if '__pycache__' in relative.parts or path.suffix in {'.pyc', '.db', '.log', '.key'}:
                raise ValueError('Private/development artifact in runtime tree: ' + str(relative))
            info = ZipInfo(addon.get('id') + '/' + relative.as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    target.with_suffix('.zip.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest() + '  ' + target.name + '\n')
    return target


if __name__ == '__main__':
    from check_skin import check
    check()
    print(build())
