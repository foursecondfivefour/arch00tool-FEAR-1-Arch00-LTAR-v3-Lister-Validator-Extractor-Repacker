**English | [Русский](../ru/03-format.md)**

# LTAR v3: the model implemented by the script

[Contents](../../README.md) · [Internals](04-internals.md)

This describes the code, not an official specification. Unknown fields have not been decoded; do not assume all games or LTAR variants are compatible. All numbers are little-endian; `I` is unsigned 32-bit, `Q` unsigned 64-bit. Offsets are bytes from the beginning of the file.

## Overall layout

```text
0             header: 48 bytes (<12I)
48            name table: names_size bytes
              file_count file records, 32 bytes each (<IQQQI)
              folder_count folder records, 16 bytes each (<IIII)
              data regions at offsets from file records
```

The parser does not require data to follow tables immediately, be ordered, or be non-overlapping. It checks only the bounds of each range; the repacker additionally rejects ranges starting inside metadata. Gaps and data outside entry ranges are not preserved during repacking.

## Header (`<12I`, 48 bytes)

| Offset | Field | Use |
|---:|---|---|
| 0 | signature | Must be the bytes `LTAR`. |
| 4 | version | Must be 3. |
| 8 | names_size | Name-table size, at most 512 MiB. |
| 12 | folder_count | Folder-record count, at most 2,000,000. |
| 16 | file_count | File-record count, at most 2,000,000. |
| 20 | retail | Flag/value printed; semantics not checked. |
| 24 | download | Likewise. |
| 28 | crc_enabled | Printed; CRC is neither checked nor recalculated. |
| 32–47 | guid | 16 original bytes, printed as hex without interpreting GUID field byte order. |

The parser also checks that the end of all tables does not exceed the archive size. The 512 MiB limit applies only to the name table, not the combined tables or payloads.

## Names

The table is a byte array; file and folder records contain offsets into it. A string ends with a NUL byte. The offset must be inside the table and a NUL must follow it. UTF-8 is attempted first; on a decoding error CP1252 with replacement is used. Only referenced strings are checked; the script does not prove the whole table valid or require an offset to point at the start of a previously allocated string.

## File record (`<IQQQI`, 32 bytes)

| Offset in record | Size | Meaning |
|---:|---:|---|
| 0 | 4 | Name offset in the name table. |
| 4 | 8 | Absolute offset of stored data in the archive. |
| 12 | 8 | `stored_size`: number of stored bytes. |
| 20 | 8 | `unpacked_size`: declared output size. |
| 28 | 4 | `compression`: 0 raw, 1–9 zlib according to this implementation. |

Each range is checked using `offset <= archive_size` and `stored_size <= archive_size - offset`. A zero-size entry may point to the end of the archive. Payloads are checked separately by `test` and `extract`, not during basic parsing.

## Folder record (`<IIII`, 16 bytes)

The first integer is a folder-name offset; the next two are preserved as unknowns; the last is the number of files in that folder. The script assigns file records to folders sequentially in table order. The counts must sum to `file_count`; running past the file table is forbidden. The full path is `folder_name + backslash + file_name`, or just the file name when the folder name is empty. Empty folders remain in the folder list but do not create file entries. Names may already contain separators; the script does not interpret folder hierarchy beyond this concatenation.
