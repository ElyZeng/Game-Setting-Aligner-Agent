---
name: game-read-validation
description: "Guide interactive parser validation for a PC game's graphics settings. Use when starting a new game validation, validating read support, sampling config mappings, checking whether the parser follows in-game setting changes, or asking the tester to change one game option, save, and exit. Keywords: read validation, parser test, game settings sampling, config mapping, read evidence."
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

| Setting | Baseline game value | Baseline parser value | Test value | Parser after change | Files changed | Result |
|---|---|---|---|---|---|---|

Choose values that discriminate enum mappings. For finite option sets, eventually sample every visible option. For numeric ranges, sample boundary and representative values. Respect dependencies such as upscaling method controlling mode or frame generation.

## Interactive Loop

For each test case:

1. Tell the tester exactly one setting and one target value to select.
2. Ask the tester to apply/save in the game, return to the settings screen to confirm the displayed value, then fully close the game and launcher.
3. Stop and wait for the tester's confirmation. Do not parse while the game may still be running.
4. Re-detect files from disk; do not trust an earlier GUI snapshot.
5. Run `python cli.py parse "<game>"` and compare the requested value with parser output.
6. Compare file hashes to identify which files changed. If mapping is unclear, inspect only relevant graphics key/value pairs and redact private data.
7. Record the observed mapping as evidence, not as an assumption.
8. If parser output is wrong, create a focused fixture from anonymized relevant fields, add a failing parser test, implement the smallest fix, and rerun the focused and full suites.
9. Repeat the same in-game sample after a parser fix before marking it passed.
10. Restore the baseline in the game before moving to an unrelated setting unless the next sample intentionally depends on the current method.

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

A case passes only when the game UI value and parser value agree after the game fully exits.

Stop the current case and diagnose when:

- the game does not retain the selected value;
- more than the expected config ownership boundary changes;
- parser output changes an unrelated setting;
- the config becomes unreadable or disappears;
- cloud sync or a launcher may have overwritten the sample.

Continue to other isolated cases only after returning to a known baseline.

## Completion

Read validation is complete only when:

- every advertised schema field is Pass or justified N/A;
- every finite enum needed by the writer has an observed retail mapping;
- dependencies are documented;
- parser tests cover each observed representation;
- a final unchanged-state parse is stable across two consecutive reads.

Update `COLLECT.txt` and `01-read-evidence/read-comparison.txt` with the matrix. Tell the user which fields passed, failed, remain unsampled, and the exact next in-game change.