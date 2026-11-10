#!/usr/bin/env python3
"""Read-only lister, validator, and extractor for FEAR LTAR v3 Arch00 files."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path


HEADER = struct.Struct("<12I")
FILE_ENTRY = struct.Struct("<IQQQI")
FOLDER_ENTRY = struct.Struct("<IIII")
HEADER_SIZE = HEADER.size
IO_CHUNK = 4 * 1024 * 1024
MAX_TABLE_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 2_000_000


class Arch00Error(Exception):
    pass


@dataclass(frozen=True)
class Header:
    version: int
    names_size: int
    folder_count: int
    file_count: int
    retail: int
    download: int
    crc_enabled: int
    guid: bytes


@dataclass(frozen=True)
class Entry:
    name: str
    offset: int
    stored_size: int
    unpacked_size: int
    compression: int


def read_exact(file, size: int, what: str) -> bytes:
    data = file.read(size)
    if len(data) != size:
        raise Arch00Error(f"truncated {what}: expected {size} bytes, got {len(data)}")
    return data


def read_c_string(blob: bytes, offset: int, what: str) -> str:
    if offset < 0 or offset >= len(blob):
        raise Arch00Error(f"{what} string offset {offset} is outside name table")
    end = blob.find(b"\0", offset)
    if end < 0:
        raise Arch00Error(f"{what} string at offset {offset} is not NUL-terminated")
    try:
        return blob[offset:end].decode("utf-8")
    except UnicodeDecodeError:
        return blob[offset:end].decode("cp1252", errors="replace")


def parse_header(file, file_size: int) -> Header:
    raw = read_exact(file, HEADER_SIZE, "LTAR header")
    values = HEADER.unpack(raw)
    signature, version, names_size, folder_count, file_count = values[:5]
    if signature != int.from_bytes(b"LTAR", "little"):
        raise Arch00Error("invalid signature (expected LTAR)")
    if version != 3:
        raise Arch00Error(f"unsupported LTAR version {version}; expected 3")
    if names_size > MAX_TABLE_BYTES:
        raise Arch00Error(f"name table too large ({names_size} bytes)")
    if folder_count > MAX_ENTRIES or file_count > MAX_ENTRIES:
        raise Arch00Error("entry count exceeds safety limit")
    records_end = HEADER_SIZE + names_size + file_count * FILE_ENTRY.size + folder_count * FOLDER_ENTRY.size
    if records_end > file_size:
        raise Arch00Error(f"metadata tables end at {records_end}, beyond archive size {file_size}")
    return Header(
        version=version,
        names_size=names_size,
        folder_count=folder_count,
        file_count=file_count,
        retail=values[5],
        download=values[6],
        crc_enabled=values[7],
        guid=raw[32:48],
    )


def parse_archive(path: Path) -> tuple[Header, list[Entry], list[str]]:
    file_size = path.stat().st_size
    with path.open("rb") as file:
        header = parse_header(file, file_size)
        names = read_exact(file, header.names_size, "name table")
        records = read_exact(file, header.file_count * FILE_ENTRY.size, "file table")
        folder_blob = read_exact(file, header.folder_count * FOLDER_ENTRY.size, "folder table")
        entries: list[Entry] = []
        for index in range(header.file_count):
            name_offset, offset, stored_size, unpacked_size, compression = FILE_ENTRY.unpack_from(
                records, index * FILE_ENTRY.size
            )
            name = read_c_string(names, name_offset, f"file record {index}")
            if offset > file_size or stored_size > file_size - offset:
                raise Arch00Error(
                    f"file record {index} ({name!r}) data range [{offset}, {offset + stored_size}) "
                    f"exceeds archive size {file_size}"
                )
            entries.append(Entry(name, offset, stored_size, unpacked_size, compression))

        folders: list[str] = []
        folder_records = []
        for index in range(header.folder_count):
            record = FOLDER_ENTRY.unpack_from(folder_blob, index * FOLDER_ENTRY.size)
            name_offset, _unknown0, _unknown1, files_in_folder = record
            if files_in_folder > header.file_count:
                raise Arch00Error(f"folder record {index} has impossible file count {files_in_folder}")
            folders.append(read_c_string(names, name_offset, f"folder record {index}"))
            folder_records.append(record)

    # Folder records partition the file-record array in order; preserve empty records
    # in the parsed table while exposing only files with non-empty paths.
    current = 0
    full_entries: list[Entry] = []
    for folder, record in zip(folders, folder_records):
        count = record[3]
        end = current + count
        if end > len(entries):
            raise Arch00Error(f"folder {folder!r} extends past the file table")
        for entry in entries[current:end]:
            full_entries.append(Entry(
                name=f"{folder}\\{entry.name}" if folder else entry.name,
                offset=entry.offset,
                stored_size=entry.stored_size,
                unpacked_size=entry.unpacked_size,
                compression=entry.compression,
            ))
        current = end
    if current != len(entries):
        raise Arch00Error(f"folder records account for {current} of {len(entries)} file records")
    return header, full_entries, folders


def safe_output_path(root: Path, archive_name: str) -> Path:
    normalized = archive_name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if (not parts or any(part == ".." or ":" in part for part in parts)
            or normalized.startswith("/") or normalized.startswith("//")):
        raise Arch00Error(f"unsafe archive path: {archive_name!r}")
    return root.joinpath(*parts)


def copy_raw(archive, entry: Entry, output) -> int:
    remaining = entry.stored_size
    total = 0
    archive.seek(entry.offset)
    while remaining:
        chunk = read_exact(archive, min(IO_CHUNK, remaining), f"data for {entry.name}")
        output.write(chunk)
        total += len(chunk)
        remaining -= len(chunk)
    return total


def inflate_zlib(archive, entry: Entry, output) -> int:
    decompressor = zlib.decompressobj()
    remaining = entry.stored_size
    total = 0
    archive.seek(entry.offset)
    while remaining:
        chunk = read_exact(archive, min(IO_CHUNK, remaining), f"compressed data for {entry.name}")
        remaining -= len(chunk)
        try:
            decoded = decompressor.decompress(chunk)
        except zlib.error as exc:
            raise Arch00Error(f"zlib failed for {entry.name}: {exc}") from exc
        if decoded:
            total += len(decoded)
            if total > entry.unpacked_size:
                raise Arch00Error(f"{entry.name}: decompressed beyond declared size {entry.unpacked_size}")
            output.write(decoded)
    try:
        tail = decompressor.flush()
    except zlib.error as exc:
        raise Arch00Error(f"zlib flush failed for {entry.name}: {exc}") from exc
    if tail:
        total += len(tail)
        output.write(tail)
    if not decompressor.eof:
        raise Arch00Error(f"{entry.name}: compressed stream ended before zlib end marker")
    if total != entry.unpacked_size:
        raise Arch00Error(f"{entry.name}: produced {total} bytes, expected {entry.unpacked_size}")
    if decompressor.unused_data:
        raise Arch00Error(f"{entry.name}: {len(decompressor.unused_data)} trailing bytes after zlib stream")
    return total


def process_entry(archive, entry: Entry, output, force_raw: bool = False) -> int:
    if entry.stored_size == 0:
        if entry.unpacked_size != 0:
            raise Arch00Error(f"{entry.name}: empty stored data but declared output size {entry.unpacked_size}")
        return 0
    if force_raw or entry.compression == 0:
        # Some shipped entries (e.g. Bink media) have different metadata sizes
        # despite a zero compression level; preserve the stored payload verbatim.
        return copy_raw(archive, entry, output)
    if not 1 <= entry.compression <= 9:
        raise Arch00Error(
            f"{entry.name}: unrecognized compression field {entry.compression}; "
            "expected raw (0) or zlib compression level 1..9"
        )
    return inflate_zlib(archive, entry, output)


def cmd_list(args) -> int:
    path = Path(args.archive)
    header, entries, folders = parse_archive(path)
    print(f"Archive: {path}")
    print(f"Size: {path.stat().st_size} bytes; LTAR v{header.version}")
    print(f"Names: {header.names_size}; folders: {header.folder_count}; file records: {header.file_count}")
    print(f"Header flags: retail={header.retail} download={header.download} crc={header.crc_enabled}")
    print(f"GUID bytes: {header.guid.hex()}")
    for entry in entries:
        marker = "raw" if entry.compression == 0 else f"method={entry.compression}"
        print(f"{entry.stored_size:>12} -> {entry.unpacked_size:<12} {marker:<10} {entry.name}")
    if args.verbose:
        print(f"Folder records: {folders!r}")
    return 0


def cmd_test(args) -> int:
    path = Path(args.archive)
    header, entries, _folders = parse_archive(path)
    checked = 0
    with path.open("rb", buffering=IO_CHUNK) as archive, open(os.devnull, "wb") as sink:
        for entry in entries:
            if entry.stored_size == 0:
                if entry.unpacked_size:
                    raise Arch00Error(f"{entry.name}: zero stored length, non-zero unpacked length")
                checked += 1
                continue
            process_entry(archive, entry, sink, args.compression == "raw")
            checked += 1
            if args.verbose and checked % 1000 == 0:
                print(f"validated {checked}/{len(entries)} entries", file=sys.stderr)
    print(f"OK: validated {checked} files in {path} (LTAR v{header.version})")
    return 0


def cmd_extract(args) -> int:
    path = Path(args.archive)
    output_root = Path(args.output)
    header, entries, _folders = parse_archive(path)
    output_root.mkdir(parents=True, exist_ok=True)
    selected = [entry for entry in entries if not args.pattern or fnmatch.fnmatchcase(entry.name, args.pattern)]
    total_bytes = extract_entries(path, output_root, selected, args.compression == "raw", args.verbose)
    print(f"Extracted {len(selected)} files ({total_bytes} bytes) from LTAR v{header.version} to {output_root}")
    return 0


def extract_entries(path: Path, output_root: Path, entries: list[Entry], force_raw: bool, verbose: bool) -> int:
    total_bytes = 0
    # Reading in ascending archive-offset order avoids unnecessary seeks while output
    # files remain in their original directory layout.
    ordered = sorted(entries, key=lambda entry: entry.offset)
    with path.open("rb", buffering=IO_CHUNK) as archive:
        for index, entry in enumerate(ordered, 1):
            destination = safe_output_path(output_root, entry.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb", buffering=IO_CHUNK) as out:
                total_bytes += process_entry(archive, entry, out, force_raw)
            if verbose and (index % 1000 == 0 or index == len(ordered)):
                print(f"[{index}/{len(ordered)}] {entry.name}", file=sys.stderr)
    return total_bytes


def archive_files(directory: Path) -> list[Path]:
    return sorted((p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".arch00"), key=lambda p: p.name.lower())


def copy_range(source, destination, source_offset: int, size: int, context: str) -> None:
    source.seek(source_offset)
    remaining = size
    while remaining:
        chunk = read_exact(source, min(IO_CHUNK, remaining), context)
        destination.write(chunk)
        remaining -= len(chunk)


def file_digest(file, offset: int, size: int, context: str) -> bytes:
    file.seek(offset)
    remaining = size
    digest = hashlib.sha256()
    while remaining:
        chunk = read_exact(file, min(IO_CHUNK, remaining), context)
        digest.update(chunk)
        remaining -= len(chunk)
    return digest.digest()


def repack_archive(source_path: Path, output_path: Path, replacement_root: Path | None = None) -> tuple[int, int, int]:
    if source_path.resolve() == output_path.resolve(strict=False):
        raise Arch00Error("output path must differ from source archive")
    if output_path.exists():
        raise Arch00Error(f"output already exists; refusing to overwrite: {output_path}")

    source_size = source_path.stat().st_size
    _parsed_header, parsed_entries, _parsed_folders = parse_archive(source_path)
    with source_path.open("rb", buffering=IO_CHUNK) as source:
        header = parse_header(source, source_size)
        names = read_exact(source, header.names_size, "name table")
        raw_records = bytearray(read_exact(source, header.file_count * FILE_ENTRY.size, "file table"))
        folders = read_exact(source, header.folder_count * FOLDER_ENTRY.size, "folder table")
        metadata_end = HEADER_SIZE + header.names_size + len(raw_records) + len(folders)
        data_entries = []
        for index in range(header.file_count):
            record_offset = index * FILE_ENTRY.size
            name_offset, data_offset, stored_size, unpacked_size, compression = FILE_ENTRY.unpack_from(
                raw_records, record_offset
            )
            read_c_string(names, name_offset, f"file record {index}")
            if data_offset < metadata_end:
                raise Arch00Error(f"file record {index} points into metadata at offset {data_offset}")
            if data_offset > source_size or stored_size > source_size - data_offset:
                raise Arch00Error(f"file record {index} data range exceeds source archive")
            original_stored_size = stored_size
            replacement = None
            if replacement_root is not None:
                candidate = safe_output_path(replacement_root, parsed_entries[index].name)
                if candidate.is_file():
                    replacement = candidate
                    stored_size = candidate.stat().st_size
                    unpacked_size = stored_size
                    compression = 0
            data_entries.append((index, data_offset, original_stored_size, stored_size, unpacked_size, compression, replacement))

        # Preserve every table byte except each file's data offset. Lay payloads
        # out in their original physical order to keep source reads sequential.
        next_offset = metadata_end
        new_offsets = {}
        for index, old_offset, _original_size, stored_size, _unpacked_size, _compression, _replacement in sorted(
                data_entries, key=lambda item: (item[1], item[0])):
            new_offsets[index] = next_offset
            next_offset += stored_size
        for index, _old_offset, _original_size, stored_size, unpacked_size, compression, _replacement in data_entries:
            record_offset = index * FILE_ENTRY.size
            name_offset = FILE_ENTRY.unpack_from(raw_records, record_offset)[0]
            FILE_ENTRY.pack_into(
                raw_records, record_offset,
                name_offset, new_offsets[index], stored_size, unpacked_size, compression,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_name(output_path.name + ".partial")
        if temp_path.exists():
            raise Arch00Error(f"temporary output already exists; refusing to overwrite: {temp_path}")
        try:
            with temp_path.open("xb", buffering=IO_CHUNK) as output:
                source.seek(0)
                copy_range(source, output, 0, HEADER_SIZE, "LTAR header")
                output.write(names)
                output.write(raw_records)
                output.write(folders)
                ordered = sorted(data_entries, key=lambda item: (item[1], item[0]))
                for index, old_offset, original_stored_size, stored_size, _unpacked_size, _compression, replacement in ordered:
                    if replacement is None:
                        copy_range(source, output, old_offset, original_stored_size, f"payload for file record {index}")
                    else:
                        with replacement.open("rb", buffering=IO_CHUNK) as replacement_file:
                            copy_range(replacement_file, output, 0, stored_size, f"replacement for {parsed_entries[index].name}")
                output.flush()
                os.fsync(output.fileno())

            # Verify that the rebuilt tables resolve to byte-identical stored payloads.
            temp_size = temp_path.stat().st_size
            with temp_path.open("rb", buffering=IO_CHUNK) as rebuilt:
                parse_header(rebuilt, temp_size)
                rebuilt.seek(HEADER_SIZE + header.names_size)
                rebuilt_records = read_exact(rebuilt, header.file_count * FILE_ENTRY.size, "rebuilt file table")
                if rebuilt_records != raw_records:
                    raise Arch00Error("rebuilt file table did not round-trip")
                rebuilt.seek(HEADER_SIZE + header.names_size + len(raw_records))
                rebuilt_folders = read_exact(rebuilt, len(folders), "rebuilt folder table")
                if rebuilt_folders != folders:
                    raise Arch00Error("rebuilt folder table changed")
                payload_bytes = 0
                with source_path.open("rb", buffering=IO_CHUNK) as original:
                    for index, old_offset, original_stored_size, stored_size, _unpacked_size, _compression, replacement in data_entries:
                        new_record = FILE_ENTRY.unpack_from(rebuilt_records, index * FILE_ENTRY.size)
                        new_offset = new_record[1]
                        if replacement is None:
                            original_entry = parsed_entries[index]
                            original_hash = file_digest(original, old_offset, original_stored_size, f"source file record {index}")
                        else:
                            with replacement.open("rb", buffering=IO_CHUNK) as replacement_file:
                                original_hash = file_digest(replacement_file, 0, stored_size, f"replacement for file record {index}")
                        rebuilt_hash = file_digest(rebuilt, new_offset, stored_size, f"rebuilt file record {index}")
                        if original_hash != rebuilt_hash:
                            raise Arch00Error(f"payload verification failed for file record {index}")
                        payload_bytes += stored_size
            temp_path.rename(output_path)
            replaced_count = sum(item[-1] is not None for item in data_entries)
            return header.file_count, payload_bytes, replaced_count
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise


def cmd_repack(args) -> int:
    source = Path(args.archive)
    output = Path(args.output)
    replacement_root = Path(args.replace_dir) if args.replace_dir else None
    count, payload_bytes, replaced_count = repack_archive(source, output, replacement_root)
    print(f"Repacked and verified {count} files ({payload_bytes} payload bytes); replaced={replaced_count}")
    print(f"Source: {source}")
    print(f"Output: {output}")
    return 0


def cmd_test_all(args) -> int:
    paths = archive_files(Path(args.directory))
    if not paths:
        raise Arch00Error(f"no .Arch00 archives found in {args.directory}")
    failures = []
    for index, path in enumerate(paths, 1):
        print(f"[{index}/{len(paths)}] Testing {path.name}", file=sys.stderr)
        try:
            header, entries, _folders = parse_archive(path)
            with path.open("rb", buffering=IO_CHUNK) as archive, open(os.devnull, "wb") as sink:
                for entry in entries:
                    process_entry(archive, entry, sink, args.compression == "raw")
            print(f"OK {path.name}: {len(entries)} files, LTAR v{header.version}")
        except (Arch00Error, OSError, OverflowError) as exc:
            failures.append((path.name, str(exc)))
            print(f"FAIL {path.name}: {exc}")
    print(f"Tested {len(paths)} archives; passed={len(paths)-len(failures)} failed={len(failures)}")
    return 1 if failures else 0


def cmd_extract_all(args) -> int:
    paths = archive_files(Path(args.directory))
    if not paths:
        raise Arch00Error(f"no .Arch00 archives found in {args.directory}")
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    failures = []
    skipped = 0
    for index, path in enumerate(paths, 1):
        destination = output_root / f"{path.name}.extracted"
        if destination.exists():
            if args.skip_existing:
                skipped += 1
                print(f"[{index}/{len(paths)}] SKIP existing {destination}", file=sys.stderr)
                continue
            raise Arch00Error(f"destination already exists; refusing to overwrite: {destination}")
        partial = output_root / f"{path.name}.extracted.incomplete"
        if partial.exists():
            raise Arch00Error(f"incomplete destination already exists; refusing to overwrite: {partial}")
        try:
            header, entries, _folders = parse_archive(path)
            partial.mkdir()
            print(f"[{index}/{len(paths)}] Extracting {path.name} ({len(entries)} files)", file=sys.stderr)
            total_bytes = extract_entries(path, partial, entries, args.compression == "raw", args.verbose)
            partial.rename(destination)
            print(f"OK {path.name}: extracted {len(entries)} files, {total_bytes} bytes to {destination}")
        except (Arch00Error, OSError, OverflowError) as exc:
            failures.append((path.name, str(exc)))
            print(f"FAIL {path.name}: {exc}")
    print(f"Processed {len(paths)} archives; skipped={skipped} failed={len(failures)}")
    return 1 if failures else 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List, test, and extract FEAR LTAR v3 Arch00 archives.")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="list archive entries")
    listing.add_argument("archive")
    listing.add_argument("-v", "--verbose", action="store_true")
    listing.set_defaults(func=cmd_list)

    test = sub.add_parser("test", help="validate metadata and file payloads without writing extracted files")
    test.add_argument("archive")
    test.add_argument("--compression", choices=("auto", "raw"), default="auto",
                      help="auto uses field 0=raw and levels 1..9=zlib; raw overrides the field")
    test.add_argument("-v", "--verbose", action="store_true")
    test.set_defaults(func=cmd_test)

    extract = sub.add_parser("extract", help="extract files to a separate output directory")
    extract.add_argument("archive")
    extract.add_argument("output")
    extract.add_argument("--pattern", help="optional case-sensitive fnmatch pattern")
    extract.add_argument("--compression", choices=("auto", "raw"), default="auto",
                         help="auto uses field 0=raw and levels 1..9=zlib; raw overrides the field")
    extract.add_argument("-v", "--verbose", action="store_true")
    extract.set_defaults(func=cmd_extract)

    test_all = sub.add_parser("test-all", help="validate every .Arch00 in a directory")
    test_all.add_argument("directory")
    test_all.add_argument("--compression", choices=("auto", "raw"), default="auto")
    test_all.set_defaults(func=cmd_test_all)

    extract_all = sub.add_parser("extract-all", help="extract every .Arch00 into a separate subfolder")
    extract_all.add_argument("directory")
    extract_all.add_argument("output")
    extract_all.add_argument("--compression", choices=("auto", "raw"), default="auto")
    extract_all.add_argument("--skip-existing", action="store_true")
    extract_all.add_argument("-v", "--verbose", action="store_true")
    extract_all.set_defaults(func=cmd_extract_all)

    repack = sub.add_parser("repack", help="rebuild an LTAR v3 archive without changing stored payloads")
    repack.add_argument("archive", help="source .Arch00 archive")
    repack.add_argument("output", help="new output path; existing files are never overwritten")
    repack.add_argument("--replace-dir", help="replace matching archive paths from this extracted directory")
    repack.set_defaults(func=cmd_repack)
    return parser


def main() -> int:
    args = make_parser().parse_args()
    try:
        return args.func(args)
    except (Arch00Error, OSError, OverflowError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
