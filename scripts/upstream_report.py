"""Report upstream Bingie commits that are not yet in main and flag files the fork also changed.

Works offline from local remote-tracking refs (run `git fetch matke upstream` first, or pass --fetch).
For every "<ref> <commit>" in UPSTREAM_BASE it lists commits reachable from <ref> but not from main,
the files each touches, and marks files the fork modified since that recorded base as REVIEW.
It never merges, checks out or pushes.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args, check=True):
    result = subprocess.run(['git', '-C', str(repo)] + list(args), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True)
    if check and result.returncode:
        raise RuntimeError('git %s failed: %s' % (' '.join(args), result.stderr.strip()))
    return result


def lines(repo, *args):
    return [line for line in git(repo, *args).stdout.splitlines() if line]


def read_bases(path):
    """[(ref, commit)] from an UPSTREAM_BASE file; blank lines and # comments are ignored."""
    bases = []
    for number, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError('%s:%d: expected "<ref> <commit>"' % (path, number))
        bases.append((parts[0], parts[1]))
    return bases


def is_ancestor(repo, older, newer):
    return git(repo, 'merge-base', '--is-ancestor', older, newer, check=False).returncode == 0


def changed_files(repo, commit):
    """Files a commit changes relative to its first parent (or everything, for a root commit)."""
    parents = lines(repo, 'rev-list', '--parents', '-n', '1', commit)[0].split()[1:]
    if parents:
        return lines(repo, 'diff', '--no-renames', '--name-only', parents[0], commit)
    return lines(repo, 'diff-tree', '--no-commit-id', '--no-renames', '--name-only', '-r', '--root', commit)


def report(repo=ROOT, base_file=None, main='main', refs=None):
    """Structured report for each tracked upstream ref; see module docstring."""
    repo = Path(repo)
    bases = read_bases(base_file or repo / 'UPSTREAM_BASE')
    if refs:
        bases = [(ref, base) for ref, base in bases if ref in refs]
    results = []
    for ref, base in bases:
        entry = {'ref': ref, 'base': base, 'warnings': [], 'commits': [], 'fork_modified': []}
        results.append(entry)
        resolved = {}
        for name in (ref, base, main):
            found = git(repo, 'rev-parse', '--verify', '--quiet', name + '^{commit}', check=False)
            resolved[name] = found.stdout.strip()
        missing = [name for name, sha in resolved.items() if not sha]
        if missing:
            entry['warnings'].append('missing ref/commit: %s (fetch the remote first)' % ', '.join(missing))
            continue
        entry['tip'] = resolved[ref]
        if not is_ancestor(repo, base, main):
            entry['warnings'].append('recorded base is not merged into %s; UPSTREAM_BASE is stale' % main)
        if not is_ancestor(repo, base, ref):
            entry['warnings'].append('recorded base is not an ancestor of %s; upstream history was rewritten' % ref)
        fork = set(lines(repo, 'diff', '--no-renames', '--name-only', base, main))
        entry['fork_modified'] = sorted(fork)
        log = lines(repo, 'log', '--reverse', '--date=short', '--format=%H%x09%ad%x09%an%x09%s',
                    ref, '^' + main, '^' + base)
        for row in log:
            sha, date, author, subject = row.split('\t', 3)
            files = changed_files(repo, sha)
            entry['commits'].append({'sha': sha, 'date': date, 'author': author, 'subject': subject,
                                     'files': files, 'overlap': sorted(set(files) & fork)})
        if entry['commits']:
            entry['upstream_changed'] = sorted(set(lines(repo, 'diff', '--no-renames', '--name-only',
                                                          base, ref)))
    return results


def format_report(results, main='main'):
    out = []
    for entry in results:
        out.append('%s  base %s  tip %s' % (entry['ref'], entry['base'][:7], entry.get('tip', '?')[:7]))
        out += ['  WARNING: ' + warning for warning in entry['warnings']]
        if 'tip' not in entry:
            continue
        out.append('  files the fork changed since base: %d' % len(entry['fork_modified']))
        if not entry['commits']:
            out.append('  no upstream commits missing from %s' % main)
            continue
        overlap = sorted({f for commit in entry['commits'] for f in commit['overlap']})
        out.append('  %d upstream commit(s) not in %s; %d file(s) changed, %d also changed by the fork'
                   % (len(entry['commits']), main, len(entry['upstream_changed']), len(overlap)))
        for commit in entry['commits']:
            out.append('  %s %s %s: %s' % (commit['sha'][:7], commit['date'], commit['author'], commit['subject']))
            for name in commit['files']:
                out.append('      %s %s' % ('REVIEW' if name in commit['overlap'] else 'clean ', name))
        if overlap:
            out.append('  Review against fork changes: ' + ', '.join(overlap))
    return '\n'.join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--repo', default=str(ROOT))
    parser.add_argument('--base-file', help='default: <repo>/UPSTREAM_BASE')
    parser.add_argument('--main', default='main', help='integration branch (default: main)')
    parser.add_argument('--ref', action='append', help='only report this tracked ref (repeatable)')
    parser.add_argument('--fetch', action='store_true', help='git fetch each ref\'s remote first; failures only warn')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--fail-on-new', action='store_true', help='exit 1 when upstream commits are pending')
    args = parser.parse_args(argv)
    if args.fetch:
        bases = read_bases(args.base_file or Path(args.repo) / 'UPSTREAM_BASE')
        for remote in sorted({ref.split('/', 1)[0] for ref, _ in bases if '/' in ref}):
            fetched = git(args.repo, 'fetch', '--quiet', remote, check=False)
            if fetched.returncode:
                print('warning: git fetch %s failed; using local refs (%s)' % (remote, fetched.stderr.strip()),
                      file=sys.stderr)
    results = report(args.repo, args.base_file, args.main, args.ref)
    print(json.dumps(results, indent=2) if args.json else format_report(results, args.main))
    if any(entry['warnings'] for entry in results):
        return 2
    return 1 if args.fail_on_new and any(entry['commits'] for entry in results) else 0


if __name__ == '__main__':
    sys.exit(main())
