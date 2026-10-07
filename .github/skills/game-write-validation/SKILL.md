---
name: game-write-validation
description: "Run pre-game real-file write validation for every writable graphics option after parser validation. Use when preparing a new game's write candidate, finding Apply Failed cases before launching the game, exercising each setting/value against real config files, validating backup/read-back/restore, or building write evidence. Keywords: write validation, Apply Failed, real config test, option matrix, backup restore, write candidate."
argument-hint: "Provide the game title, platform, version, and approved writable settings"
user-invocable: true
disable-model-invocation: false
---

# Game Write Validation

Exercise every legal writer option against the real game config while the game is closed, before asking a tester to launch the game. This phase finds file-level Apply failures; it does not prove in-game persistence.

## Non-Negotiable Entry Criteria

Do not perform real writes until all are true:

1. `game-read-validation` is complete for the exact retail game/version/platform.
2. Parser mappings and option dependencies are backed by in-game samples and focused tests.
3. The game and non-Steam launchers are fully closed and cloud sync is paused. An open Steam client is a warning, not a blocker, when the tester confirms its cloud sync remains paused.
4. The exact version and structural fingerprint match a `write_candidate: verified` or `write_verified: verified` rule.
5. The rule allowlist contains only settings approved for this test.
6. The tester explicitly confirms real-file testing may begin.
7. A complete independent baseline export exists outside the rolling automatic-backup directory.

Never weaken a fingerprint, version, allowlist, consent gate, or read-back check to make a test pass.

## Establish the Baseline

1. Run detection and `python cli.py parse "<game>"` from live disk.
2. Create a full restore package:

   `python cli.py export --games "<game>" --output "<private-path>/baseline.json"`

3. Confirm the package includes every detected config owned by this game.
4. Record SHA-256 hashes for every detected file and any known auxiliary file.
5. Test the restore package once before the matrix: make no intentional setting change, import it, then confirm every baseline hash and parser value is unchanged.
6. Store baseline packages, configs, hashes, and logs only in ignored/private evidence paths.

If baseline restore cannot reproduce the exact starting state, stop. Do not begin matrix testing.

## Build the Complete Write Matrix

Use parser `available_options`, the exact rule allowlist, and dependency rules to enumerate cases.

- Test every selectable value for every writable setting, excluding only `—`, `N/A`, and the current value when it would be a no-op.
- For a parent-dependent setting, test valid combinations separately. Examples: each upscaling mode under each method; frame generation under every method that exposes it.
- Include compatibility transformations deliberately implemented by the product, such as a screen-mode adjustment required by frame generation.
- Keep each case atomic: one setting/value or one explicitly coupled combination.
- Give every case a stable ID such as `upscaling-xess__frame-generation-auto`.

## Real-File Test Loop

For every matrix case, without launching the game:

1. Import the independent baseline package.
2. Re-detect live files and verify every baseline hash. If any differ, stop.
3. Run the non-writing smoke gate first:

   `python cli.py preflight "<game>" --settings '<case-json>'`

4. If preflight fails, record `Preflight Fail`; do not perform real Apply for that case.
5. If preflight passes, perform the real guarded write:

   `python cli.py apply "<game>" --settings '<case-json>' --confirm-test-write`

6. Capture structured output and exit status. An exception, error result, skipped result, no files written, or GUI Apply Failed is `Apply Fail`.
7. Re-detect files and run `python cli.py parse "<game>"`.
8. Confirm every requested setting reads back as expected, including aliases and intentional coupled changes.
9. Compare hashes against baseline. Only rule-owned target files and documented auxiliary files may differ.
10. Import the independent baseline package immediately, even after Apply Fail.
11. Re-detect, parse, and verify every baseline hash and value exactly.
12. Record the result, then continue to the next isolated case.

The rolling backup under `%LOCALAPPDATA%/GameTuner/backups` is evidence and emergency rollback, not the matrix baseline. It may be replaced by later successful writes.

## Failure Policy

After `Preflight Fail` or `Apply Fail`:

- Preserve the error text, case JSON, parser output, and changed-file list.
- Restore the independent baseline.
- If restore and all hashes pass, mark only that case failed and continue with the next matrix case.
- Add a minimal automated regression test that reproduces the failed setting/value before fixing the writer.

Stop the entire matrix immediately when:

- baseline import or hash restoration fails;
- an unrelated file changes;
- the game or a non-Steam launcher starts; an open Steam client alone is a warning, but resumed cloud sync is a stop condition;
- cloud sync resumes;
- the fingerprint or game version changes;
- private config content would need to be exposed publicly.

Do not launch the game to investigate an Apply failure. Fix all file-level failures first.

## Result Table

Maintain `03-write-evidence/write-results.txt` with:

| Case ID | Setting JSON | Preflight | Apply | Parser read-back | Changed files allowed | Restore hash | Result |
|---|---|---|---|---|---|---|---|

Use `Pass`, `Fail`, or `Blocked`; include the exact normalized error code. Do not include raw config content or user-identifying paths.

## Promotion to In-Game Testing

A setting/value may proceed to manual in-game persistence testing only when:

- preflight passes;
- real Apply succeeds;
- parser read-back matches;
- only allowed files changed;
- independent baseline restoration is exact.

After the entire matrix passes at file level, give the tester a reduced in-game plan. Prefer one representative value per independent setting plus every dependency-sensitive combination. For each, verify game UI effect, restart persistence, parser read-back, and restoration.

Do not promote a rule to `write_verified` from this skill alone. Promotion still requires successful in-game persistence and restore evidence.