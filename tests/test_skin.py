import hashlib
import shutil
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
from check_skin import (CONDITION_ALLOWED, RUNTIME_DIRS, bad_condition_functions, balanced, broken_references, check,
                        household_identifiers, raw_audio_flags, removed_infolabels, top_level_and_terms, unbalanced_expressions, unguarded_autoplay, unguarded_playback_actions)
from build_skin import build
import build_skin


def pvr_hub_paths(root, livetv, addon, kids):
    """Widget paths the PVR hub include tree resolves to for one profile/setting combination."""
    atoms = {'Skin.HasSetting(KM_EnableLiveTV)': livetv,
             'System.HasAddon(script.kodi.live.tv)': addon,
             'Skin.HasSetting(KM_FamilyMode)': kids,
             'Skin.HasSetting(KM_CustomPVRRows)': livetv,
             'Skin.HasSetting(KM_PVRShowRecent)': True,
             'Skin.HasSetting(KM_FamilyGuideAllowed)': False,
             '$EXP[KM_HasNavigation]': addon,
             **{'String.IsEmpty(Skin.String(KM_PVRRow%dPath))' % i: False for i in range(1,4)}}
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

    paths = walk(includes['bingie_items_pvr'])
    for index in range(1, 4):
        paths = [p.replace('$INFO[Skin.String(KM_PVRRow%dPath)]' % index,
                           'pvr://channels/tv/Example%d@7/' % index) for p in paths]
    return paths


class SkinTests(unittest.TestCase):
    def test_release_documentation_matches_the_packaged_version(self):
        version = ET.parse(ROOT / 'addon.xml').getroot().get('version')
        readme = (ROOT / 'README.md').read_text()
        self.assertIn('**Version %s beta**' % version, readme)
        self.assertIn('`skin.bingie-%s.zip`' % version, readme)
        self.assertIn('/releases/tag/v' + version, readme)

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
        self.assertIn('$EXP[KM_HasNavigation]', nodes[0].get('condition'))
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
            if any(action == 'Skin.ToggleSetting(%s)' % key for key in ('KM_EnableProviderActions', 'KM_EnableLiveTV', 'KM_EnableDirectSwitch')):
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
        expressions = {n.get('name'): n.text for n in root.iter('expression')}
        self.assertEqual(top_level_and_terms(expressions['KM_PreviewPlaying']), [
            '$EXP[IsPlayingUnrecognizedContent]', '!String.IsEmpty(Window(Home).Property(KM_PreviewActive))'])
        self.assertEqual(expressions['KM_PreviewMayStart'].replace(' ', ''), '!Player.HasMedia|$EXP[KM_PreviewPlaying]')

    def test_preview_marker_is_set_only_by_preview_arming_and_cleared_by_fullscreen(self):
        # Only skin-armed previews carry KM_PreviewActive; anything the user watches goes fullscreen,
        # which clears it, so focus changes can no longer stop user-started streams.
        clears = [n for n in ET.parse(ROOT / '1080i/VideoFullScreen.xml').getroot().findall('onload')
                  if (n.text or '').strip() == 'ClearProperty(KM_PreviewActive,Home)']
        self.assertEqual(len(clears), 1)
        self.assertIsNone(clears[0].get('condition'))
        root = ET.parse(ROOT / '1080i/IncludesFunctions.xml').getroot()
        arming = [n for n in root.iter() if n.tag in ('include', 'control')
                  and any('AlarmClock(preview_delay' in (h.text or '') for h in n.findall('onfocus'))]
        self.assertEqual(len(arming), 3)
        for node in arming:
            handlers = node.findall('onfocus')
            marks = [h for h in handlers if (h.text or '').strip() == 'SetProperty(KM_PreviewActive,1,Home)']
            self.assertEqual(len(marks), 1)
            self.assertEqual(marks[0].get('condition'), '$EXP[KM_PreviewMayStart]')
            last_arm = max(i for i, h in enumerate(handlers) if 'AlarmClock(preview_delay' in (h.text or ''))
            self.assertGreater(handlers.index(marks[0]), last_arm)
        for path in sorted((ROOT / '1080i').glob('*.xml')):
            for node in ET.parse(path).iter():
                if 'SetProperty(KM_PreviewActive' in (node.text or ''):
                    self.assertEqual(path.name, 'IncludesFunctions.xml')

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

    def test_automatic_stop_and_play_require_guards(self):
        stop, play = 'PlayerControl(Stop)', 'PlayMedia(x,1)'
        cases = [  # (file, xml, flagged)
            ('View.xml', '<onunfocus condition="$EXP[IsPlayingUnrecognizedContent] + A">%s</onunfocus>' % stop, True),
            ('View.xml', '<onunfocus condition="$EXP[KM_PreviewPlaying] + A">%s</onunfocus>' % stop, False),
            ('View.xml', '<onunfocus condition="$EXP[KM_PreviewPlaying] | A">%s</onunfocus>' % stop, True),
            ('View.xml', '<onfocus condition="!$EXP[KM_PreviewPlaying]">%s</onfocus>' % stop, True),
            ('View.xml', '<onback condition="Player.HasVideo">Stop</onback>', True),
            ('View.xml', '<onunload>AlarmClock(StopPlayback,PlayerControl(Stop),00:00,silent)</onunload>', True),
            ('View.xml', '<onunload>CancelAlarm(StopPlayback,silent)</onunload>', False),
            ('View.xml', '<onclick>%s</onclick>' % stop, False),
            ('View.xml', '<onload condition="A">%s</onload>' % play, True),
            ('View.xml', '<onload condition="A + !Player.HasMedia">%s</onload>' % play, False),
            ('View.xml', '<onfocus>AlarmClock(p,RunScript(script.bingie.helper,action=playtrailer),00:03)</onfocus>', True),
            ('VideoFullScreen.xml', '<onunload condition="Skin.HasSetting(ForceVideoPlaybackStop) + A">%s</onunload>' % stop, False),
            ('VideoFullScreen.xml', '<onunload condition="A">%s</onunload>' % stop, True),
            ('Other.xml', '<onunload condition="Skin.HasSetting(ForceVideoPlaybackStop)">%s</onunload>' % stop, True),
            ('Includes.xml', '<control id="70011"><onunfocus condition="$EXP[KM_UnrecognizedVideo]">Stop</onunfocus></control>', False),
            ('Includes.xml', '<control id="70011"><onunfocus condition="Player.HasVideo">Stop</onunfocus></control>', True),
            ('Includes.xml', '<control id="70012"><onunfocus condition="$EXP[KM_UnrecognizedVideo]">Stop</onunfocus></control>', True),
        ]
        for name, xml, flagged in cases:
            with tempfile.TemporaryDirectory() as folder:
                (Path(folder) / name).write_text('<window>%s</window>' % xml)
                self.assertEqual(bool(unguarded_playback_actions(Path(folder))), flagged, (name, xml))

    def test_unguarded_stop_paths_fail_validation(self):
        self.assertEqual(unguarded_playback_actions(), [])
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / '1080i'
            shutil.copytree(ROOT / '1080i', copy)
            for path in copy.glob('*.xml'):
                text = path.read_text(encoding='utf-8')
                reverted = text.replace('$EXP[KM_PreviewPlaying]', '$EXP[IsPlayingUnrecognizedContent]')
                reverted = reverted.replace('"$EXP[KM_UnrecognizedVideo]">Stop<', '"Player.HasVideo">Stop<')
                reverted = reverted.replace(' + !Player.HasMedia">PlayMedia(', '">PlayMedia(')
                path.write_text(reverted, encoding='utf-8')
            found = unguarded_playback_actions(copy)
        self.assertEqual(len(found), 19, found)  # the stop/play paths guarded in 2.0.2.3

    def test_recovery_prompt_stays_closed_after_back(self):
        visible = ET.parse(ROOT / '1080i/Custom_1170_StreamRecovery.xml').getroot().findtext('visible')
        self.assertIn('!String.IsEqual(Window(Home).Property(pov_recovery_dismissed),'
                      'Window(Home).Property(pov_recovery_session))', visible)

    def test_pvr_hub_defaults_to_stock_channel_rows(self):
        root = ET.parse(ROOT / '1080i/IncludesHomeWidgets.xml').getroot()
        wrapper = next(n for n in root.findall('include') if n.get('name') == 'bingie_items_pvr')
        branches = wrapper.findall('include')
        self.assertIn('Skin.HasSetting(KM_CustomPVRRows)', branches[0].get('condition'))
        self.assertEqual(branches[0].text, 'bingie_items_pvr_Experience')
        stock = ET.tostring(next(n for n in root.findall('include') if n.get('name') == 'bingie_items_pvr_Stock')).decode()
        self.assertNotIn('System.ProfileName', stock)
        self.assertIn('pvr://channels/tv/*', stock)
        self.assertNotRegex(stock, r'pvr://channels/tv/[^*"]+@')
        for livetv in (True, False):
            for addon in (True, False):
                adult = pvr_hub_paths(root, livetv, addon, kids=False)
                self.assertTrue(adult)
                if not livetv:
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

    def test_balance_check_flags_malformed_conditions_and_actions(self):
        self.assertTrue(balanced('[A | String.IsEmpty(B)] + $EXP[C]'))
        for text in ('String.IsEmpty(Window(Home).Property(X)', '[A + B(C))] | D', 'AlarmClock(a,b,00:01],silent)', ')('):
            self.assertFalse(balanced(text), text)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Home.xml'
            path.write_text(
                '<window><onload condition="!String.IsEmpty(Window(Home).Property(X)">Close</onload><controls>'
                '<control type="button"><visible>[A | B</visible><onclick>Close</onclick>'
                '<label>$INFO[ListItem.Year,(,]</label></control></controls></window>')
            found = unbalanced_expressions(path)
            self.assertEqual(len(found), 3)
            self.assertIn('<condition>', found[0])
            self.assertIn('<visible>', found[1])
            allowed = {('Home.xml', '$INFO[ListItem.Year,(,]')}
            self.assertEqual(len(unbalanced_expressions(path, allowed)), 2)

    def test_condition_check_flags_typos_and_wrong_argument_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Home.xml'
            path.write_text(
                '<window><!-- String.Bogus(x) in a comment is ignored -->'
                '<onload condition="String.IsEqual(Window(Home).Property(ListItem.DBTYPE,tvshow))">Close</onload>'
                '<visible>String.EmdsWith(Player.FileNameAndPath,.iso) | Skin.String(X)</visible>'
                '<visible>String.Contains(Window(Home).Property(P,X)) + string.isempty(ListItem.Label)</visible>'
                '<visible>String.IsEqual(Window(Home).Property(ListItem.DBTYPE),tvshow) + Integer.IsGreater(A,1)'
                ' + String.StartsWith(ListItem.Path,$INFO[X,a,b]) + String.EndsWith(A,[B,C])</visible>'
                '<visible>String.IsEqual(Container(5050).ListItem.Path)</visible></window>')
            found = bad_condition_functions(path)
            self.assertEqual(len(found), 4, found)
            self.assertIn('Home.xml:1: String.IsEqual takes 2 arguments, got 1', found[0])
            self.assertIn('unknown function String.EmdsWith', found[1])
            self.assertIn('String.Contains takes 2 arguments, got 1', found[2])
            self.assertIn('String.IsEqual(Container(5050).ListItem.Path)', found[3])
            allowed = {('Home.xml', 'String.IsEqual(Container(5050).ListItem.Path)')}
            self.assertEqual(len(bad_condition_functions(path, allowed)), 3)
        # No one-argument comparisons are left in the skin (the dead Play-next folder branch is gone).
        self.assertEqual(CONDITION_ALLOWED, set())
        for path in sorted((ROOT / '1080i').glob('*.xml')):
            self.assertEqual(bad_condition_functions(path), [], path.name)

    def test_removed_kodi22_infolabels_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Home.xml'
            path.write_text(
                '<window><!-- Player.Cutlist in a comment is ignored -->\n'
                '<info>Player.Cutlist</info><info>Player.EditList</info>\n'
                '<label>$INFO[slideshow.exifsoftware]</label><info>VideoPlayer.Cutlistx</info></window>')
            found = removed_infolabels(path)
            self.assertEqual(found, ['Home.xml:2: Player.Cutlist was removed in Kodi 22',
                                     'Home.xml:3: slideshow.exifsoftware was removed in Kodi 22'])
        for path in sorted((ROOT / '1080i').glob('*.xml')):
            self.assertEqual(removed_infolabels(path), [], path.name)

    def test_audio_flag_textures_go_through_the_kodi22_mapping(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Flags.xml'
            path.write_text('<window>\n<texture>$VAR[p]$INFO[ListItem.AudioCodec,/audio/,.png]</texture>\n'
                            '<texture>$VAR[p]$VAR[ListItemAudioFlagVar,/audio/,.png]</texture>\n'
                            '<label>$INFO[ListItem.AudioCodec]</label></window>')
            self.assertEqual(raw_audio_flags(path), ['Flags.xml:2: audio flag texture uses the raw codec name; '
                                                     'use ListItemAudioFlagVar or VideoPlayerAudioFlagVar'])
        for path in sorted((ROOT / '1080i').glob('*.xml')):
            self.assertEqual(raw_audio_flags(path), [], path.name)

    def test_suggestion_titles_are_escaped_for_skin_setstring(self):
        # A title with a comma ("Love, Death & Robots", a remembered "the office, us") would
        # otherwise be cut at the comma by Kodi's builtin parameter splitting.
        text = (ROOT / '1080i/Custom_1109_BingieSearch.xml').read_text(encoding='utf-8')
        self.assertNotIn('Skin.SetString(CustomSearchTerm,$VAR[', text)
        self.assertNotIn('Skin.SetString(CustomSearchTerm,$INFO[', text)
        self.assertIn('Skin.SetString(CustomSearchTerm,$ESCVAR[BingieSuggestionTitle])', text)
        keys = (ROOT / '1080i/IncludesBingieSearch.xml').read_text(encoding='utf-8')
        self.assertNotIn('Skin.SetString(CustomSearchTerm,$INFO[', keys)

    def test_leftover_search_term_is_cleared_before_home(self):
        # The search widgets build their path from the term; a term saved when Kodi quit
        # would be opened as a directory while Home loads, before its own reset runs.
        root = ET.parse(ROOT / '1080i/Startup.xml').getroot()
        loads = [(e.get('condition') or '', e.text) for e in root.findall('onload')]
        reset = loads.index(('!String.IsEmpty(Skin.String(CustomSearchTerm))', 'Skin.Reset(CustomSearchTerm)'))
        replace = next(i for i, (_c, text) in enumerate(loads) if text.startswith('ReplaceWindow('))
        self.assertLess(reset, replace)

    def test_voice_search_hint_is_opt_in(self):
        # The hint is only true where a helper app makes the mic button search in Kodi, which the
        # skin cannot detect: it stays behind a setting that is off by default, on Android only.
        includes = (ROOT / '1080i/IncludesBingieSearch.xml').read_text(encoding='utf-8')
        self.assertIn('<expression name="VoiceSearchHintVisible">Skin.HasSetting(ShowVoiceSearchHint) + '
                      'System.Platform.Android + ', includes)
        window = (ROOT / '1080i/Custom_1109_BingieSearch.xml').read_text(encoding='utf-8')
        self.assertEqual(window.count('$EXP[VoiceSearchHintVisible]'), 1)
        self.assertTrue((ROOT / 'extras/media/voice_mic.png').is_file())
        for path in sorted((ROOT / '1080i').glob('*.xml')):
            if path.name != 'IncludesSkinSettings.xml':
                self.assertNotIn('Skin.SetBool(ShowVoiceSearchHint', path.read_text(encoding='utf-8'), path.name)

    def test_voice_button_is_optional_reachable_and_preserves_typed_search(self):
        root = ET.parse(ROOT / '1080i/Custom_1109_BingieSearch.xml').getroot()
        button = next(n for n in root.iter('control') if n.get('id') == '1009')
        self.assertIn('$EXP[KM_VoiceAvailable]', button.findtext('visible'))
        self.assertEqual(button.findtext('enable'), '!Player.HasMedia')
        self.assertEqual(button.findtext('onclick'), 'RunScript(script.bingie.companion,voice)')
        self.assertEqual(button.findtext('ondown'), '101')
        self.assertTrue(any(n.text == 'SetFocus(1009)' for n in root.iter('onup')))
        self.assertFalse(any('CustomSearchTerm' in (n.text or '') for n in button.iter('onclick')))
        expressions = ET.parse(ROOT / '1080i/IncludesExperience.xml').getroot()
        condition = next(n.text for n in expressions.findall('expression') if n.get('name') == 'KM_VoiceAvailable')
        self.assertEqual(top_level_and_terms(condition), ['System.Platform.Android',
                         'Skin.HasSetting(KM_EnableVoiceSearch)',
                         'System.AddonIsEnabled(script.bingie.companion)'])

    def test_existing_navigation_coordinator_keeps_precedence(self):
        root = ET.parse(ROOT / '1080i/IncludesExperience.xml').getroot()
        navigation = next(n for n in root.findall('variable') if n.get('name') == 'KM_NavigationAddon')
        self.assertEqual([n.text for n in navigation.findall('value')],
                         ['script.kodi.live.tv', 'script.bingie.companion'])

    def test_family_navigation_requires_manager_and_has_no_unfiltered_provider_fallback(self):
        root = ET.parse(ROOT / '1080i/View_525_Bingie_Episodes.xml').getroot()
        values = next(n for n in root.findall('variable') if n.get('name') == 'View525SeasonsContent').findall('value')
        family = next(n for n in values if 'mode=family' in (n.text or ''))
        self.assertIn('System.AddonIsEnabled(service.kodi.addonadmin)', family.get('condition'))
        self.assertIn('Skin.HasSetting(KM_FamilyMode)', family.get('condition'))
        direct = next(n for n in values if (n.text or '').startswith('plugin://plugin.video.pov/'))
        self.assertIn('!Skin.HasSetting(KM_FamilyMode)', direct.get('condition'))

    def test_community_skin_has_no_implicit_household_profile_or_group_names(self):
        for name in ('IncludesHomeWidgets.xml', 'View_525_Bingie_Episodes.xml'):
            text = (ROOT / '1080i' / name).read_text()
            for term in ('System.ProfileName,Kids', 'Little Ones', 'Cartoons@', 'Sky Sports', 'TNT Sports'):
                self.assertNotIn(term, text, name)

    def test_kodi_manager_search_history_is_optional(self):
        # Every use of Kodi Manager's plugin sits behind SearchHistoryEnabled (installed, enabled
        # and not switched off), so the stock skin behaves as before without it.
        uses = []
        for path in sorted((ROOT / '1080i').glob('*.xml')):
            for line in path.read_text(encoding='utf-8').splitlines():
                if 'plugin://service.kodi.addonadmin/?mode=search_history' in line:
                    uses.append((path.name, line.strip()))
        # Listing (suggestions), and recording on moving into the results or picking a
        # suggestion; never on window unload, which also runs while Kodi quits.
        self.assertEqual(len(uses), 4, uses)
        for name, line in uses:
            self.assertTrue('$EXP[SearchHistoryRecordable]' in line or '$EXP[SearchHistoryEnabled]' in line, (name, line))
        text = (ROOT / '1080i/IncludesBingieSearch.xml').read_text(encoding='utf-8')
        self.assertIn('<expression name="SearchHistoryEnabled">System.AddonIsEnabled(service.kodi.addonadmin) + '
                      '!Skin.HasSetting(DisableSearchHistory)</expression>', text)
        self.assertIn('<expression name="SearchHistoryRecordable">$EXP[SearchHistoryEnabled] + '
                      '!String.IsEmpty(Skin.String(CustomSearchTerm))</expression>', text)

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
            (root / 'resources/notes.md').write_text('fixture-user@example.invalid')
            (root / 'fonts/clean.ttf').write_bytes(b'\0\x01192.168.1.20')
            (root / 'media/clean.png').write_bytes(b'\x89PNG\0')
            self.assertEqual(household_identifiers(root), [
                'playlists/kids.m3u', 'resources/notes.md', 'shortcuts/mainmenu.DATA.xml'])
            self.assertTrue(set(build_skin.RUNTIME) <= set(RUNTIME_DIRS))

    def test_privacy_scan_is_independent_of_the_maintainers_household(self):
        for private in ('http://172.16.1.2/stream', 'smb://172.31.2.3/files',
                        'another-user@example.invalid', 'https://fixture:password@example.invalid/stream'):
            with self.subTest(private=private), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'resources').mkdir()
                (root / 'resources/notes.txt').write_text(private)
                self.assertEqual(household_identifiers(root), ['resources/notes.txt'])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'resources').mkdir()
            (root / 'resources/notes.txt').write_text('https://example.invalid/stream https://172.32.1.2/')
            self.assertEqual(household_identifiers(root), [])

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
