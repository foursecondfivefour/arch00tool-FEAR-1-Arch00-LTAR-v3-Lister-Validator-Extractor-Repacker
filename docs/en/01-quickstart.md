**English | [Русский](../ru/01-quickstart.md)**

# Getting started and modding

[Contents](../../README.md) · [Commands](02-cli.md) · [Format](03-format.md)

## Preparation

You need Python 3.10+ with the standard library, including `zlib`. No third-party packages are required. Run commands from the directory containing the script, or give the full path to `arch00tool.py`. On Windows, use `py` instead of `python` if needed. Quote paths containing spaces. Allow disk space for extracted files, the new archive, and the temporary file. Do not change input files while the tool is running.

## A cautious workflow

1. Back up the original archive and game files. Work on a copy outside the game directory.
2. Inspect the contents and check the payloads:

   ```bash
   python arch00tool.py list original.Arch00 -v
   python arch00tool.py test original.Arch00 -v
   ```

3. Extract to a new directory:

   ```bash
   python arch00tool.py extract original.Arch00 extracted
   ```

4. Edit a resource with an appropriate tool. This script does not edit textures, models, or game-specific formats. Create a separate `mod` directory containing **only modified files**, retaining their archive paths. For example, for `Textures\wall.dds`, place the replacement at `mod/Textures/wall.dds`. Case matters especially on case-sensitive filesystems. Check the actual path against `list` output.
5. Build and test a new archive:

   ```bash
   python arch00tool.py repack original.Arch00 modded.Arch00 --replace-dir mod
   python arch00tool.py list modded.Arch00
   python arch00tool.py test modded.Arch00
   ```

   Check `replaced=N`: missing replacement files are silently ignored, and extra files under `mod` are not added to the archive. Renaming, adding, and removing entries are not supported. Passing the entire `extracted` directory replaces every matching file, even unchanged ones; a separate directory of changes is preferable.
6. If needed, extract the rebuilt archive into another empty directory and compare the changed files. Only then try it in the game, after backing up. Installation and archive priority depend on the game and are not established here. A successful `test` does not prove the game will accept the archive or resource.

## Selective extraction and batches

```bash
python arch00tool.py extract original.Arch00 textures --pattern '*.dds' -v
python arch00tool.py test-all archives
python arch00tool.py extract-all archives extracted-all --skip-existing
```

The case-sensitive `fnmatchcase` pattern is matched against the full archive name, which uses backslashes; `*` can also match directory separators. Quote the pattern to prevent shell expansion. Batch commands search only the specified directory, not its descendants.
