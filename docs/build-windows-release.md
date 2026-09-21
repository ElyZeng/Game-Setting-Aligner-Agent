# Windows Release Build

Use `tools/build_windows_release.py` from the repository root. The command runs the full test suite, builds the PyInstaller bundle, creates the ZIP checksum, obtains the verification manifest assets, validates the manifest checksum, and fails unless all four release assets exist.

## From a local rules directory

```powershell
python tools/build_windows_release.py `
  --version 0.07.4 `
  --rules-dir release-assets/verification-rules-v1.2.1 `
  --output-dir release-output
```

## From a GitHub rules release

Requires GitHub CLI to be installed and authenticated:

```powershell
python tools/build_windows_release.py `
  --version 0.07.4 `
  --rules-release verification-rules-v1.2.1 `
  --output-dir release-output
```

## Required output

A successful build prints and creates exactly these release assets:

```text
release-output/Game-Setting-Aligner-Agent-windows-x64.zip
release-output/Game-Setting-Aligner-Agent-windows-x64.zip.sha256
release-output/verified-games.json
release-output/verified-games.json.sha256
```

The archive contains `Game-Setting-Aligner-Agent/Game-Setting-Aligner-Agent.exe`.

Upload all four files to the same GitHub Release. Do not publish the EXE assets alone: the application requires both verification manifest assets for **Check Rules**.

The command does not create or publish a GitHub Release. Review the test output and generated assets first, then upload them with the GitHub CLI or GitHub UI.

## Safety

- The build does not modify game settings.
- It does not require a clean Git worktree.
- It does not delete user validation evidence.
- Use a separate release branch/worktree for version bumps and release commits.
