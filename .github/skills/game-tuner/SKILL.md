---
name: game-tuner
description: "Manage PC game graphics settings. Use when: scanning installed games (Steam/Epic/GOG), querying PCGamingWiki for config paths, reading/parsing game config files, modifying graphics settings (resolution, vsync, frame limit, upscaling, screen mode, dynamic resolution, frame generation), exporting or importing game config backups. Keywords: game settings, graphics config, Steam, Epic, GOG, DLSS, FSR, XeSS, PCGamingWiki."
argument-hint: "Describe what you want to do with game settings (e.g., 'scan my games', 'set vsync off for Cyberpunk')"
---

# Game Tuner Skill

Manage PC game graphics settings via CLI. Supports scanning installed games, querying config file locations from PCGamingWiki, parsing 9 key graphics settings, and writing modifications back to disk.

## When to Use

- User wants to see what PC games are installed
- User wants to check or change game graphics settings (resolution, vsync, frame limit, etc.)
- User wants to export/import game config backups
- User asks about game config file locations

## Prerequisites

Run all commands from the project root:

```
cd "<project-root>"
```

Ensure dependencies are installed:

```
pip install -r requirements.txt
```

## Available Commands

### 1. Scan Installed Games

Detects games across Steam, Epic Games Store, and GOG.

```bash
python cli.py scan
python cli.py scan --platform steam
```

**Output:** JSON array of games with `name`, `platform`, `install_path`, `app_id`.

### 2. Query Config Paths from PCGamingWiki

Looks up where a game stores its config files.

```bash
python cli.py query "Cyberpunk 2077"
python cli.py query "Counter-Strike 2" --install-path "D:\Steam\steamapps\common\CS2"
```

**Output:** JSON with `raw_paths`, `expanded_paths`, `error`.

### 3. Detect Local Config Files

Finds and reads actual config files on disk for a game.

```bash
python cli.py detect "Cyberpunk 2077"
```

**Output:** JSON array of config file objects with `expanded_path`, `content`, `found`.

### 4. Parse Graphics Settings

Extracts 7 key settings from a game's config files.

```bash
python cli.py parse "Cyberpunk 2077"
```

**Output:** JSON with current values for:

| Key | Description |
|-----|-------------|
| `resolution` | Display resolution (e.g., "1920x1080") |
| `screen_mode` | Fullscreen / Windowed / Borderless |
| `vsync` | V-Sync on/off |
| `frame_limit` | FPS cap value |
| `dynamic_resolution` | Dynamic resolution on/off |
| `upscaling` | Upscaling method such as DLSS / FSR / XeSS |
| `upscaling_mode` | Quality mode such as Quality / Balanced / Performance |
| `frame_generation` | Frame generation on/off |

### 5. Apply Settings

Write new settings to a game's config files.

```bash
python cli.py apply "Cyberpunk 2077" --settings '{"vsync": "Off", "frame_limit": "120"}'
python cli.py apply "Forza Horizon 5" --settings '{"resolution": "2560x1440", "screen_mode": "Fullscreen"}'
```

**Settings JSON keys:** `resolution`, `screen_mode`, `vsync`, `frame_limit`, `dynamic_resolution`, `upscaling`, `frame_generation`. Only include keys you want to change.

**Output:** JSON array of results with `path`, `status` ("ok"/"error"), `detail`.

### 6. Export Configs

Bundle game configs into a JSON backup package.

```bash
python cli.py export --output backup.json
python cli.py export --games "Cyberpunk 2077,Counter-Strike 2" --output backup.json
```

### 7. Import Configs

Restore game configs from a backup package.

```bash
python cli.py import backup.json
```

## Typical Workflow

1. **Scan** → find installed games
2. **Parse** → check current settings for a specific game
3. **Apply** → modify settings as needed
4. **Export** → create a backup before major changes

## Error Handling

- All commands output JSON to stdout
- Errors appear as `"error"` fields in the JSON output
- Non-zero exit code on fatal errors

## Supported Games (Parser-Specific)

The tool has specialized parsers for:
- **Cyberpunk 2077** — `UserSettings.json`
- **Unreal Engine games** — `GameUserSettings.ini`
- **Forza Horizon** — XML config
- **Counter-Strike 2** — Valve KV format (multi-file)
- **Horizon Zero Dawn / Shadow of the Tomb Raider** — Registry-based JSON

Other games fall back to generic INI/JSON/XML heuristic parsing.
