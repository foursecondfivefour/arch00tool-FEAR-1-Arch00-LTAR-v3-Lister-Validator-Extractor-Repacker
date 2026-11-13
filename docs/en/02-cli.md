**English | [Русский](../ru/02-cli.md)**

# Command-line reference

[Contents](../../README.md) · [Getting started](01-quickstart.md) · [Limitations](05-safety.md)

General syntax: `python arch00tool.py COMMAND ...`. Command options follow the command name. For individual help, run e.g. `python arch00tool.py extract --help`.

## `list ARCHIVE [-v]`

Reads metadata and prints archive size, version, name-table size, folder and file-record counts, three flags, and raw GUID bytes in hex. Each entry shows `stored_size -> unpacked_size`, `raw` when the compression field is 0 or `method=N` otherwise, and its full path. `-v`/`--verbose` additionally shows the folder-name list. File offsets are **not printed**. Payloads are not decoded or checked; an unknown method may be displayed without an error.

## `test ARCHIVE [--compression auto|raw] [-v]`

Parses metadata and processes every entry into the system null sink. In `auto` (default), 0 means copy stored bytes, 1–9 means a zlib stream; other values on nonempty entries cause an error. `raw` forces copying stored bytes regardless of the field and checks neither compressed streams nor size equality. A zero `stored_size` requires zero `unpacked_size`. Nonzero sizes may differ for raw entries. `-v` reports progress to stderr every 1,000 checked nonempty entries; processing stops at the first error. Archive CRC is not checked.

## `extract ARCHIVE OUTPUT [--pattern PATTERN] [--compression auto|raw] [-v]`

Creates the output directory if necessary, selects entries using an optional case-sensitive `fnmatchcase` pattern against the full archive name, and extracts in offset order. Without a pattern, all entries are selected. No matches is a successful extraction of zero files. Compression modes are as for `test`; `raw` outputs stored bytes, which may not be usable as an extracted resource. `-v` reports progress every 1,000 files and at the last file. Files are opened exclusively: existing files are not overwritten. On error, previously created files and a partially written file remain.

## `test-all DIRECTORY [--compression auto|raw]`

Tests immediate files with a case-insensitive `.Arch00` suffix, sorted by case-insensitive name. Per-archive processing errors print `FAIL` and processing continues; totals are printed at the end. No archives is an error. Unlike `test`, there is no `-v` option.

## `extract-all DIRECTORY OUTPUT [--compression auto|raw] [--skip-existing] [-v]`

Finds archives as `test-all` does. Each is first extracted into `OUTPUT/NAME.Arch00.extracted.incomplete`, then the directory is renamed to `OUTPUT/NAME.Arch00.extracted`. Failed extraction leaves the incomplete directory for diagnosis; inspect and manually remove or move it before retrying. An existing final destination aborts the command unless `--skip-existing` is used, in which case it is skipped without checking its contents. An existing `.incomplete` aborts even with `--skip-existing` if the final directory is absent. Errors during individual archive processing are accumulated, but these preflight conflicts abort the whole run.

## `repack ARCHIVE OUTPUT [--replace-dir DIRECTORY]`

Creates a new archive without modifying the source. Without replacements, it copies stored entry payloads; if a regular file exists at a matching path under the replacement directory, its bytes are used, both sizes are set to the file size, and compression is set to 0. Missing replacements are ignored; extra files are not added. Prints the entry count, total stored bytes, and replacement count. Existing output and `OUTPUT.partial` are rejected. SHA-256 is compared for every stored range against the source or replacement, but zlib validity and game compatibility are not checked. See [repacking details](04-internals.md#repacking).

## Exit codes and streams

- `0`: success, including no pattern matches or skipped destinations.
- `1`: `test-all` or `extract-all` completed with per-archive errors.
- `2`: an `argparse` argument error or a top-level handled archive, filesystem, or overflow error.

Summaries generally go to stdout; progress and top-level errors go to stderr. Batch `FAIL` lines go to stdout. Not all exceptions are caught: unexpected Python errors may produce a traceback.
