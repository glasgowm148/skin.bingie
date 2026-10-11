import hashlib
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
from check_skin import (RUNTIME_DIRS, broken_references, check, household_identifiers, top_level_and_terms,
                        unguarded_autoplay)
from build_skin import build
import build_skin


def pvr_hub_paths(root, livetv, addon, kids):
    """Widget paths the PVR hub include tree resolves to for one profile/setting combination."""
    atoms = {'Skin.HasSetting(KM_EnableLiveTV)': livetv,
             'System.HasAddon(script.kodi.live.tv)': addon,
             'String.IsEqual(System.ProfileName,Kids)': kids}
    includes = {n.get('name'): n for n in root.findall('include') if n.get('name')}

    def holds(condition):
        if not condition:
            return True
        for atom, value in atoms.items():
            condition = condition.replace(atom, ' %s ' % value)
        expression = condition.replace('[', ' ( ').replace(']', ' ) ').replace('!', ' not ')
        expression = expression.replace('+', ' and ').replace('|', ' or ')
        if not set(expression.split()) <= {'True', 'False', 'not', 'and', 'or', '(', ')'}:
            raise AssertionError('unknown condition ' + condition)
        return eval(expression)  # Kodi precedence (! > + > |) matches Python's not/and/or

    def walk(node):
        paths = []
        for child in node.findall('include'):
            if not holds(child.get('condition')):
                continue
            if child.get('content'):
                paths += [p.get('value') for p in child.findall('param')
                          if p.get('name') == 'widgetPath' and p.get('value')]
            else:
                paths += walk(includes[child.text.strip()])
        return paths

    return walk(includes['bingie_items_pvr'])


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

    def test_experience_options_reload_only_on_request_outside_playback(self):
        root = ET.parse(ROOT / '1080i/Custom_1171_ExperienceSettings.xml').getroot()
        reloads = [c for c in root.iter('control') if c.findtext('onclick', '') == 'ReloadSkin()']
        self.assertEqual(len(reloads), 1)
        self.assertEqual(reloads[0].findtext('enable'), '!Player.HasMedia')
        for handler in ('onload', 'onunload'):
            self.assertFalse(any('ReloadSkin' in (n.text or '') for n in root.iter(handler)))
        self.assertTrue(any('reload' in (n.findtext('label') or '').lower()
                            for n in root.iter('control') if n.get('type') == 'label'))

    def test_auto_previews_never_replace_user_playback(self):
        self.assertEqual(unguarded_autoplay(), [])
        root = ET.parse(ROOT / '1080i/Includes.xml').getroot()
        guard = next(n for n in root.iter('expression') if n.get('name') == 'KM_PreviewMayStart').text
        self.assertIn('!Player.HasMedia', guard)
        self.assertIn('$EXP[IsPlayingUnrecognizedContent]', guard)

    def test_cast_click_from_pause_info_keeps_playback(self):
        # VideoOSD resets EnableOSDInfo before the cast helper opens 1191/1190 over playback, so the
        # fullscreen stop must exempt those helper windows itself.
        stops = [n for n in ET.parse(ROOT / '1080i/VideoFullScreen.xml').getroot().findall('onunload')
                 if 'PlayerControl(Stop)' in (n.text or '')]
        self.assertTrue(stops)
        for node in stops:
            terms = [t.strip() for t in node.get('condition').split('+')]
            self.assertNotIn('|', node.get('condition'))
            for window in ('1190', '1191'):
                self.assertIn('!Window.Next(%s)' % window, terms)

    def test_preview_guard_must_be_anded_at_top_level(self):
        alarm = 'AlarmClock(preview_delay,PlayMedia(x),00:03,silent)'
        cases = {'A + $EXP[KM_PreviewMayStart]': False,
                 '[A | B] + $EXP[KM_PreviewMayStart]': False,
                 'A | B + $EXP[KM_PreviewMayStart]': True,
                 '[A + $EXP[KM_PreviewMayStart]] | B': True,
                 '[A + $EXP[KM_PreviewMayStart]]': False,
                 'A + !$EXP[KM_PreviewMayStart]': True,
                 'A + $EXP[KM_PreviewMayStartX]': True}
        for condition, unguarded in cases.items():
            with tempfile.TemporaryDirectory() as folder:
                (Path(folder) / 'View.xml').write_text(
                    '<window><onfocus condition="%s">%s</onfocus></window>' % (condition, alarm))
                self.assertEqual(bool(unguarded_autoplay(Path(folder))), unguarded, condition)

    def test_home_menu_rebuild_waits_for_idle_player(self):
        # Skin Shortcuts may rebuild and reload the skin; Home must not start that over playback.
        builds = [n for n in ET.parse(ROOT / '1080i/Home.xml').getroot().findall('onload')
                  if 'script.skinshortcuts,type=buildxml' in (n.text or '')]
        self.assertEqual(len(builds), 1)
        terms = top_level_and_terms(builds[0].get('condition') or '')
        self.assertIn('!Player.HasMedia', terms)
        self.assertIn('!System.HasAlarm(KodiNavigationSwitch)', terms)

    def test_recovery_prompt_stays_closed_after_back(self):
        visible = ET.parse(ROOT / '1080i/Custom_1170_StreamRecovery.xml').getroot().findtext('visible')
        self.assertIn('!String.IsEqual(Window(Home).Property(pov_recovery_dismissed),'
                      'Window(Home).Property(pov_recovery_session))', visible)

    def test_pvr_hub_defaults_to_stock_channel_rows(self):
        root = ET.parse(ROOT / '1080i/IncludesHomeWidgets.xml').getroot()
        wrapper = next(n for n in root.findall('include') if n.get('name') == 'bingie_items_pvr')
        branches = wrapper.findall('include')
        self.assertIn('Skin.HasSetting(KM_EnableLiveTV)', branches[0].get('condition'))
        self.assertEqual(branches[0].text, 'bingie_items_pvr_Experience')
        stock = ET.tostring(next(n for n in root.findall('include') if n.get('name') == 'bingie_items_pvr_Stock')).decode()
        self.assertNotIn('System.ProfileName', stock)
        self.assertIn('pvr://channels/tv/*', stock)
        self.assertNotRegex(stock, r'pvr://channels/tv/[^*"]+@')
        for livetv in (True, False):
            for addon in (True, False):
                adult = pvr_hub_paths(root, livetv, addon, kids=False)
                self.assertTrue(adult)
                if not (livetv and addon):
                    self.assertIn('pvr://channels/tv/*', adult)

    def test_kids_pvr_hub_never_lists_all_channels(self):
        root = ET.parse(ROOT / '1080i/IncludesHomeWidgets.xml').getroot()
        for livetv in (True, False):
            for addon in (True, False):
                paths = pvr_hub_paths(root, livetv, addon, kids=True)
                for path in paths:
                    self.assertFalse(path.startswith('pvr://channels/tv/*'), (livetv, addon, path))
                    self.assertNotIn('lastplayed', path)
                    self.assertNotIn('recordings', path)

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

    def test_household_scan_covers_all_runtime_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'shortcuts').mkdir()
            (root / 'extras').mkdir()
            (root / 'tests').mkdir()
            (root / 'shortcuts/mainmenu.DATA.xml').write_text('<path>smb://192.168.1.20/films</path>')
            (root / 'extras/clean.xsp').write_text('<smartplaylist/>')
            (root / 'tests/fixture.xml').write_text('192.168.1.20')
            for folder_name in ('playlists', 'resources', 'fonts', 'media'):
                (root / folder_name).mkdir()
            (root / 'playlists/kids.m3u').write_text('http://10.0.0.5/stream')
            (root / 'resources/notes.md').write_text('markglasgow@example')
            (root / 'fonts/clean.ttf').write_bytes(b'\0\x01192.168.1.20')
            (root / 'media/clean.png').write_bytes(b'\x89PNG\0')
            self.assertEqual(household_identifiers(root), [
                'playlists/kids.m3u', 'resources/notes.md', 'shortcuts/mainmenu.DATA.xml'])
            self.assertTrue(set(build_skin.RUNTIME) <= set(RUNTIME_DIRS))

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

    def test_changed_tree_never_overwrites_same_version_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'addon.xml').write_text('<addon id="skin.test" version="1"/>')
            (root / 'media').mkdir()
            (root / 'media/a.txt').write_text('first')
            with patch.object(build_skin, 'ROOT', root):
                released = build().read_bytes()
                self.assertEqual(build().read_bytes(), released)
                (root / 'media/a.txt').write_text('second')
                with self.assertRaisesRegex(ValueError, 'version'):
                    build()
            self.assertEqual((root / 'dist/skin.test-1.zip').read_bytes(), released)
            self.assertIn(hashlib.sha256(released).hexdigest(), (root / 'dist/skin.test-1.zip.sha256').read_text())

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
