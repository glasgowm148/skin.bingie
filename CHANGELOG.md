# Changes

## 2.0.2.11 — 2026-10-15

- Search remembers what you searched: with Kodi Manager installed, earlier searches matching what you type are listed first in the suggestions (tagged "recent"), and before typing the most recent ones are shown. Searches are recorded when you move into the results, pick a suggestion or leave the search screen. Turn it off in Skin settings → Search ("Disable search history").

## 2.0.2.10 — 2026-10-15

- Library and widget audio flags map Kodi 22's codec names (truehd_atmos, eac3_ddp_atmos, dtshd_ma_x, dts_es, aac_lc, pcm_dvd…) to the flag images the skin ships, as the player overlay already did; codec labels check Atmos and DTS:X before Dolby, TrueHD and DTS-HD.
- `check_skin.py` refuses audio flag textures built from the raw codec name.

## 2.0.2.9 — 2026-10-15

- Kodi 22: the OSD edit-list ranges use `Player.EditList` (`Player.Cutlist` was removed); audio flags and labels map Kodi 22's profile codec names (aac_lc, eac3_ddp_atmos, truehd_atmos, dts_es…).
- The always-false "Play from beginning" folder branch is removed (behaviour unchanged); `check_skin.py` reports labels Kodi 22 removed.

## 2.0.2.8 — 2026-10-15

- Fix conditions Kodi could never evaluate: the OSD age-rating badge and its colours now use TMDb Bingie Helper's rating property; the ISO "dvd" flag (`String.EmdsWith` typo); subtitle-language names; the TV-show "new episodes" sublabel and set years with the main menu open. Broken always-false terms are removed from the shared DB-type expressions (no behaviour change).
- The large watched indicator uses an existing font.
- `check_skin.py` flags unknown `String.*`/`Integer.*` functions and wrong argument counts.

## 2.0.2.7 — 2026-10-15

- Fix malformed conditions and paths that Kodi could not parse: crew/director/writer rows in the information dialog now close the dialog before opening the helper; the Spotlight TV/episode trailer condition (and its preview guard) parses; the version manager poster shows; the white studio footer logo path, the PVR channels OSD alarm and the cast-number setting label are well-formed; a stray `)` is removed from the Trakt watchlist path.
- Provider watchlist/rating actions no longer fall back to an episode's or season's own TMDb id as the show id.
- `check_skin.py` now rejects unbalanced brackets and parentheses in conditions, actions and labels; the render check reports Kodi condition-parser errors.

## 2.0.2.6 — 2026-10-13

- Director, creator and writer recommendations wait for a usable person ID instead of requesting an empty person from TMDb Bingie Helper.
- Episodes only request director recommendations when the director menu is selected; other information tabs no longer trigger that request.
- Person links pass the TMDb ID directly, removing the redundant empty search query. Writer recommendations retain their screenplay-first selection.
- Added route regression tests covering missing IDs, every supported person slot, media types, menu selection and writer fallback. Installed and tested on the reference Shield: missing-ID episode details, a valid director query, helper search, profile switching and local-video playback controls passed. A separate BBC-episode trailer lookup error remains outside this fix.

## 2.0.2.5 — 2026-10-12

- Bingie's search suggestions use TMDb Bingie Helper's movie/TV search instead of Google web autocomplete. The existing helper returns South Park first for `south` on the maintained Shield.
- Empty input retains static search categories without opening the helper's input dialog. Queries are URL-escaped, suggestion clicks fill the undecorated title, and paging is disabled.
- The general virtual keyboard keeps its existing Autocompletion provider setting. Installed on the reference Shield / Kodi 22 RC1: the native search screen displayed South Park first for `sout`, and empty input retained the search categories without opening an input dialog.

## 2.0.2.4 — 2026-10-12

- Prepare Bingie Experience for community distribution: rewritten README with the fork's additions, compatibility evidence, dependency installation, rollback and optional integration requirements.
- Add a generic Experience options screenshot from the Kodi 21 CI render; no household screenshots or layouts.
- Generalize the packaged-file privacy check to private LAN addresses, email addresses and URL credentials, with synthetic regression cases.
- Refresh add-on metadata and package version. Runtime skin XML is unchanged from 2.0.2.3, whose shipped files match the installation on the maintained NVIDIA Shield / Kodi 22 RC1 setup.
- Fetch and check Matke omega and BigMoco omega on 2026-10-12: no unmerged commits beyond the recorded revisions in UPSTREAM_BASE.

## 2.0.2.3

- Development only (no skin change): `docs/upstream.md` documents reviewing and merging upstream Bingie; `UPSTREAM_BASE` records the merged Matke (`9f1c6eb`) and BigMoco (`c960cbb`) revisions and `scripts/upstream_report.py` lists upstream commits missing from `main`, flagging files the fork also changed.
- Development only: a separate `render.yml` workflow screenshots the skin in a headless Kodi 21 (Flathub) and fails on new `kodi.log` skin errors; its latest run passed with stubbed Bingie dependencies.
- Moving focus, leaving a hub or pressing Back in a view no longer stops a YouTube, IPTV or other add-on stream you started; only auto-previews the skin started (tracked with `KM_PreviewActive`, cleared when video goes fullscreen) are stopped or replaced.
- Home no longer rebuilds the Skin Shortcuts menu while anything is playing; the next Home load with an idle player rebuilds it.
- Back from the information dialog's trailer viewer stops only the trailer, never live TV or library video; the startup splash only plays with an idle player.
- Validator rejects stops and plays in focus, load, unload and Back handlers (directly or via `AlarmClock`) without a preview or playback guard; only the fullscreen-exit stop, the trailer viewer and the boot window are allowlisted.
- CI runs the validator, pytest and unittest on Python 3.9, 3.10 and 3.12 and checks that two ZIP builds are byte-identical; actions are pinned by commit SHA with read-only permissions.

## 2.0.2.2

- Opening a cast or crew member from the auto-opened pause information no longer stops playback when "Stop playback when leaving fullscreen" is on.
- A profile named `Kids` never falls back to all-channel, recordings or Recently Watched PVR hub rows; it keeps the `Little Ones` and `Cartoons` group rows.
- Experience options explain that changes apply after a skin reload and offer an Apply button that is disabled during playback.
- After upgrading from the earlier patched overlay, enable all three Experience options in every profile (see docs/integrations.md).
- Validator requires the preview guard ANDed at the top level and scans every shipped folder for household identifiers.
- Builds refuse to overwrite an existing release ZIP of the same version with different contents.

## 2.0.2.1

- Allow enabled integrations to be turned off after their dependency is removed.
- Auto-preview trailers no longer start while a paused or recognised video, live TV or music is playing; only an idle player or another preview is replaced.
- Dismissing the stream-recovery prompt with Back keeps it closed for that session instead of reopening immediately.
- Restore the stock PVR hub rows by default; the household channel-group rows now follow the Live TV Experience option.
- Show the context-menu Trakt/Favourites hint only when provider actions are enabled.
- Validator also checks variables, expressions, skin strings, fonts, custom windows and packed textures.
- Reject symlinked, hidden and private runtime artifacts during packaging; failed builds preserve the previous ZIP.

- Preserve BigMoco history and keyboard layout; merge reviewed Matke omega updates.
- Import skin navigation, watchlist icons, ratings controls, episode/season view, pause-overlay, guide, profile-switch overlay and stream-recovery presentation changes.
- Make patched provider, custom guide and direct-switch integrations opt-in with standard Bingie fallbacks.
- Add Experience options to Configure Skin; guard BBC helper actions when absent.
- Normalize malformed XML comments/entity escaping inherited from upstream for validation.
- Add XML/include checks, fallback regression tests and a deterministic skin ZIP builder.

The 2.0.2.3 runtime is installed on the maintained Shield / Kodi 22 RC1 setup. Headless Kodi 21 rendering and source tests cover additional default/fallback paths; they do not establish compatibility with every device or add-on combination. No credentials, personal layout data or add-on/account patches are bundled.
