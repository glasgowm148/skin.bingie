# Beta acceptance and rollback

Source checks and CI rendering do not establish Android voice recognition or every helper/provider
combination. Keep these checks separate from the automated results in the release notes.

Before installation, back up the current skin ZIP, per-profile skin settings and Skin Shortcuts data.
Keep existing companion/voice app versions. Test only when the TV is idle and available.

- With optional companions absent, check Home, the typed keyboard, title suggestions, episode/season
  views and the standard PVR guide. No companion error or installation prompt should appear.
- Choose channel rows in a test profile. Cancel midway and confirm its previous choices remain.
  Enable family mode and confirm missing rows stay empty, with no unrestricted history/channel
  fallback. Enable family guide shortcuts only with a restricted PVR client.
- In an existing configured installation, confirm the original navigation helper still handles
  guide/profile actions. Verify direct switching retains its original guarded relaunch behavior.
  Unsupported Kodi 22 switching must be refused, never attempted through native profile loading.
- Install/configure the optional Android voice app and Kodi companion separately. Check the mic's
  keyboard navigation, permission prompt, partial/final speech, cancel, empty recognition, missing
  token, unreachable Kodi Manager, and a title containing a comma. Spoken results should use the
  same search view; cancelling must preserve typed text. Test the physical mic only after an explicit
  assistant-role choice; an on-screen mic test must not change that role.
- While a local test video is playing/paused, verify disruptive voice/profile actions are disabled
  or refused and ordinary focus changes do not stop playback.
- With explicitly configured Continue Watching sources, check a resumable duplicate, completed
  items and an unavailable source. Switch profiles and confirm no source/history is inherited.
- Roll back to the saved skin ZIP. Newly added community keys are ignored by older skins; restore
  the saved settings/Skin Shortcuts backup if needed. New public companion/app IDs can coexist with
  existing helpers, so a skin rollback does not require replacing a working voice installation.

For the reference installation, the stopped-Kodi settings migration remains private. It adds explicit
family/channel choices without overwriting existing settings and keeps backups before either profile
is written. Do not copy that installation's settings into a community release.

The 2026-10-17 reference Shield beta observations are recorded in
[Bingie Companion's runtime validation](https://github.com/glasgowm148/bingie-companion/blob/main/docs/runtime-validation.md).
Those observations distinguish native UI/API checks from spoken-recognition acceptance and retain
all device-specific evidence privately.
