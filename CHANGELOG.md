# Changes

## 2.0.2.3 — development

- Moving focus, leaving a hub or pressing Back in a view no longer stops a YouTube, IPTV or other add-on stream you started; only auto-previews the skin started (tracked with `KM_PreviewActive`, cleared when video goes fullscreen) are stopped or replaced.
- Home no longer rebuilds the Skin Shortcuts menu while anything is playing; the next Home load with an idle player rebuilds it.
- Back from the information dialog's trailer viewer stops only the trailer, never live TV or library video; the startup splash only plays with an idle player.
- Validator rejects stops and plays in focus, load, unload and Back handlers (directly or via `AlarmClock`) without a preview or playback guard; only the fullscreen-exit stop, the trailer viewer and the boot window are allowlisted.

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

The complete fork has not yet been installed or visually verified on a TV. No credentials, personal layout data or addon/account patches are bundled.
