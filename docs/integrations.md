# Optional integrations

The toggles under Configure Skin → Experience options default off. Each reload chooses either the stock or experience include branch; duplicate native guide control IDs are never loaded together.

| Setting | Additional requirement | Missing/off behavior |
| --- | --- | --- |
| `KM_EnableProviderActions` | Patched POV with `manager_watchlist_status`, `manager_watchlist`, `manager_show`, `manager_seen`, `manager_rating_status`, `manager_rating` | Stock Bingie information controls; no manager-route initializers |
| `KM_EnableLiveTV` | `script.kodi.live.tv` supporting `home` and `day`, configured PVR client; the PVR hub rows expect channel groups `TV Guide`, `Sky Sports` and `TNT Sports` (`Little Ones` and `Cartoons` for a profile named `Kids`) | Stock guide and stock PVR hub rows (Recently Watched, Channels, Recordings, Live & Radio); a profile named `Kids` gets only the `Little Ones` and `Cartoons` group rows (hidden when the group is absent), never all channels, recordings or Recently Watched |
| `KM_EnableDirectSwitch` | `script.kodi.live.tv` supporting `switch-account` and its guarded two-profile restart integration where needed | Native profile picker |

Skin settings are stored per profile. When an installation that ran the earlier patched overlay (where these features were always on) is upgraded to this build, switch `KM_EnableProviderActions`, `KM_EnableLiveTV` and `KM_EnableDirectSwitch` on in **every** profile, including `Kids`, then reload the skin; otherwise the Trakt actions, integrated guide and PVR hub rows, and direct profile switching revert to stock. With Experience Live TV enabled, the `Kids` PVR hub hides Recently Watched.

BBC items also require the helper's `browse-bbc-show` and `mark-bbc-watched` actions. Their experience buttons are disabled if the helper is absent. This skin does not copy cloud history or authorize an account.

Playback recovery is a separate provider integration. It owns `pov_recovery_prompt`, `pov_recovery_session`, `pov_recovery_request` and `pov_recovery_dismissed` on Window(Home). The skin only presents Keep waiting/Try another stream; it never replaces a stream itself. An absent integration leaves the dialog dormant. The prompt stays hidden while `pov_recovery_dismissed` equals the current session, so Back dismisses it for that session.

The pause cleanup only closes an overlay marked `KM_AutoPauseInfo`; it preserves an overlay opened deliberately.

The source validator permits the inherited include references recorded in `tests/upstream-unresolved.json`, including generated Skin Shortcuts templates and existing upstream legacy references. It rejects newly introduced unresolved names, and also undefined `$VAR`/`$EXP` names, missing skin strings (31000–32999), fonts absent from a fontset, missing custom windows, textures absent from `media/Textures.xbt` (two upstream textures are listed in the same file) and focus-triggered trailer previews without the `KM_PreviewMayStart` playback guard. It is not a substitute for Kodi's runtime/visual checks.

Changes to Kodi, POV, iPlayer, TMDb Bingie Helper, PVR or the Android helper stay outside this repository. Do not enable an optional integration solely because an addon with the same ID is installed: confirm its required routes are implemented.

An enabled Experience option can always be turned off, including after its helper add-on is removed. Enabling an inactive option still requires its dependency.
