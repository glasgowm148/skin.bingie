import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import upstream_report

ENV = dict(os.environ, GIT_AUTHOR_NAME='Upstream', GIT_AUTHOR_EMAIL='up@example.invalid',
           GIT_COMMITTER_NAME='Upstream', GIT_COMMITTER_EMAIL='up@example.invalid',
           GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)


@unittest.skipUnless(shutil.which('git'), 'git is required')
class UpstreamReportTests(unittest.TestCase):
    """Synthetic history: base -> fork edits Home.xml; upstream edits Home.xml and Font.xml."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.repo))
        self.git('init', '-q')
        self.git('symbolic-ref', 'HEAD', 'refs/heads/main')
        self.commit({'1080i/Home.xml': 'base', '1080i/Font.xml': 'base', 'addon.xml': 'base'}, 'base')
        self.base = self.git('rev-parse', 'HEAD')
        self.commit({'1080i/Home.xml': 'fork'}, 'fork: home')
        self.git('checkout', '-q', '-b', 'upstream-omega', self.base)
        self.commit({'1080i/Home.xml': 'upstream'}, 'upstream: home')
        self.commit({'1080i/Font.xml': 'upstream'}, 'upstream: font')
        self.git('checkout', '-q', 'main')
        # Mimic a remote-tracking ref so the report runs fully offline.
        self.git('update-ref', 'refs/remotes/matke/omega', 'upstream-omega')
        (self.repo / 'UPSTREAM_BASE').write_text('# comment\nmatke/omega %s\n' % self.base)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), '-c', 'commit.gpgsign=false'] + list(args), env=ENV,
                              check=True, stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()

    def commit(self, files, message):
        for name, text in files.items():
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / name).write_text(text + '\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', message)

    def test_lists_pending_commits_and_flags_fork_overlap(self):
        [entry] = upstream_report.report(self.repo)
        self.assertEqual(entry['warnings'], [])
        self.assertEqual(entry['fork_modified'], ['1080i/Home.xml'])
        self.assertEqual([c['subject'] for c in entry['commits']], ['upstream: home', 'upstream: font'])
        self.assertEqual([c['overlap'] for c in entry['commits']], [['1080i/Home.xml'], []])
        self.assertEqual(entry['upstream_changed'], ['1080i/Font.xml', '1080i/Home.xml'])
        text = upstream_report.format_report([entry])
        self.assertIn('REVIEW 1080i/Home.xml', text)
        self.assertIn('clean  1080i/Font.xml', text)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(upstream_report.main(['--repo', str(self.repo), '--fail-on-new']), 1)

    def test_merged_upstream_with_updated_base_is_clean(self):
        self.git('merge', '-q', '-X', 'ours', '--no-edit', 'matke/omega')
        tip = self.git('rev-parse', 'matke/omega')
        (self.repo / 'UPSTREAM_BASE').write_text('matke/omega %s\n' % tip)
        [entry] = upstream_report.report(self.repo)
        self.assertEqual((entry['commits'], entry['warnings']), ([], []))
        self.assertEqual(entry['fork_modified'], ['1080i/Home.xml'])  # fork kept its Home.xml
        with redirect_stdout(io.StringIO()):
            self.assertEqual(upstream_report.main(['--repo', str(self.repo), '--fail-on-new']), 0)

    def test_stale_or_missing_bases_warn(self):
        (self.repo / 'UPSTREAM_BASE').write_text('matke/omega %s\nbigmoco/omega %s\n'
                                                 % (self.git('rev-parse', 'matke/omega'), self.base))
        stale, missing = upstream_report.report(self.repo)
        self.assertIn('UPSTREAM_BASE is stale', stale['warnings'][0])
        self.assertIn('missing ref/commit: bigmoco/omega', missing['warnings'][0])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(upstream_report.main(['--repo', str(self.repo)]), 2)

    def test_repository_records_a_merged_base_for_each_tracked_ref(self):
        bases = upstream_report.read_bases(ROOT / 'UPSTREAM_BASE')
        self.assertEqual([ref for ref, _ in bases], ['matke/omega', 'upstream/omega'])
        self.assertTrue(all(len(sha) == 40 for _, sha in bases))


if __name__ == '__main__':
    unittest.main()
