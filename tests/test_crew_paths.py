"""Resolve shipped crew routes with representative Kodi list-item metadata."""
from pathlib import Path
import re
import unittest
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def crew_path(role, menu, dbtype, properties):
    variables = {v.get('name'): v for v in ET.parse(ROOT / '1080i/IncludesPaths.xml').getroot()}

    def holds(condition):
        atoms = {
            'String.IsEqual(Container(8999).ListItem.Label,$LOCALIZE[%s])' % m: menu == m
            for m in (20339, 31530, 31488)
        }
        atoms.update({'String.IsEqual(ListItem.DBType,%s)' % t: dbtype == t
                      for t in ('movie', 'tvshow', 'episode')})
        for r, count in [('Director', 5), ('Creator', 3), ('Writer', 5)]:
            for i in range(1, count + 1):
                for field in ('TMDb_ID', 'job'):
                    key = '%s.%s.%s' % (r, i, field)
                    label = 'Container(17195).ListItem.Property(%s)' % key
                    atoms['String.IsEmpty(%s)' % label] = not properties.get(key, '')
                    atoms['String.IsEqual(%s,Screenplay)' % label] = properties.get(key) == 'Screenplay'
        for atom, value in atoms.items():
            condition = condition.replace(atom, ' %s ' % value)
        expression = condition.replace('[', ' ( ').replace(']', ' ) ').replace('!', ' not ')
        expression = expression.replace('+', ' and ').replace('|', ' or ')
        if not set(expression.split()) <= {'True', 'False', 'not', 'and', 'or', '(', ')'}:
            raise AssertionError('Unknown condition: ' + condition)
        return eval(expression)

    def resolve(name):
        value = next((v.text or '' for v in variables[name] if holds(v.get('condition', 'True'))), '')
        value = re.sub(r'\$VAR\[([^,\]]+)(?:,([^,]*),([^\]]*))?\]',
                       lambda m: ((m[2] or '') + resolve(m[1]) + (m[3] or '')) if resolve(m[1]) else '', value)
        value = re.sub(r'\$INFO\[Container\(17195\).ListItem.Property\(([^)]+)\),([^,]*),([^\]]*)\]',
                       lambda m: m[2] + properties[m[1]] + m[3] if properties.get(m[1]) else '', value)
        return value.replace('$INFO[Window(Home).Property(TMDbBingieHelper.Widgets.Reload)]', '')

    return resolve('Path_From' + role)


class CrewPathTests(unittest.TestCase):
    CASES = [('Director', 20339, ('movie', 'episode'), 5),
             ('Creator', 31530, ('tvshow', 'episode'), 3),
             ('Writer', 31488, ('movie',), 5)]

    def test_missing_metadata_never_requests_an_empty_person(self):
        for role, menu, types, _ in self.CASES:
            for kind in types:
                with self.subTest(role=role, kind=kind):
                    self.assertEqual(crew_path(role, menu, kind, {}), '')

    def test_each_supported_person_slot_uses_id_without_empty_query(self):
        for role, menu, types, count in self.CASES:
            for index in range(1, count + 1):
                props = {f'{role}.{index}.TMDb_ID': '123', f'{role}.{index}.job': 'Screenplay'}
                for kind in types:
                    with self.subTest(role=role, index=index, kind=kind):
                        query = parse_qs(urlsplit(crew_path(role, menu, kind, props)).query, keep_blank_values=True)
                        self.assertEqual(query['tmdb_id'], ['123'])
                        self.assertNotIn('query', query)
                        self.assertEqual(query['filter_value'], [role])

    def test_wrong_menu_or_media_type_does_not_request_crew(self):
        for role, menu, types, _ in self.CASES:
            props = {f'{role}.1.TMDb_ID': '123'}
            for kind in ('movie', 'tvshow', 'episode', 'season', ''):
                self.assertEqual(crew_path(role, 99999, kind, props), '')
                if kind not in types:
                    self.assertEqual(crew_path(role, menu, kind, props), '')

    def test_writer_prefers_screenplay_then_first_writer(self):
        props = {'Writer.1.TMDb_ID': '12', 'Writer.2.TMDb_ID': '34', 'Writer.2.job': 'Screenplay'}
        self.assertIn('tmdb_id=34&', crew_path('Writer', 31488, 'movie', props))
        props['Writer.2.job'] = 'Novel'
        self.assertIn('tmdb_id=12&', crew_path('Writer', 31488, 'movie', props))
        del props['Writer.1.TMDb_ID']
        self.assertEqual(crew_path('Writer', 31488, 'movie', props), '')
