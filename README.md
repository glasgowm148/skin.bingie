# Bingie Experience

A private development fork of **Bingie**, focused on a smoother TV experience: clearer watchlists, easier episode navigation, an integrated programme guide and playback controls that get out of the way.

Based on [BigMoco's Bingie](https://github.com/Bigmoco/skin.bingie), with reviewed [Matke updates](https://github.com/matke-84/skin.bingie). Their Git history, credits and GPL v2 license are retained. This is an independent fork, not an official upstream release.

| Improvement | Availability |
| --- | --- |
| Episode/season browsing and pause-overlay cleanup | Skin changes |
| Widget layout and artwork-loading adjustments | Skin changes; no claim of universal speed improvement |
| Clear Add/Remove Watchlist controls, `+` icon, Browse Show and rating actions | Opt-in; requires compatible patched POV |
| Integrated Live TV guide, channel groups, guide search and day navigation | Opt-in; requires the custom Kodi navigation helper and configured PVR |
| Direct two-profile account switch and progress overlay | Opt-in; requires the custom Kodi navigation helper |
| Try another stream prompt | Dormant unless a compatible playback-recovery addon supplies its properties |

**Standard Bingie controls remain the default.** The fork contains no accounts, playlists, EPG URLs, API keys, profile photos, watched history or household hub configuration. Provider patches and the Android restart helper are separate projects.

## Install or roll back

This development ZIP uses the existing `skin.bingie` ID and **replaces** an installed Bingie. Back up the existing skin, profile settings and Skin Shortcuts data first. Have a copy of the previous skin ZIP available.

1. Build the ZIP using the commands below, or have your agent build it.
2. In Kodi, open **Settings → Add-ons → Install from zip file**, select the ZIP and reload the skin.
3. Check Home, Movies, Shows, an episode view and the guide before enabling optional integrations.
4. Under **Configure Skin → Experience options**, enable only integrations your installation supports. Reload the skin after changing these options.

For rollback, switch temporarily to Estuary, reinstall the previous Bingie ZIP, then restore the backed-up skin/Skin Shortcuts settings if needed. Reinstalling a skin alone does not restore personal layouts. Do not uninstall Kodi or erase its data.

## Compatibility

- Base: BigMoco omega `c960cbb`, merged with reviewed Matke omega `9f1c6eb`; BigMoco's keyboard layout is retained.
- Fork version: **2.0.2.1**. Addon dependencies remain declared in `addon.xml`.
- The originating skin changes were exercised on a Shield with Kodi 22 beta 2. This newly assembled fork and its optional/default branches have source/build validation; they have **not yet been installed and visually tested as a complete package**.
- The profile restart workaround applies to the tested Android beta build, not every Kodi version. See [NVIDIA MCP's optional source kit](https://github.com/glasgowm148/nvidia-MCP/tree/main/contrib/profile-relaunch).
- Stock POV does not implement our `manager_*` routes. Merely installing POV is insufficient: leave the provider toggle off unless those routes are available.
- BBC browse/watched actions additionally require `script.kodi.live.tv`. PVR Simple setup, playlists and EPG registration are outside the skin.

See [integration details](docs/integrations.md) and [changes](CHANGELOG.md).

## Validate and build

Python 3.9+; no third-party build dependency required. The agent handles these computer steps.

```sh
python scripts/check_skin.py
python -m unittest discover -s tests -q
python scripts/build_skin.py
```

The deterministic ZIP and SHA-256 file are written to `dist/`. ZIPs contain runtime skin files and the license, never development files or user profiles. CI validates XML, conditional fallbacks and package contents on each push; it does not automate TV testing.

Before publishing: test the complete package on a backed-up TV, inspect both default and enabled integration views, add generic screenshots and review the remaining upstream include warnings. No household screenshots or personal configuration are committed here.

## Credits and license

Bingie by Matke, with BigMoco's modifications and this fork's additions. **GPL v2.0**; see [LICENSE](LICENSE). Preserve upstream attribution when sharing or contributing patches. [Original README](README.upstream.md).
