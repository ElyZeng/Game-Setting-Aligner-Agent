---
name: game-read-validation
description: "Guide interactive parser validation for a PC game's graphics settings. Use when starting a game validation, sampling config mappings, or checking parser reads after in-game saves without exiting. Fall back to exit-per-case when saves are not readable until shutdown, then check stability after one final restart. Keywords: read validation, parser test, game settings sampling, config mapping, read evidence."
argument-hint: "Provide the game title and platform, for example: Black Myth: Wukong on Steam"
user-invocable: true
disable-model-invocation: false
---

# Game Read Validation

Validate parser behavior from controlled in-game changes before implementing or testing writes.

## Safety and Privacy

- Never print, commit, or upload raw config contents, account identifiers, paths containing usernames, diagnostic ZIPs, or backups.
- Report only setting names, normalized values, filenames, structural keys, hashes, and redacted paths.
- Change one setting at a time. Keep every other visible setting unchanged.
- Do not infer enum mappings from another game, benchmark, or generic engine behavior.
- A benchmark or demo validates only that executable, not the retail game.

## Entry Criteria

1. Identify exact game title, platform, install path, game version, and client version.
2. Read the target game's `validation-evidence/<game>/COLLECT.txt` when present.
3. Detect config files and run `python cli.py parse "<game>"` for the baseline.
4. Record a privacy-safe structural fingerprint and hashes for detected files.
5. List every graphics setting visible in the game and map it to the 9-setting schema:
   `resolution`, `screen_mode`, `vsync`, `frame_limit`, `dynamic_resolution`,
   `upscaling`, `upscaling_mode`, `frame_generation`, `quick_preset`.
6. Mark `N/A` only when the retail game genuinely lacks the setting.

## Sampling Matrix

Build a table with one row per setting and these columns:

| Setting | Baseline game value | Baseline parser value | Test value | Owned config changed | Read mode | Result |
|---|---|---|---|---|---|---|---|

Choose values that discriminate enum mappings. Sample each finite option you intend to mark verified; list other visible options as unsampled. For numeric ranges, sample boundary and representative values. Respect dependencies such as upscaling method controlling mode or frame generation.

## Continuous In-Game Loop (Default)

First, test whether this game/version saves a readable config while running: start from a known saved baseline, change one already-understood setting to a distinct value in the game, save, and confirm the displayed value without exiting. Re-detect the owned config; require a changed file hash or relevant registry value and two consecutive reads that agree on a complete, parseable snapshot before trusting the live result. If the save is not visible until exit, use the exit-per-case fallback below for this game/version.

For each subsequent case, keep the game open:

1. Tell the tester exactly one setting and one target value to select.
2. Ask the tester to save, return to the settings screen to confirm the displayed value, and leave the game running. Stop and wait for confirmation before reading.
3. Re-detect owned files or registry values; do not reuse an earlier GUI or CLI snapshot. Confirm a file hash or relevant registry value differs from the previous case and two consecutive reads agree on a complete, parseable snapshot. Do not treat an unchanged, missing, truncated, or transient config as a successful sample.
4. Run `python cli.py parse "<game>"` against the fresh saved state twice. Compare the selected value, its relevant stored key, and the other normalized settings with the game UI and previous case; do not print private content.
5. Record the observed mapping and read mode as evidence. Mark the case `Pass (in-session read)` only if the UI, stable saved file, and parser agree; this does not prove that every setting survives a restart.
6. If parser output is wrong despite a stable saved file, create a focused fixture from anonymized relevant fields, add a failing parser test, implement the smallest fix, and rerun focused and full suites. Reparse the saved file and confirm the UI still shows the selected value before marking the read passed; do not require another exit just for the fix.
7. Restore a known baseline in the game before an unrelated setting unless the next sample intentionally depends on the current method. Save and verify that baseline from disk using the same checks.

## Exit-Per-Case Fallback

If a confirmed in-game save does not update a complete, stable config until shutdown, stop the continuous loop for that game/version. For each remaining case, save and confirm the UI value, fully close the game and launcher, re-detect the config, and parse twice from the saved state before marking `Pass (after-exit read)`. Do not retry live reads for every value once this behavior is established. If only a particular option requires a restart, use this fallback for that option and keep continuous reads for options that still save reliably while running.

## Dependency Order

Use this order unless the game UI requires another:

1. Resolution and screen mode
2. V-Sync and frame limit
3. Dynamic resolution
4. Upscaling method
5. Upscaling mode for each applicable method
6. Frame generation for each applicable method
7. Quick preset, while checking whether independent settings remain independent

When changing a parent setting alters child options, rescan available options and extend the matrix. Do not flatten dependent choices into one global list.

## Pass and Stop Rules

A read case passes when the game UI value matches two parses of the same complete, stable saved config snapshot, either in-session or after exit. Record which mode was used; in-session reads alone do not establish post-restart persistence.

Stop the current case and diagnose when:

- the game does not retain the selected value;
- a saved change is not visible in the owned config, or the config is partial or unstable while the game is running;
- more than the expected config ownership boundary changes;
- parser output changes an unrelated setting;
- the config becomes unreadable or disappears;
- cloud sync or a launcher may have overwritten the sample.

For a missing or unstable live save, switch to the exit-per-case fallback if closing the game reveals the saved value; otherwise diagnose before continuing. Continue to other isolated cases only after returning to a known baseline.

## Completion

Read validation is complete only when:

- every advertised schema field is Pass or justified N/A;
- every finite enum needed by the writer has an observed retail mapping;
- dependencies are documented;
- parser tests cover each observed representation;
- after all cases, the tester saves one representative final state, fully exits, relaunches the game once, confirms the value in the UI, then exits again; fresh config detection and two parses agree with that final state. If it does not persist, investigate affected in-session results rather than marking them restart-verified;
- a final unchanged-state parse is stable across two consecutive reads.

The single final restart checks the selected final state, not the persistence of every earlier case. Keep the per-case `in-session` versus `after-exit` evidence distinct, and never treat read validation as authorization to write game files. Update `COLLECT.txt` and `01-read-evidence/read-comparison.txt` with the matrix. Tell the user which fields passed, failed, remain unsampled, and the exact next in-game change.