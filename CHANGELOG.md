# Changelog

# v0.08.7 (2026-09-17)

### Fixed
- Black Myth: Wukong Benchmark Tool now derives borderless output resolution from its base resolution and window scaling value.
- Black Myth: Wukong now preserves explicit display resolution instead of replacing it with image-quality data.
- Upscaling is consistently represented as separate Method and Mode settings across parsers, writers, the GUI, CLI, and HTTP API.
- F1 25 and Forza Horizon 6 verification rules now authorize the separate `upscaling_mode` setting.
- The reviewed rule source retains all current writable candidates: Cyberpunk 2077, F1 25, and Forza Horizon 6.

### Validation
- Full test suite: 305 passed.
- Every selectable upscaling Method/Mode combination for the three writable candidates passed writer-to-parser round-trip tests.
- The Windows x64 release archive and verification manifest checksums were validated.

---

# v0.08.6 (2026-09-17)

### Fixed
- Cyberpunk 2077 2.31 now reads string-based window modes correctly.
- Cyberpunk writes preserve the current JSON schema and synchronize dynamic-list indexes for verified display modes and resolutions.
- Cyberpunk VSync now exposes refresh-specific values such as `144`, `72`, `48`, and `36`, and writes their matching dynamic-list indexes.
- Cyberpunk Screen Mode now matches the game UI by offering only Windowed and Borderless Windowed.
- The active desktop resolution is labeled as recommended for proper window scaling.
- VSync choices are generated from the active refresh rate, including non-144/60 Hz displays.
- Dynamic Resolution and Frame Generation remain read-only until their current-version write semantics are verified.
- Cyberpunk Quick Preset options are now exposed consistently by the GUI, CLI, and HTTP API.
- Cyberpunk upscaling writes now synchronize the `ResolutionScaling` method and dynamic-list index.
- Cyberpunk 2.31 guarded writes now allow method-level upscaling and Quick Preset testing with automatic read-back restore.
- Cyberpunk FSR and XeSS dropdowns now expose their quality modes and synchronize each mode's value and dynamic-list index.
- Cyberpunk upscaling read-back now validates the selected quality mode, not only the upscaling method.
- Cyberpunk upscaling is now split into method and mode controls, distinguishing FSR 2.1, FSR 3, and XeSS.
- Cyberpunk mode choices now follow the selected method and include Native AA and Dynamic where supported.
- Cyberpunk 2.31 now reads and writes the renamed `MaximumFPS_Value` field while retaining legacy `MaximumFPS` compatibility.
- Cyberpunk Frame Limit now uses the game-native `Off` label instead of `Unlimited`, and guarded writes now authorize this setting.

### Validation
- Full test suite: 278 passed.
- Real Cyberpunk 2077 2.31 validation confirmed `Windowed` and `1920x1080` persist in the game UI.

---

# v0.08.5 (2026-09-16)

### Fixed
- F1 25 parser now reports `Custom (BasePreset)` when Frame Generation is enabled over a recognized base preset.
- Apply now refreshes the visible settings from the actual written config instead of displaying raw dropdown values.
- F1 25 Quick Preset is included in the guarded write rule and writer flow.
- F1 25 parser dispatch handles the registered `F1® 25` scanner name consistently.

### Validation
- Full test suite: 252 passed.
- Real GUI validation confirmed `Custom (Medium)` after applying Medium with Frame Generation enabled.

---

# v0.08.4 (2026-09-14)

### Fixed
- F1 25 automatically changes Fullscreen to Windowed when enabling AMD FSR3 or XeFG unless the user explicitly selects Borderless Windowed.
- F1 Frame Generation changes now preserve the game's valid Screen Mode constraint during Apply and read-back validation.

### Validation
- Full test suite: 247 passed.
- F1 writer and automatic Screen Mode compatibility tests passed.
- F1 25 base Write flow was manually validated; Quick Preset/preset Write was not tested and remains outside the current write rule.

---

# v0.08.3 (2026-09-14)

### Fixed
- F1 25 now limits Screen Mode to Windowed or Borderless Windowed while Frame Generation is enabled.
- The same F1 compatibility rule is enforced before writing, including non-GUI write callers.
- F1 Frame Generation writer mappings now support Off, AMD FSR3, and XeFG.

### Validation
- Full test suite: 244 passed.
- F1 Frame Generation/Screen Mode compatibility tests passed.

---

# v0.08.2 (2026-09-14)

### Fixed
- F1 25 GUI now exposes dedicated FSR/XeSS quality dropdown options.
- F1 25 Resolution writes are covered using the registered Steam scanner name `F1® 25`.

### Validation
- Full test suite: 240 passed.
- F1 writer and options focused tests: 15 passed.

---

# v0.08.1 (2026-09-14)

### Fixed
- F1 25 writer dispatch now recognizes the Steam scanner's `F1® 25` game name instead of falling back to the Forza XML writer.
- F1 25 Screen Mode and other XML writes now use the F1-specific writer and read-back validation correctly.

### Validation
- Full test suite: 238 passed.
- F1 writer tests passed with the real `F1® 25` scanner name.

---

# v0.08.0 (2026-09-14)

### Fixed
- Corrected F1 25 verification matching to use the complete `hardwaresettings` directory fingerprint used by the GUI scanner.
- F1 25 now reaches `write_candidate: verified` when its detected Steam version and config layout match the published rule.

### Validation
- Full test suite: 238 passed.
- Real GUI-style F1 25 scan matched the write candidate rule.

---

# v0.07.9 (2026-09-14)

### Added
- Added guarded F1 25 XML writing for resolution, screen mode, V-Sync, frame limit, and FSR/XeSS upscaling modes.
- Added F1 25 `write_candidate` verification coverage for the detected Steam build and structural fingerprint.

### Fixed
- Verification status now prefers exact platform/fingerprint rules over the built-in wildcard baseline.
- F1 25 XeSS and FSR quality modes are reported using their game-specific `aa_quality` mappings.

### Validation
- Full test suite: 238 passed.
- F1 writer fixture tests and real-config verification status passed.

---

# v0.07.8 (2026-09-14)

### Fixed
- Forza Horizon 6 now rejects the incompatible `V-Sync On` plus `Unlimited` frame-limit combination before writing files.
- Cyberpunk 2077 now recognizes the real XeSS Frame Generation config shape and reports active `MFG: x2` state correctly.
- Verification update handling and management tooling now preserve safe cache behavior and expose clearer update outcomes.

### Validation
- Full test suite: 219 passed.
- Focused verification, CLI, and Cyberpunk tests: 41 passed.

---

# v0.07.7 (2026-09-14)

### Added
- PCGamingWiki configuration data now persists in the per-user Game Tuner cache instead of relying only on bundled files.
- The GUI asks before downloading PCGamingWiki data on first use and when newly detected games have no cached configuration data.
- Download decisions persist across restarts, while declined games remain offline and cached games are not downloaded again.

### Validation
- Added GUI consent and persistence regression coverage.
- Full test suite validated before release build.

---

# v0.07.6 (2026-09-14)

### Fixed
- Cyberpunk 2077 Frame Generation now reports the effective parent state instead of presenting a stale `DLSS_MultiFrameGeneration` child value when Frame Generation is Off.
- Cyberpunk Frame Generation writes preserve the stored MFG multiplier while changing only the parent setting.
- Check Rules now immediately refreshes all visible game verification statuses after a new manifest is installed.
- The UI displays the loaded verification manifest version and preserves the previous safe cache when an update fails.

### Validation
- Full test suite: 169 passed on the merged PR branch.
- Focused #30/#40 tests: 22 passed.

---

# v0.07.5 (2026-09-11)

### Added
- Added a reproducible Windows release build tool that runs tests, builds the PyInstaller bundle, creates SHA-256 checksums, includes verification manifest assets, and validates the final release asset set.

### Fixed
- Forza Horizon 6 v2 config package Restore now also restores the `fullscreen_choice` binary sidecar from the restored `UserConfigSelections` XML.
- Import now refreshes the GUI after a successful Restore so restored values are shown immediately.
- Forza Horizon 6 XeSS Ultra Performance now maps to `XeSSMode=6` instead of showing as an unknown preset.

### Validation
- Full test suite: 176 passed.
- Windows x64 PR EXE manually validated for Backup, Restore, and Consistency.

---

# v0.07.4 (2026-09-11)

### Fixed
- Rebuilt from the latest `main` after PR #66 so Forza Version 52 FrameRate mapping is included in the distributed EXE.
- Release packaging includes both verification manifest assets required by Check Rules.

---

# v0.07.3 (2026-09-11)

### Fixed
- Forza Horizon 6 FrameRate mapping now matches the current UI: 20, 30, 60, and Unlimited.
- Removed unsupported 40 FPS and 120 FPS FrameRate options from the Forza dropdown.

### Validation
- Full test suite: 174 passed.
- Windows x64 EXE rebuilt from merged `main`.

---

# v0.07.2 (2026-09-10)

### Added
- Forza Horizon 6 guarded preset Write for Very Low, Low, Medium, High, Ultra, and Extreme quality signatures.
- Preset writes update the full captured quality component signature and use existing backup/rollback validation.

### Safety
- Ray-tracing variants remain Read-only.
- Overall preset Write is experimental `write_candidate`, not `write_verified`.

---

# v0.07.1 (2026-09-10)

### Fixed
- Forza Horizon 6 Read inference now recognizes Very Low, Low, Medium, High, Ultra, Extreme, High + RT, Ultra + RT, and Extreme + RT signatures.
- Overall presets and ray-tracing variants remain Read-only; mixed signatures remain `Custom`.

---

# v0.07.0 (2026-09-10)

### Fixed
- Forza Horizon 6 now infers the captured Extreme and Lowest Graphics & Performance preset signatures.
- Unknown or mixed component quality combinations remain `Custom`.

---

# v0.06.8 (2026-09-10)

### Fixed
- Forza Horizon 6 Version 52 FrameRate parsing now covers 20/30/40/60/120/Unlimited consistently.
- Forza Quick Preset remains visible as a derived Read value, but its non-functional write dropdown is hidden.

---

# v0.06.7 (2026-09-10)

### Fixed
- Forza Horizon 6 now exposes and writes FSR Quality, Balance, Performance, and Ultra Performance modes.
- Forza Horizon 6 now exposes and writes XeSS Ultra Quality Plus, Ultra Quality, Quality, Balanced, and Performance modes.
- Corrected Version 52 frame-limit enum handling and hides unsupported Borderless Windowed selection for Forza.

---

# v0.06.6 (2026-09-10)

### Fixed
- Forza Horizon 6 now writes `fullscreen_choice` as the required binary byte (`0x00` or `0x01`) instead of ASCII text (`"0"` or `"1"`).

---

# v0.06.5 (2026-09-10)

### Fixed
- Forza Horizon 6 Screen Mode writes now update both `UserConfigSelections` and the `fullscreen_choice` launch-state sidecar.
- The sidecar is included in guarded backups and rollback.

---

# v0.06.4 (2026-09-10)

### Fixed
- Forza Horizon 6 Screen Mode now preserves the confirmed Version 52 semantics: `Fullscreen=1` is Fullscreen and `Fullscreen=0` is Windowed.
- Added regression coverage based on the real persistence test.

---

# v0.06.3 (2026-09-10)

### Fixed
- Forza Horizon 6 Version 52 Screen Mode now uses the game's actual Full Screen toggle semantics for Read and Write.

---

# v0.06.2 (2026-09-10)

### Fixed
- Forza Horizon 6 reports Dynamic Resolution and independent Frame Generation as `N/A` when the game does not expose them as separate settings.
- Forza guarded Write rules no longer advertise those unsupported settings.

---

# v0.06.1 (2026-09-09)

### Fixed
- Black Myth: Wukong and Benchmark Tool parsing now prefers confirmed resolution values and corrected UI mappings.
- Forza Horizon 6 `UserConfig` Version 52 frame-rate read/write mapping now reports and writes 60 FPS correctly.

### Validation
- Added regression coverage for Black Myth Benchmark and Forza Horizon 6 parser/writer behavior.
- Updated the 19-target game validation plan and evidence collection instructions.

---

# v0.06.0 (2026-09-08)

### Added
- Verification rule updates from GitHub Releases with checksum validation, local fallback, and diagnostic logging
- `candidate`, `read_verified`, `write_candidate`, `write_verified`, and `deprecated` support states
- Explicit tester consent, automatic backups, read-back validation, and rollback for guarded writes
- Privacy-aware diagnostic ZIP export with per-file selection and hardware metadata
- Touch drag scrolling and clean-environment EXE validation workflows

### Changed
- Remote verification rules merge over built-in read-only rules
- Game-specific config selection now prefers authoritative filenames
- Black Myth: Wukong Benchmark Tool uses its known local config path

---

## v0.05.1 (2026-06-14)

### New Features
- **Global Settings Panel**: New top-level panel with dropdowns for all 7 settings — apply once, write to all supported games via "⚡ Apply to All Supported Games" button
- **Smart Dropdown Filtering**: Per-game settings panels now only show dropdowns for settings the game actually supports; `N/A` settings shown as read-only labels, unsupported (`None`) settings hidden entirely

### Bug Fixes
- **`{{P|game}}` expansion**: Now correctly substitutes the game's install path instead of expanding to an empty string
- **`{{P|userprofile/appdata/locallow}}`**: Added missing token mapping for Unity LocalLow config paths (e.g. Sons Of The Forest)
- **Wiki markup in paths**: Strip `''(version info)''` italic markup from config paths returned by PCGamingWiki
- **™/®/© in game titles**: Retry wiki lookups with cleaned titles and search API fallback when special characters cause lookup failures (e.g. Horizon Zero Dawn™ Remastered)

### Files Changed
- `main.py` — Version bump to 0.05.1
- `gui/app.py` — Global settings panel, smart dropdown filtering, window 960×700
- `wiki_api/pcgamingwiki.py` — `install_path` parameter, `locallow` token, wiki markup stripping, ™/® retry logic

---

## v0.05 (2026-06-12)

### New Features
- **Settings Editor**: Each game's expandable panel now shows editable dropdown menus alongside the current value for all 7 key settings (Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling, Frame Generation)
- **Per-Game Apply**: "✏️ Apply Changes" button in each game's settings panel writes dropdown selections back to the actual config files on disk
- **Batch Apply All**: "⚡ Batch Apply All" button in the action bar applies pending changes across all games at once
- **Settings Writer Module** (`config_manager/settings_writer.py`): New module with format-specific writers:
  - `_write_cyberpunk()` — JSON (Cyberpunk 2077 UserSettings.json)
  - `_write_unreal_ini()` — INI (Unreal Engine games)
  - `_write_forza_xml()` — XML (Forza Horizon series)
  - `_write_registry_json()` — Registry (HZD Remastered, Shadow of the Tomb Raider)
  - `_write_cs2_video()` — Valve KV (Counter-Strike 2)
- **Setting Options** (`SETTING_OPTIONS`): Predefined dropdown choices for each setting key

### Files Changed
- `main.py` — Version bump to 0.05
- `config_manager/__init__.py` — Export `SETTING_OPTIONS`, `write_settings`
- `config_manager/settings_parser.py` — Added `SETTING_OPTIONS` dict
- `config_manager/settings_writer.py` — **NEW** Settings write-back module
- `gui/app.py` — GameRow dropdowns, Apply button, Batch Apply, wider window (960x650)

---

## v0.04.1 (2026-06-05)

### Verified Games (tested on workstation)

| Game | Config Found | Config Path |
|------|-------------|-------------|
| Baldur's Gate 3 | ✅ | `{{p|localappdata}}\Larian Studios\Baldur's Gate 3\graphicSettings.lsx` |
| Cyberpunk 2077 | ✅ | `{{P|localappdata}}\CD Projekt Red\Cyberpunk 2077\UserSettings.json` |
| Hades II | ✅ | `{{p|userprofile}}\Saved Games\Hades II\GlobalSettingsWin.sjson` |
| Apex Legends | ✅ | `{{P|userprofile}}\Saved Games\Respawn\Apex\local\videoconfig.txt` (+ 2 more) |
| Red Dead Redemption 2 | ✅ | `{{P|userprofile\Documents}}\Rockstar Games\Red Dead Redemption 2\Settings\system.xml` |
| Black Myth: Wukong | ✅ | `{{p|localappdata}}\b1\Saved\Config\Windows\GameUserSettings.ini` (+ 26 more) |
| Horizon Zero Dawn™ Remastered | ✅ | `{{p|userprofile\documents}}\Horizon Zero Dawn Remastered\profile.dat` |

### Cache Updated
- Added **Baldur's Gate 3**, **Hades II**, **Apex Legends** to `cache/wiki_cache.json`
- Added 27 more games from PCGamingWiki verification: Total War: Warhammer III, Horizon Zero Dawn, Naraka: Bladepoint, Elden Ring, Sons of the Forest, Street Fighter 6, Palworld, Starfield, Nine Sols, The Finals, EA Sports FC 24, Horizon Forbidden West, F1 24, Marvel Rivals, Strange Brigade, Monster Hunter Wilds, Tom Clancy's Rainbow Six Siege, Fallout 4, Dying Light 2, Helldivers 2, Dota 2, PUBG: Battlegrounds, Hogwarts Legacy, Hollow Knight: Silksong, Metro Exodus, Resident Evil 6, Grand Theft Auto V Enhanced
- Total cache: 49 games

---

## v0.04 (2026-06-05)

### New Features
- **Key Settings Panel**: Added expandable settings panel in each GameRow showing 7 key graphics settings:
  - Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling, Frame Generation
- **Settings Parser** (`config_manager/settings_parser.py`): New module with dedicated parsers for multiple config formats:
  - `_parse_cyberpunk()` — JSON (Cyberpunk 2077 UserSettings.json)
  - `_parse_unreal_ini()` — INI (Unreal Engine games like ARC Raiders)
  - `_parse_forza_xml()` — XML (Forza Horizon 6 UserConfigSelections)
  - `_parse_registry_json()` — Registry JSON (Horizon Zero Dawn Remastered, Shadow of the Tomb Raider)
  - `_parse_cs2()` — Valve KeyValues (Counter-Strike 2 multi-file configs)
- **Frosted Glass Dark Theme**: Full visual redesign with frosted glass dark theme for GUI
- **English Labels**: All UI labels switched to English (`DISPLAY_NAMES_EN`)
- **Simulation Tool** (`tools/simulate_gui.py`): Standalone GUI preview tool with frosted glass theme
- **Config Import v2 Support**: `ConfigPackage.import_package()` now supports both v1 and v2 package formats

### Bug Fixes
- Fixed Cyberpunk 2077 VSync localization key display (now shows "Off"/"On" instead of raw `LocKey`)
- Fixed Shadow of the Tomb Raider Frame Generation showing `None` instead of `N/A`
- Fixed "Unsupported package version 2" error when importing configs exported by v0.04
- Fixed v2 import to write raw content back to files (skips registry entries and binary files)

### Verified Games (tested on real machine — MVT-PR4)

| Game | Config Format | Key Settings Extracted |
|------|--------------|----------------------|
| Cyberpunk 2077 | JSON (`UserSettings.json`) | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling (XeSS), Frame Generation (XESS/MFG) |
| ARC Raiders | Unreal INI (`GameUserSettings.ini`) | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling (XeSS), Frame Generation |
| Forza Horizon 6 | XML (`UserConfigSelections`) | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling (XeSS), Frame Generation |
| Horizon Zero Dawn™ Remastered | Registry + binary `profile.dat` | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling (XeSS), Frame Generation |
| Counter-Strike 2 | Valve KV (`.vcfg` + `.txt`, multi-file) | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution (N/A), Upscaling, Frame Generation (N/A) |
| Shadow of the Tomb Raider | Registry JSON | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling (XeSS), Frame Generation (N/A) |

> **Note**: "Steamworks Common Redistributables" is detected by Steam but has no config files (expected behavior).

### Files Changed
- `main.py` — Version bump to 0.04
- `config_manager/__init__.py` — Updated exports for new functions
- `config_manager/settings_parser.py` — **NEW** Key settings extraction module
- `config_manager/package.py` — Added v2 import support (`SUPPORTED_VERSIONS`, `_import_v2`)
- `config_manager/config_exporter.py` — v2 export format with config file contents
- `gui/app.py` — GameRow redesign with key settings panel, frosted glass theme, English labels
- `tools/simulate_gui.py` — **NEW** Standalone GUI simulation tool
- `wiki_api/pcgamingwiki.py` — Wiki API improvements
- `tests/test_config_exporter.py` — Test updates
- `tests/test_wiki_api.py` — Test updates
- `validation/test6.json` — **NEW** Real machine test data (export)
- `validation/test7.json` — **NEW** Real machine test data (import test)

---

## v0.03 (2026-06-04)

- Wiki cache system for offline operation
- Config file detection and status display in GUI
- Path token expansion fixes and diagnostic tools

## v0.02

- Initial GUI with CustomTkinter
- PCGamingWiki API integration
- Config file reading/writing (JSON, XML, INI)

## v0.01

- Project scaffolding
- Basic config reader/writer
- PyInstaller packaging setup
