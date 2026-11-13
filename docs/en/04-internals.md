**English | [Русский](../ru/04-internals.md)**

# Internals

[Contents](../../README.md) · [Format](03-format.md) · [Safety](05-safety.md)

The project consists of `arch00tool.py`. The “modules” below are logical parts of that file, not separate Python packages. It uses `argparse`, `fnmatch`, `hashlib`, `os`, `struct`, `sys`, `zlib`, `dataclasses`, and `pathlib`. Annotations are postponed via `from __future__ import annotations`.

## Constants and models

- `HEADER`, `FILE_ENTRY`, `FOLDER_ENTRY`: precompiled `struct.Struct` instances for the three structures; formats and sizes are in the [format guide](03-format.md).
- `HEADER_SIZE`: 48; `IO_CHUNK`: 4 MiB for reading/copying; `MAX_TABLE_BYTES`: 512 MiB for names; `MAX_ENTRIES`: 2 million for each count.
- `Arch00Error`: exception for format and safety-check failures.
- Immutable `Header`: `version`, `names_size`, `folder_count`, `file_count`, `retail`, `download`, `crc_enabled`, `guid` (16 raw bytes).
- Immutable `Entry`: full `name`, absolute `offset`, `stored_size`, `unpacked_size`, `compression`.

## Parsing

- `read_exact(file, size, what)` reads the requested bytes or raises `Arch00Error` with context.
- `read_c_string(blob, offset, what)` checks offset and NUL, decoding UTF-8 with CP1252 fallback.
- `parse_header(file, file_size)` reads the header at the current position, checks signature, version, limits, and metadata size, and returns `Header`.
- `parse_archive(path)` gets the size with `stat`, opens the archive, reads all three tables, and checks ranges and folder assignment. Returns `(Header, list[Entry], list[str])`; entries are in file-table order, not physical data order. This matters for replacement mapping during repacking.

## Paths and payload processing

- `safe_output_path(root, archive_name)` replaces `\` with `/`, removes empty components and `.`, then rejects an empty result, `..` components, colons, and absolute paths. Returns `root.joinpath(...)`; it does not `resolve` the path or check symbolic links.
- `copy_raw(archive, entry, output)` seeks to the offset and copies exactly `stored_size` bytes in chunks, returning the byte count; it does not compare `unpacked_size`.
- `inflate_zlib(archive, entry, output)` reads exactly the stored range, feeds chunks to `zlib.decompressobj`, writes the result, and checks declared size, stream EOF, and absence of `unused_data`. Zlib errors become `Arch00Error`. Decompressing one input chunk can produce substantially more than 4 MiB in memory; the read chunk is not a memory limit.
- `process_entry(archive, entry, output, force_raw=False)` handles zero stored length first, then chooses raw (including forced mode) or zlib for 1–9; other nonempty methods are rejected. Returns the number of bytes written.
- `extract_entries(path, output_root, entries, force_raw, verbose)` sorts entries by offset, creates parent directories and each file using `xb`, calls `process_entry`, and totals bytes. There is no rollback on failure.

## Repacking

- `archive_files(directory)` returns immediate regular files with a `.arch00` suffix, sorted by case-insensitive name.
- `copy_range(source, destination, source_offset, size, context)` and `file_digest(file, offset, size, context)` stream-copy a range and compute SHA-256 respectively; both use `read_exact`.
- `repack_archive(source_path, output_path, replacement_root=None)` returns `(entry_count, total_stored_size, replacement_count)` and performs these steps:
  1. Checks that source and output paths differ and the output does not exist; parses the source archive, then rereads the header and raw tables.
  2. For each file checks that the data start is not inside metadata, and if `replacement_root` is provided looks for a file at the safely normalized full name. A replacement becomes raw with both sizes set to the file size. Other entries retain sizes and method.
  3. Sorts entries by `(old offset, index)`, lays ranges tightly after the tables, and updates offsets (and, for replacements, sizes and method). The original header, name table, folder records, and other file-record fields are copied.
  4. Exclusively creates `OUTPUT.partial`, writes metadata and payloads, calls `flush` and `fsync`. It rechecks the header and compares the read-back file table to the newly constructed in-memory table, and the folder table to the original. Header and names are not byte-compared during verification.
  5. Compares SHA-256 for each new range with the corresponding source range or replacement file, then renames the temporary file to the output. On an exception caught within the writing block, it attempts to remove the temporary file.

This verifies copying integrity, not compression, CRC, metadata semantics, or game behavior. Re-layout removes unreferenced gaps/trailing data, and overlapping ranges are copied separately: whole-archive byte identity is not promised. Replacement size and data are read at different times, so files must not change while the tool runs.

## CLI and control flow

- `cmd_list`, `cmd_test`, `cmd_extract`, `cmd_repack`, `cmd_test_all`, `cmd_extract_all` implement their respective commands and return exit codes. Batch handlers catch per-archive errors and continue where supported.
- `make_parser()` builds an `argparse.ArgumentParser`, defines arguments, and binds functions through `set_defaults(func=...)`.
- `main()` parses arguments, calls `args.func(args)`, catches `Arch00Error`, `OSError`, `OverflowError`, and returns 2. The entry point calls `raise SystemExit(main())`. `argparse` handles its own argument errors.
