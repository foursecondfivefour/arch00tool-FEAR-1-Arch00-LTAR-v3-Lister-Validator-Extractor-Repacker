# arch00tool

**A read-only lister, validator, extractor — and a safe repacker — for FEAR's `.Arch00` (LTAR v3) archives.**

`arch00tool` is a single-file, dependency-free Python 3 CLI for working with the
`Arch00` archive format used by *F.E.A.R.* and related Monolith titles. It parses
the LTAR v3 header, name, file, and folder tables, validates every payload
(zlib level 1–9 or raw/`compression == 0`), and extracts files while refusing
unsafe archive paths. A `repack` subcommand rebuilds an archive without
touching stored payloads, and can optionally substitute individual files from
an extracted directory — with full metadata round-trip and per-payload SHA-256
verification before the output is published.

---

### Features

- **List** archive contents (names, offsets, stored vs. unpacked sizes, compression mode)
- **Test** metadata and payload integrity without writing output (`auto` or forced `raw` compression)
- **Extract** one archive (with optional `fnmatch` pattern) or a whole directory of `.Arch00` files
- **Repack** an archive byte-for-byte (metadata-preserving) with optional per-file replacement from an extracted tree
- **Safety by default**
  - NUL-checked name table, bounded table sizes and entry counts
  - Strict path-traversal protection (`..`, drive letters, absolute paths, empty segments)
  - Repack is fully verified (rebuilt tables must equal the originals; each stored payload is hashed)
  - Never overwrites existing output files or `.partial` temporaries
- **Zero dependencies** — uses only the Python 3 standard library
- **Streaming I/O** — 4 MiB chunks, safe for large media entries
- **Bulk helpers** — `test-all` and `extract-all` for whole-directory workflows

---

### Quick start

```bash
# List contents
python arch00tool.py list Some.Arch00 -v

# Validate all payloads
python arch00tool.py test Some.Arch00 -v

# Extract a single archive
python arch00tool.py extract Some.Arch00 out/ --pattern "*.dds" -v

# Validate / extract every .Arch00 in a directory
python arch00tool.py test-all ./archives
python arch00tool.py extract-all ./archives ./extracted --skip-existing

# Repack, optionally replacing selected files
python arch00tool.py repack Some.Arch00 Some.repacked.Arch00 --replace-dir ./mod
