# Full Game Validation

Use this procedure to decide whether one game can be marked as fully supported
for scanning, reading, writing, backup, restore, and diagnostic export. The
tester does not need Python, a terminal, the CLI, or prior Game Tuner
experience. Tester actions use only `GameTuner.exe`, the Game Tuner GUI, the
game UI, and Windows File Explorer.

## Roles

- **Maintainer**: prepares the test build and verification rule, then reviews
  the evidence.
- **Tester**: follows the numbered steps on a Windows test machine.

Do not claim full support from a successful scan alone. A game is fully
supported only after every required section below passes.

## Maintainer Preparation

Before sending the test package:

1. Confirm the exact game title, store platform, game version, and configuration
   fingerprint.
2. Confirm read support from an anonymized diagnostic package, then publish a
   `write_candidate` rule for that exact combination. Do not use `*` for the
   version or fingerprint in a write-test rule.
3. Confirm the rule declares only settings that the parser and writer support.
4. Provide the tester with `Game-Setting-Aligner-Agent-windows-x64.zip` and the expected SHA-256
   of that ZIP through the approved private channel.
5. Tell the tester which game settings are expected to be supported.

For benchmark/demo tools, record the exact tool name and do not treat a passing
result as support for the corresponding full game. For Battle.net games, the
GUI must first detect the Battle.net installation and the settings file must be
available offline rather than only as a cloud placeholder.

Record these values before testing:

| Field | Expected value |
|---|---|
| Game | |
| Platform | |
| Game version | |
| Game Tuner build/commit | |
| Test ZIP SHA-256 | |
| Verification manifest version | |
| Expected supported settings | |

## Tester Safety Rules

1. Use a test account or a machine where changing game settings is acceptable.
2. Fully close the game and its launcher before every write or restore step.
3. Temporarily disable cloud synchronization for the test game. Cloud sync can
   overwrite local settings and invalidate the result.
4. Do not delete files under `%LOCALAPPDATA%\GameTuner` during the test.
5. Do not share diagnostic ZIP files publicly. Use only the private channel
   specified by the maintainer.
6. Stop immediately if Game Tuner identifies the wrong game, wrong platform,
   wrong configuration files, or anything other than `write_candidate` for
   this test.

## 1. Install and Start

1. Download the ZIP only from the private location supplied by the maintainer.
2. Extract the entire ZIP to a new folder. Do not run the EXE from inside the
   ZIP and do not copy only `GameTuner.exe` out of the folder.
3. Run `GameTuner.exe`.
4. If Windows SmartScreen appears, record a screenshot and stop unless the
   maintainer explicitly approved continuing.

Pass when:

- The application opens without Python being installed.
- No PowerShell or console window flashes during startup.
- The application does not crash.

## 2. Update Verification Rules

1. Select **Check Rules**.
2. Confirm that the update succeeds.
3. If it fails, do not continue to write testing. Send this file to the
   maintainer:

   `%LOCALAPPDATA%\GameTuner\logs\verification.log`

Pass when:

- The update reports success.
- The target game status is updated after scanning finishes.

The maintainer checks the downloaded manifest version, checksum, and previous
cache after receiving the test evidence. The tester does not need to open or
interpret JSON files.

## 3. Scan and Identify the Game

1. Wait until scanning and configuration detection finish.
2. Find the target game by its exact title and platform.
3. Confirm the row reports at least one configuration file.
4. Expand the row.

Pass when:

- The correct game and platform appear exactly once.
- The status is `write_candidate: verified`.
- The row contains settings rather than an empty panel.

Stop when:

- The game is absent, duplicated, assigned to the wrong platform, or marked
   `candidate`, `read_verified`, `write_verified`, or `deprecated`.
- The application reports no configuration files.

## 4. Verify Read Support

1. Start the game and open its graphics/video settings page.
2. Record every visible value listed below, then fully close the game again.
3. Compare the game UI values with the values shown by Game Tuner.

| Setting | Game UI | Game Tuner | Result |
|---|---|---|---|
| Resolution | | | Pass / Fail / N/A |
| Screen mode | | | Pass / Fail / N/A |
| V-Sync | | | Pass / Fail / N/A |
| Frame limit | | | Pass / Fail / N/A |
| Dynamic resolution | | | Pass / Fail / N/A |
| Upscaling | | | Pass / Fail / N/A |
| Frame generation | | | Pass / Fail / N/A |
| Quality preset | | | Pass / Fail / N/A |

Use `N/A` only when the game genuinely does not offer that setting. Use `Fail`
when the game offers it but Game Tuner is missing it or shows the wrong value.

Pass when every advertised setting matches the game UI.

## 5. Verify Metadata-Only Diagnostic Output

1. Select only the target game.
2. Select **Export Diagnostics**.
3. Leave **Include anonymized config content** unchecked.
4. Confirm files containing `input`, `key`, `binding`, `save`, `log`, `cache`,
   and empty files are not selected by default.
5. Select **Create ZIP**.

Pass when:

- A ZIP is created under `%LOCALAPPDATA%\GameTuner\reports`.
- The GUI reports a successful export.
- The tester sends the ZIP to the maintainer without opening or modifying it.

The maintainer confirms the ZIP contains `manifest.json`, contains no files
under `configs/`, and contains no device name, username, Steam ID, token,
password, or account identifier.

## 6. Verify Content Diagnostic Output

1. Open **Export Diagnostics** again.
2. Enable **Include anonymized config content**.
3. Use **Recommended** selections. Review every selected filename.
4. Do not manually select input, key binding, save, log, cache, or unrelated
   files.
5. Select **Create ZIP**, review the final warning, and confirm.

Pass when:

- The GUI reports a successful export.
- The tester can provide the ZIP through the approved private channel without
   opening or manually editing it.

The maintainer confirms only selected files appear under `configs/`, paths and
contents are anonymized, and the ZIP remains below 10 MB.

## 7. Verify Write Consent Gate

1. Do not select **Enable Test Writes** yet.
2. Change one dropdown value in Game Tuner and select **Apply Changes**.
3. Confirm that the write is rejected with `test_write_consent_required` or an
   equivalent **Write Disabled** message.
4. Select **Enable Test Writes** and decline the confirmation once. Repeat the
   write attempt and confirm it remains blocked.
5. Select **Enable Test Writes** again, read the warning, and accept.

Pass when no file is changed before explicit consent and the button changes to
**Disable Test Writes** only after acceptance.

## 8. Verify Each Writable Setting

Test one setting at a time. Use a reversible value that is different from the
baseline. Do not test resolution first; begin with V-Sync or frame limit when
available.

For each advertised writable setting:

1. Confirm the game and launcher are fully closed.
2. Record the original value.
3. Choose one different value in Game Tuner.
4. Select **Apply Changes** and record the result message.
5. Start the game and confirm its UI shows the new value.
6. Close the game completely.
7. Start Game Tuner again and confirm it reads the new value.
8. Use Game Tuner to restore the original value.
9. Start the game once more and confirm the original value is restored.

| Setting | Original | Test value | Applied | Persisted | Restored |
|---|---|---|---|---|---|
| Resolution | | | Pass / Fail | Pass / Fail | Pass / Fail |
| Screen mode | | | Pass / Fail | Pass / Fail | Pass / Fail |
| V-Sync | | | Pass / Fail | Pass / Fail | Pass / Fail |
| Frame limit | | | Pass / Fail | Pass / Fail | Pass / Fail |
| Dynamic resolution | | | Pass / Fail | Pass / Fail | Pass / Fail |
| Upscaling | | | Pass / Fail | Pass / Fail | Pass / Fail |
| Frame generation | | | Pass / Fail | Pass / Fail | Pass / Fail |
| Quality preset | | | Pass / Fail | Pass / Fail | Pass / Fail |

Pass when every advertised writable setting is applied, survives a game launch,
is read back correctly, and can be restored.

## 9. Verify Automatic Backup

After a successful write, use Windows File Explorer to open:

`%LOCALAPPDATA%\GameTuner\backups\<game-name>`

Pass when:

- The directory exists.
- It contains a copy of every configuration file modified by that write.
- A later successful write replaces the previous automatic backup only after
  the new write passes read-back validation.

Do not deliberately corrupt a real game file to test automatic rollback. The
rollback failure path belongs in automated tests or a disposable fixture, not
on a tester's installed game.

## 10. Verify Export and Import Restore

1. Close the game and launcher.
2. Select only the target game and select **Export Selected**.
3. Save the JSON package in a temporary folder.
4. Change one already-verified setting using Game Tuner.
5. Select **Import Config**, choose the exported JSON, and confirm the warning.
6. Start the game and verify the original setting has been restored.

Pass when the JSON export is created, import reports success, and the game UI
returns to the original value.

## 11. Cleanup

1. Restore every game setting to its original value.
2. Re-enable cloud synchronization if it was disabled.
3. Select **Disable Test Writes**.
4. Keep the automatic backup until the maintainer accepts the result.

## 12. Promote the Support Rule

This step is performed by the maintainer after reviewing all tester evidence.

1. Confirm every required area in the final table is `Pass`.
2. Confirm the tested game version and configuration fingerprint still match
   the `write_candidate` rule.
3. Change only that exact rule from `write_candidate` to `write_verified`.
4. Publish a new verification manifest and checksum.
5. Have the tester select **Check Rules** once more and confirm the game now
   displays `write_verified: verified`.

If any required area fails, keep the rule as `write_candidate` or downgrade it
to `read_verified`; do not add the game to the full support list.

## Result Report

Send the maintainer:

- This checklist with every result filled in.
- Screenshots of the game UI and matching Game Tuner values.
- `%LOCALAPPDATA%\GameTuner\logs\verification.log`.
- Both diagnostic ZIP files through the approved private channel.
- The exported backup JSON through the approved private channel.
- A short description of every failure, including the exact step number and
  whether the game or launcher was running.

The tester does not need to run commands, inspect JSON, calculate hashes, or
interpret log contents. The maintainer performs those checks after receiving
the files.

Final decision:

| Area | Result |
|---|---|
| EXE startup | Pass / Fail |
| Rule update | Pass / Fail |
| Game detection | Pass / Fail |
| Read all advertised settings | Pass / Fail |
| Metadata-only diagnostic output | Pass / Fail |
| Content diagnostic output | Pass / Fail |
| Consent gate | Pass / Fail |
| Write all advertised settings | Pass / Fail |
| Automatic backup | Pass / Fail |
| Export/import restore | Pass / Fail |

Mark the game **fully supported** only when every required area is `Pass` and a
new manifest has promoted the exact tested rule to `write_verified`. Any wrong
value, unverified write, missing backup, failed restore, privacy leak, or crash
is a failed validation and must be fixed before updating the support list.