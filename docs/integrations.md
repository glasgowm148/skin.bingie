# Optional integrations

The toggles under Configure Skin → Experience options default off. Each reload chooses either the stock or experience include branch; duplicate native guide control IDs are never loaded together.

| Setting | Additional requirement | Missing/off behavior |
| --- | --- | --- |
| `KM_EnableProviderActions` | Patched POV with `manager_watchlist_status`, `manager_watchlist`, `manager_show`, `manager_seen`, `manager_rating_status`, `manager_rating` | Stock Bingie information controls; no manager-route initializers |
| `KM_EnableLiveTV` | `script.kodi.live.tv` supporting `home` and `day`, configured PVR client | Stock guide |
| `KM_EnableDirectSwitch` | `script.kodi.live.tv` supporting `switch-account` and its guarded two-profile restart integration where needed | Native profile picker |

BBC items also require the helper's `browse-bbc-show` and `mark-bbc-watched` actions. Their experience buttons are disabled if the helper is absent. This skin does not copy cloud history or authorize an account.

Playback recovery is a separate provider integration. It owns `pov_recovery_prompt`, `pov_recovery_session`, `pov_recovery_request` and `pov_recovery_dismissed` on Window(Home). The skin only presents Keep waiting/Try another stream; it never replaces a stream itself. An absent integration leaves the dialog dormant.

The pause cleanup only closes an overlay marked `KM_AutoPauseInfo`; it preserves an overlay opened deliberately.

The source validator permits the inherited include references recorded in `tests/upstream-unresolved.json`, including generated Skin Shortcuts templates and existing upstream legacy references. It rejects newly introduced unresolved names; it is not a substitute for Kodi's runtime/visual checks.

Changes to Kodi, POV, iPlayer, TMDb Bingie Helper, PVR or the Android helper stay outside this repository. Do not enable an optional integration solely because an addon with the same ID is installed: confirm its required routes are implemented.
