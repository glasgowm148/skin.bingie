import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_skin import broken_references, check, unguarded_autoplay
from build_skin import build
import build_skin


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

    def test_missing_addon_still_allows_disabling_active_integration(self):
        root = ET.parse(ROOT / '1080i/Custom_1171_ExperienceSettings.xml').getroot()
        for control in root.iter('control'):
            action = control.findtext('onclick', '')
            if action.startswith('Skin.ToggleSetting(KM_'):
                setting = action[len('Skin.ToggleSetting('):-1]
                self.assertIn('Skin.HasSetting(' + setting + ') | ', control.findtext('enable'))

    def test_auto_previews_never_replace_user_playback(self):
        self.assertEqual(unguarded_autoplay(), [])
        root = ET.parse(ROOT / '1080i/Includes.xml').getroot()
        guard = next(n for n in root.iter('expression') if n.get('name') == 'KM_PreviewMayStart').text
        self.assertIn('!Player.HasMedia', guard)
        self.assertIn('$EXP[IsPlayingUnrecognizedContent]', guard)

    def test_recovery_prompt_stays_closed_after_back(self):
        visible = ET.parse(ROOT / '1080i/Custom_1170_StreamRecovery.xml').getroot().findtext('visible')
        self.assertIn('!String.IsEqual(Window(Home).Property(pov_recovery_dismissed),'
                      'Window(Home).Property(pov_recovery_session))', visible)

    def test_pvr_hub_defaults_to_stock_channel_rows(self):
        root = ET.parse(ROOT / '1080i/IncludesHomeWidgets.xml').getroot()
        wrapper = next(n for n in root.findall('include') if n.get('name') == 'bingie_items_pvr')
        branches = wrapper.findall('include')
        self.assertEqual(len(branches), 2)
        self.assertIn('Skin.HasSetting(KM_EnableLiveTV)', branches[0].get('condition'))
        self.assertEqual(branches[1].get('condition'), '![' + branches[0].get('condition') + ']')
        self.assertEqual(branches[1].text, 'bingie_items_pvr_Stock')
        stock = ET.tostring(next(n for n in root.findall('include') if n.get('name') == 'bingie_items_pvr_Stock')).decode()
        self.assertNotIn('System.ProfileName', stock)
        self.assertIn('pvr://channels/tv/*', stock)
        self.assertNotRegex(stock, r'pvr://channels/tv/[^*"]+@')

    def test_provider_hint_in_context_menu_is_opt_in(self):
        for node in ET.parse(ROOT / '1080i/IncludesContextMenu.xml').iter('control'):
            if 'Trakt' in (node.findtext('label') or ''):
                self.assertIn('Skin.HasSetting(KM_EnableProviderActions)', node.findtext('visible') or '')

    def test_reference_checker_reports_missing_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '1080i').mkdir()
            (root / 'media').mkdir()
            (root / 'language/resource.language.en_gb').mkdir(parents=True)
            (root / 'language/resource.language.en_gb/strings.po').write_text('msgctxt "#31000"\nmsgid "Ok"\n')
            entry = b'ok.png'.ljust(256, b'\0') + struct.pack('<II', 0, 0)
            (root / 'media/Textures.xbt').write_bytes(b'XBTF2' + struct.pack('<I', 1) + entry)
            (root / '1080i/Font.xml').write_text('<fonts><fontset id="Default"><font><name>Reg30</name></font></fontset></fonts>')
            (root / '1080i/Custom_1150_Ok.xml').write_text('<window id="1150"/>')
            (root / '1080i/Home.xml').write_text(
                '<window><onload>ActivateWindow(1150)</onload><onload>ActivateWindow(1199)</onload><controls>'
                '<control type="label"><font>reg30</font><label>$LOCALIZE[31000]</label><texture>ok.png</texture></control>'
                '<control type="label"><font>Bold99</font><label>$LOCALIZE[31999] $VAR[Nope] $EXP[Gone]</label>'
                '<texture>missing.png</texture></control></controls></window>')
            errors = '\n'.join(broken_references(root))
            for expected in ('$VAR[Nope]', '$EXP[Gone]', 'string 31999', 'font Bold99', 'window 1199', 'missing.png'):
                self.assertIn(expected, errors)
            self.assertEqual(len(broken_references(root)), 6)
            self.assertNotIn('missing.png', '\n'.join(broken_references(root, ['missing.png'])))

    def test_bad_runtime_artifacts_preserve_previous_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'addon.xml').write_text('<addon id="skin.test" version="1"/>')
            (root / 'media').mkdir()
            target = root / 'dist/skin.test-1.zip'
            target.parent.mkdir()
            target.write_bytes(b'previous release')
            outside = root / 'private.txt'
            outside.write_text('private data')
            for kind in ('link', 'hidden', 'log'):
                bad = root / 'media' / {'link': 'poster.png', 'hidden': '.env', 'log': 'debug.LOG'}[kind]
                if kind == 'link':
                    bad.symlink_to(outside)
                else:
                    bad.write_text('private data')
                with patch.object(build_skin, 'ROOT', root):
                    with self.assertRaises(ValueError):
                        build()
                self.assertEqual(target.read_bytes(), b'previous release')
                bad.unlink()

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
