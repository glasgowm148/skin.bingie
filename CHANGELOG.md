# Changes

## 2.0.2.1 — development

- Allow enabled integrations to be turned off after their dependency is removed.
- Auto-preview trailers no longer start while a paused or recognised video, live TV or music is playing; only an idle player or another preview is replaced.
- Reject symlinked, hidden and private runtime artifacts during packaging; failed builds preserve the previous ZIP.

- Preserve BigMoco history and keyboard layout; merge reviewed Matke omega updates.
- Import skin navigation, watchlist icons, ratings controls, episode/season view, pause-overlay, guide, profile-switch overlay and stream-recovery presentation changes.
- Make patched provider, custom guide and direct-switch integrations opt-in with standard Bingie fallbacks.
- Add Experience options to Configure Skin; guard BBC helper actions when absent.
- Normalize malformed XML comments/entity escaping inherited from upstream for validation.
- Add XML/include checks, fallback regression tests and a deterministic skin ZIP builder.

The complete fork has not yet been installed or visually verified on a TV. No credentials, personal layout data or addon/account patches are bundled.
