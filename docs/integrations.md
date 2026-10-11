# Optional integrations

The toggles under Configure Skin → Experience options default off and take effect after a skin reload (the window's Apply button, disabled during playback, or a Kodi restart). Each reload chooses either the stock or experience include branch; duplicate native guide control IDs are never loaded together.

| Setting | Additional requirement | Missing/off behavior |
| --- | --- | --- |
| `KM_EnableProviderActions` | Patched POV with `manager_watchlist_status`, `manager_watchlist`, `manager_show`, `manager_seen`, `manager_rating_status`, `manager_rating` | Stock Bingie information controls; no manager-route initializers |
| `KM_EnableLiveTV` | `script.kodi.live.tv` supporting `home` and `day`, configured PVR client; the PVR hub rows expect channel groups `TV Guide`, `Sky Sports` and `TNT Sports` (`Little Ones` and `Cartoons` for a profile named `Kids`) | Stock guide and stock PVR hub rows (Recently Watched, Channels, Recordings, Live & Radio); a profile named `Kids` gets only the `Little Ones` and `Cartoons` group rows (hidden when the group is absent), never all channels, recordings or Recently Watched |
| `KM_EnableDirectSwitch` | `script.kodi.live.tv` supporting `switch-account` and its guarded two-profile restart integration where needed | Native profile picker |

Skin settings are stored per profile. When an installation that ran the earlier patched overlay (where these features were always on) is upgraded to this build, switch `KM_EnableProviderActions`, `KM_EnableLiveTV` and `KM_EnableDirectSwitch` on in **every** profile, including `Kids`, then reload the skin; otherwise the Trakt actions, integrated guide and PVR hub rows, and direct profile switching revert to stock. With Experience Live TV enabled, the `Kids` PVR hub hides Recently Watched.

BBC items also require the helper's `browse-bbc-show` and `mark-bbc-watched` actions. Their experience buttons are disabled if the helper is absent. This skin does not copy cloud history or authorize an account.

Playback recovery is a separate provider integration. It owns `pov_recovery_prompt`, `pov_recovery_session`, `pov_recovery_request` and `pov_recovery_dismissed` on Window(Home). The skin only presents Keep waiting/Try another stream; it never replaces a stream itself. An absent integration leaves the dialog dormant. The prompt stays hidden while `pov_recovery_dismissed` equals the current session, so Back dismisses it for that session.

The pause cleanup only closes an overlay marked `KM_AutoPauseInfo`; it preserves an overlay opened deliberately.

Auto-previews are tracked with `Window(Home).Property(KM_PreviewActive)`. The skin sets it when it arms a preview with an idle player (or while its own preview plays) and clears it whenever video enters fullscreen. Focus, hub and view-exit stop paths, and new previews, act only on playing unrecognised video while it is set, so a YouTube, IPTV or other add-on stream the user started (which always opens fullscreen) is never stopped or replaced by moving focus, even after leaving fullscreen with "Stop playback when leaving fullscreen" off. A preview the user switches to fullscreen becomes ordinary playback. The marker is not matched against the playing path: YouTube, IMDb and helper trailers resolve to plugin or stream URLs the skin cannot predict when it arms the 3-second alarm. A trailer started by hand from the information dialog can still be stopped by focus changes if an earlier preview left the marker set, as before.

Home rebuilds the Skin Shortcuts menu only when nothing is playing; while media plays the rebuild waits for the next Home load with an idle player. Leaving Skin Settings still rebuilds immediately.

The source validator permits the inherited include references recorded in `tests/upstream-unresolved.json`, including generated Skin Shortcuts templates and existing upstream legacy references. It rejects newly introduced unresolved names, and also undefined `$VAR`/`$EXP` names, missing skin strings (31000–32999), fonts absent from a fontset, missing custom windows, textures absent from `media/Textures.xbt` (two upstream textures are listed in the same file) focus-triggered trailer previews without the `KM_PreviewMayStart` playback guard ANDed at the top level of their condition, any stop in an `onfocus`/`onunfocus`/`onload`/`onunload`/`onback` handler (including through `AlarmClock`) without `$EXP[KM_PreviewPlaying]` at the top level, any play there without `KM_PreviewMayStart` or `!Player.HasMedia`, and household addresses or accounts in any NUL-free file under the folders the build ships. Only three stops are allowlisted, each still requiring its own guard term: leaving fullscreen with `ForceVideoPlaybackStop`, leaving the information dialog's trailer viewer (`KM_UnrecognizedVideo`), and the boot `Startup` window. It is not a substitute for Kodi's runtime/visual checks.

Changes to Kodi, POV, iPlayer, TMDb Bingie Helper, PVR or the Android helper stay outside this repository. Do not enable an optional integration solely because an addon with the same ID is installed: confirm its required routes are implemented.

An enabled Experience option can always be turned off, including after its helper add-on is removed. Enabling an inactive option still requires its dependency.
