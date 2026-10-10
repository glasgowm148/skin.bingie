import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_skin import check
from build_skin import build


class SkinTests(unittest.TestCase):
    def test_complete_xml_and_include_tree(self):
        check()

    def test_provider_actions_keep_stock_fallback(self):
        root = ET.parse(ROOT / '1080i/IncludesDialogVideoInfo.xml').getroot()
        for name in ['BingieInfo', 'BingieAltInfo']:
            wrapper = next(n for n in root.findall('include') if n.get('name') == name)
            branches = wrapper.findall('include')
            self.assertEqual(len(branches), 2)
            self.assertIn('Skin.HasSetting(KM_EnableProviderActions)', branches[0].get('condition'))
            self.assertEqual(branches[1].get('condition'), '![' + branches[0].get('condition') + ']')
            stock = next(n for n in root.findall('include') if n.get('name') == name + '_Stock')
            self.assertNotIn('mode=manager_', ET.tostring(stock).decode())

    def test_guide_defaults_to_stock_without_helper(self):
        nodes = ET.parse(ROOT / '1080i/MyPVRGuide.xml').findall('controls/include')
        self.assertEqual(len(nodes), 2)
        self.assertIn('System.HasAddon(script.kodi.live.tv)', nodes[0].get('condition'))
        self.assertEqual(nodes[1].get('condition'), '![' + nodes[0].get('condition') + ']')
        self.assertEqual(nodes[1].text, 'Stock_PVR_Guide')

    def test_switch_retains_native_logoff(self):
        text = (ROOT / '1080i/IncludesBingie.xml').read_text()
        self.assertIn('System.LogOff</onclick>', text)
        self.assertIn('Skin.HasSetting(KM_EnableDirectSwitch)', text)

    def test_provider_initializers_are_opt_in(self):
        for node in ET.parse(ROOT / '1080i/DialogVideoInfo.xml').iter('onload'):
            if 'mode=manager_' in (node.text or ''):
                self.assertIn('Skin.HasSetting(KM_EnableProviderActions)', node.get('condition'))

    def test_archive_is_deterministic_and_has_no_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            path = build(folder)
            before = path.read_bytes()
            self.assertEqual(build(folder).read_bytes(), before)
            with ZipFile(path) as archive:
                names = archive.namelist()
                self.assertIn('skin.bingie/addon.xml', names)
                self.assertIn('skin.bingie/LICENSE', names)
                self.assertFalse(any('/userdata/' in n or '/tests/' in n or '/scripts/' in n or '/.git/' in n for n in names))
                self.assertIsNone(archive.testzip())


if __name__ == '__main__':
    unittest.main()
