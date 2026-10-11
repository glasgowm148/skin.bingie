# Merging upstream Bingie

This fork tracks two upstreams. Their merged revisions are recorded in [`UPSTREAM_BASE`](../UPSTREAM_BASE):

| Remote | Branch | Project | Recorded base |
| --- | --- | --- | --- |
| `matke` | `omega` | [matke-84/skin.bingie](https://github.com/matke-84/skin.bingie), the active Bingie upstream | `9f1c6eb` |
| `upstream` | `omega` | [Bigmoco/skin.bingie](https://github.com/Bigmoco/skin.bingie), the original base (keyboard layout) | `c960cbb` |

Both were joined in `5d0b828` ("fix: merge reviewed Bingie upstream updates"); every later fork change sits on top. Repeat the steps below for each upstream batch. Never rebase or force-push `main`; upstream history and credits stay intact.

## 1. Fetch and report

```sh
git remote add matke https://github.com/matke-84/skin.bingie.git      # once
git remote add upstream https://github.com/Bigmoco/skin.bingie.git    # once
git fetch matke && git fetch upstream
python scripts/upstream_report.py            # offline from local refs; --fetch fetches first, --json for tools
```

For each `UPSTREAM_BASE` line the report lists commits reachable from the upstream ref but not from `main`, every file each one touches, and marks it:

- `REVIEW` — the fork changed this file since the recorded base (`git diff --name-only <base> main`). Merge by hand.
- `clean` — the fork never touched it. Upstream's version can be taken as is.

Exit status: 0 = report printed, 1 = pending commits with `--fail-on-new`, 2 = warning (missing ref, stale base, rewritten upstream history). A "stale" base means `UPSTREAM_BASE` names a commit that is not in `main`; fix the file before merging.

## 2. Triage

For every pending commit read `git show -w <sha>` (`-w` hides the whitespace-only churn between the trees) and decide: take, adapt, or skip. Record skipped commits and why in the merge commit body.

- **Fork-only files** never exist upstream: `Custom_1169_ResumeClosePauseInfo.xml`, `Custom_1170_StreamRecovery.xml`, `Custom_1171_ExperienceSettings.xml`, `IncludesExperienceGuide.xml`, `docs/`, `scripts/`, `tests/`, `.github/`, `UPSTREAM_BASE`, `AGENTS.md`.
- **Toggle-guarded files** (`grep -l KM_Enable 1080i/*`): experience code sits behind `Skin.HasSetting(KM_Enable…)` conditions, usually as an `*_Experience` include next to a `*_Stock` include (e.g. `BingieInfo_*`, `bingie_items_pvr_*`). Upstream fixes to stock behaviour go into the `_Stock` branch, and into `_Experience` only where the same bug exists there.
- **Heavy local edits** — `IncludesDialogVideoInfo.xml`, `IncludesBingie.xml`, `Includes.xml`, `IncludesHomeWidgets.xml`, `MyPVRGuide.xml`, `View_525/527`, `DialogConfirm.xml`, `Font.xml`: compare `git diff -w <base> main -- <file>` with the upstream change before resolving.
- **BigMoco keyboard** (`IncludesBingieKeyboard.xml`): keep BigMoco's layout unless the Matke change is a bug fix that applies to it.
- **Translations and `strings.po`**: usually `clean`; take upstream. New fork strings stay in their own ID range — check upstream did not reuse an ID the fork added.
- `addon.xml`: take upstream dependency, `xbmc.gui` and metadata changes; keep the fork's `name`, `provider-name`, description, `<source>` and version scheme (step 6).
- Anything that adds automatic `PlayMedia`/`Stop` in focus, load, unload or Back handlers must get the preview guards described in [integrations](integrations.md); the validator rejects it otherwise.

## 3. Merge

```sh
git switch -c merge/matke-$(git rev-parse --short matke/omega) main
git merge --no-ff --no-commit matke/omega      # one upstream at a time; repeat for upstream/omega
# files marked clean merge automatically; resolve REVIEW files by hand:
git diff --name-only --diff-filter=U   # conflicted files
```

Rules: new fork behaviour is never the default, every `KM_*` toggle keeps a stock branch, and no household data enters the tree. Upstream XML that does not parse (malformed comments, bare `&`) is fixed minimally, as in the original merge.

Update `UPSTREAM_BASE` to the merged commit in the same merge commit (full SHA, e.g. `git rev-parse matke/omega`). Commit as `fix: merge reviewed Bingie upstream updates`, with a body naming the upstream range (`<old base>..<new tip>`), skipped commits and notable conflict resolutions.

## 4. Validator allowlist

`tests/upstream-unresolved.json` lists include names and textures that upstream itself references without defining them (mostly Skin Shortcuts templates generated at runtime). If `scripts/check_skin.py` reports `New unresolved includes` or a missing texture:

1. Confirm upstream has the same gap: `git grep -n '<name>' matke/omega -- 1080i`. If the fork's merge caused it, fix the merge instead.
2. Add the name, keep the lists sorted, and say so in the commit body.
3. Remove entries upstream has since defined:

```sh
python -c "import json,sys; sys.path.insert(0,'scripts'); from check_skin import unresolved, ROOT; \
k=json.load(open('tests/upstream-unresolved.json')); print(sorted(set(k['includes'])-unresolved(ROOT/'1080i')))"
```

## 5. Checks

```sh
python scripts/check_skin.py
python -m pytest -q tests
python -m unittest discover -s tests -q
python scripts/build_skin.py
python scripts/upstream_report.py            # must show no pending commits for the merged ref and no warnings
```

Push the branch and open a pull request against `main`: `validate.yml` repeats these on Python 3.9–3.12. Run the `Render skin` workflow (`render.yml`, workflow_dispatch) on the branch and compare its Home/window screenshots and `kodi.log` skin-error summary with the last run on `main`. Source tests and headless screenshots are not runtime validation on a TV.

## 6. TV test and release

Only with the owner's authorization and a known viewing state (nothing playing that matters):

1. Back up `userdata/addon_data/skin.bingie`, `userdata/addon_data/script.skinshortcuts` and the currently installed skin ZIP.
2. Install the built ZIP (**Settings → Add-ons → Install from zip file**) and reload the skin.
3. With every `KM_*` option off, check Home, Movies, Shows, an episode/season view, the information dialog, the guide, the PVR hub and the OSD/pause overlay.
4. Enable the Experience options supported by the installation in each profile, reload, and repeat; also confirm that moving focus over widgets does not stop playback started by the user.
5. Review `kodi.log` for `Error loading`, `Skin has invalid include` or missing-include warnings.
6. Roll back as described in the README if anything regresses.

Release: version is `<upstream version>.<fork revision>` — keep the upstream's three components and bump the fourth for fork releases (upstream `2.0.2` → `2.0.2.1`, `2.0.2.2`…; when upstream moves to `2.0.3`, restart at `2.0.3.1`). In one `release: <version>` commit update `addon.xml`, the CHANGELOG heading (list merged upstream revisions) and the README Compatibility lines (base revisions and fork version). `build_skin.py` refuses to reuse a version for different bytes. Do not push without the owner's approval.
