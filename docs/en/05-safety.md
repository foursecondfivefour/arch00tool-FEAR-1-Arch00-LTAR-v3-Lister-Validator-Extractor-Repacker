**English | [Русский](../ru/05-safety.md)**

# Safety, limitations, and troubleshooting

[Contents](../../README.md) · [Commands](02-cli.md)

## What to expect and what not to assume

- The tool checks entry bounds, folder file counts, signature, version, referenced strings, and zlib streams during normal testing/extraction. It does not check CRC, header flags, overlapping ranges, the validity of game resource contents, or game compatibility. `list` does not check payloads; `repack` checks copying, not decompression. Run `test` before and after rebuilding.
- `safe_output_path` prevents several lexical path traversals, but **is not complete protection against untrusted archives**: existing symlinks in the output tree may redirect writes outside it; links in the replacement tree may also point outside. Use new private directories without links and prevent other processes from changing them during operation. Duplicate names or names that normalize to one path, as well as case differences, may cause conflicts.
- Empty segments and `.` are removed, not rejected; `..`, colons, absolute paths, and an empty resulting path are forbidden. The check does not cover all Windows device-name, filename, or link behavior. Existence checks followed by renaming are not race-proof: avoid shared directories. On some systems `rename` can replace a file created by another process after the check.
- Extraction is not atomic: previously extracted files and possibly a partially written file remain on error. `extract-all` leaves `.incomplete`; `repack` tries to remove `.partial` on ordinary errors, but a crash can leave it behind. Inspect remnants before manually removing them.
- Table limits do not bound archive size, extracted data size, or decompression memory. Disk/memory exhaustion and decompression bombs are possible. Work with trusted copies, limit environment resources, and check free disk space.
- Repacking does not create names, remove files, or compress replacements. `crc_enabled` is copied as-is; a game requiring additional checks or special metadata may reject the result. Support for other LTAR versions or related games is not guaranteed.

## Common messages

| Message | Possible cause and action |
|---|---|
| `invalid signature` / `unsupported LTAR version` | Not a supported LTAR v3, or damaged file; check the source. |
| `truncated ...` / `metadata tables end ... beyond archive size` | Truncated or invalid file/table; restore the original. |
| `string offset ... outside name table` / `not NUL-terminated` | Invalid name reference; check the original archive. |
| `folder ... extends past the file table` / `folder records account for ...` | Folder file counts do not match the table; check format and source. |
| `data range ... exceeds archive size` | Offset or length is out of bounds. |
| `unrecognized compression field` | Method unsupported in `auto`; `--compression raw` allows inspection of stored bytes but does not validate or decompress them. |
| `zlib failed`, `compressed stream ended ...`, `trailing bytes`, `produced ... expected` | Damage or incompatible interpretation of the stream/size. A successful `raw` run does not validate contents. |
| `unsafe archive path` | Name fails lexical checks; investigate the archive without disabling safeguards for unknown data. |
| `File exists` / `destination already exists` / `temporary output already exists` | Choose a new path, or inspect and manually remove a previous run's remnants. `--skip-existing` applies only to completed `extract-all` destinations. |
| `points into metadata` | The repacker forbids data starting inside tables even if basic parsing accepted the range. |
| `payload verification failed` | Copied bytes do not match; check the disk and ensure the source and replacements did not change while running. |
| `no .Arch00 archives found` | Check the directory and extension; the search is not recursive. |
| `replaced=0` | No paths matched: check replacement-directory layout, case, and names. This is not an error. |

Keep the complete message and command when diagnosing problems (omit personal paths when posting publicly). Use `list -v` to investigate structure and `test`, not `--compression raw`, to check payload format.
