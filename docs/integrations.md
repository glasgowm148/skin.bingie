# Optional integrations

The legacy integration toggles under Configure Skin → Experience options default off and take effect after a skin reload (the window's Apply button, disabled during playback, or a Kodi restart). Each reload chooses either the stock or experience include branch; duplicate native guide control IDs are never loaded together.

| Setting | Additional requirement | Missing/off behavior |
| --- | --- | --- |
| `KM_EnableProviderActions` | Patched POV with `manager_watchlist_status`, `manager_watchlist`, `manager_show`, `manager_seen`, `manager_rating_status`, `manager_rating` | Stock Bingie information controls; no manager-route initializers |
| `KM_EnableLiveTV` | Bingie Companion or existing `script.kodi.live.tv` supporting `home` and `day`, with a configured PVR client | Stock guide. Stock PVR rows are used unless custom rows or family mode are explicitly enabled |
| `KM_EnableDirectSwitch` | Bingie Companion or existing `script.kodi.live.tv` supporting `switch-account`; Kodi 22 requires a compatible guarded coordinator | Native profile picker |

## Per-profile channel rows and family mode

`KM_CustomPVRRows` uses up to three explicit `KM_PVRRow1Path`/`KM_PVRRow1Label` pairs (and rows 2/3).
Choose them through **Experience options → Choose channel rows** with Bingie Companion installed.
The picker uses the PVR directory paths returned by Kodi; it never guesses group IDs from labels.
Cancelling the picker leaves all rows unchanged. `KM_PVRShowRecent` optionally adds Recently Watched
for unrestricted custom-row profiles. The standard PVR rows remain the default for ordinary installs.

`KM_FamilyMode` is an explicit per-profile choice. It hides stock all-channel, recording and history
rows regardless of companion availability, displaying only the chosen group paths. Missing rows stay
empty. Provider season filtering also requires enabled Kodi Manager; without it the family provider
route is absent instead of falling back to an unfiltered route. Family mode is a presentation filter,
`KM_FamilyGuideAllowed` separately permits guide shortcuts only when the owner has restricted the PVR client itself; it defaults off. Family mode is not an authentication boundary; use Kodi profile locks and backend access controls as appropriate.

Older custom installs must prepare these explicit settings before upgrading from 2.0.2.15 or earlier.
Keep the old skin/settings backups. The private reference installation has a separate stopped-Kodi,
additive settings migration; its names, group paths and user settings are not shipped in this skin.
The new keys are ignored by older skin versions, preserving rollback behavior.

## Voice and reusable companions

[Bingie Companion](https://github.com/glasgowm148/bingie-companion) installs separately. Existing
`script.kodi.live.tv` keeps navigation precedence. Enable `KM_EnableVoiceSearch` under Search only
after installing/configuring the companion and its Android voice app. The on-screen button is visible
only on Android with the enabled Kodi companion; its Up/Down navigation connects to the typed keyboard.
It is disabled during playback. **Set up voice search** explains the requirements and can open the
Android app's private configuration screen. `ShowVoiceSearchHint` remains a separate opt-in for owners
who configured their remote's physical mic button.

The Android app handles listening, partial recognition, errors and microphone permission; recognized
text goes through Kodi Manager 0.7.42+'s authenticated local voice API into the existing search.
The on-screen action never takes the system assistant role. The remote mic requires a separate owner
choice. Audio may be sent to the Android speech provider; no local-only recognition claim is made.

For a provider-neutral Continue Watching widget, configure sources in the companion's current-profile
settings and use `plugin://script.bingie.companion/?mode=continue`. There are no default providers or
cross-profile fallback sources. See the companion README for setup and validation limits.


BBC items also require the helper's `browse-bbc-show` and `mark-bbc-watched` actions. Their experience buttons are disabled if the helper is absent. This skin does not copy cloud history or authorize an account.

Playback recovery is a separate provider integration. It owns `pov_recovery_prompt`, `pov_recovery_session`, `pov_recovery_request` and `pov_recovery_dismissed` on Window(Home). The skin only presents Keep waiting/Try another stream; it never replaces a stream itself. An absent integration leaves the dialog dormant. The prompt stays hidden while `pov_recovery_dismissed` equals the current session, so Back dismisses it for that session.

The pause cleanup only closes an overlay marked `KM_AutoPauseInfo`; it preserves an overlay opened deliberately.

Auto-previews are tracked with `Window(Home).Property(KM_PreviewActive)`. The skin sets it when it arms a preview with an idle player (or while its own preview plays) and clears it whenever video enters fullscreen. Focus, hub and view-exit stop paths, and new previews, act only on playing unrecognised video while it is set, so a YouTube, IPTV or other add-on stream the user started (which always opens fullscreen) is never stopped or replaced by moving focus, even after leaving fullscreen with "Stop playback when leaving fullscreen" off. A preview the user switches to fullscreen becomes ordinary playback. The marker is not matched against the playing path: YouTube, IMDb and helper trailers resolve to plugin or stream URLs the skin cannot predict when it arms the 3-second alarm. A trailer started by hand from the information dialog can still be stopped by focus changes if an earlier preview left the marker set, as before.

Home rebuilds the Skin Shortcuts menu only when nothing is playing; while media plays the rebuild waits for the next Home load with an idle player. Leaving Skin Settings still rebuilds immediately.

The source validator permits the inherited include references recorded in `tests/upstream-unresolved.json`, including generated Skin Shortcuts templates and existing upstream legacy references. It rejects newly introduced unresolved names, and also undefined `$VAR`/`$EXP` names, missing skin strings (31000–32999), fonts absent from a fontset, missing custom windows, textures absent from `media/Textures.xbt` (two upstream textures are listed in the same file) focus-triggered trailer previews without the `KM_PreviewMayStart` playback guard ANDed at the top level of their condition, any stop in an `onfocus`/`onunfocus`/`onload`/`onunload`/`onback` handler (including through `AlarmClock`) without `$EXP[KM_PreviewPlaying]` at the top level, any play there without `KM_PreviewMayStart` or `!Player.HasMedia`, and household addresses or accounts in any NUL-free file under the folders the build ships. Only three stops are allowlisted, each still requiring its own guard term: leaving fullscreen with `ForceVideoPlaybackStop`, leaving the information dialog's trailer viewer (`KM_UnrecognizedVideo`), and the boot `Startup` window. It is not a substitute for Kodi's runtime/visual checks.

Changes to Kodi, POV, iPlayer, TMDb Bingie Helper, PVR or the Android helper stay outside this repository. Do not enable an optional integration solely because an addon with the same ID is installed: confirm its required routes are implemented.

An enabled Experience option can always be turned off, including after its helper add-on is removed. Enabling an inactive option still requires its dependency.
