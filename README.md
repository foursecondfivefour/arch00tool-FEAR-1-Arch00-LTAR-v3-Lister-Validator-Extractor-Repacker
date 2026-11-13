**English | [Русский](docs/ru/README.md)**

# arch00tool

A single-file Python utility for listing, validating, extracting, and rebuilding **LTAR v3 / `.Arch00`** archives, including those used by F.E.A.R. It uses only the Python standard library and requires Python 3.10 or newer.

```bash
python arch00tool.py list Some.Arch00 -v
python arch00tool.py test Some.Arch00
python arch00tool.py extract Some.Arch00 extracted/ --pattern '*.dds'
python arch00tool.py repack Some.Arch00 Some.modded.Arch00 --replace-dir mod/
python arch00tool.py test Some.modded.Arch00
```

The source archive is not modified. Repacking preserves unchanged file payloads, but **does not necessarily produce a byte-for-byte copy of the whole archive**. Replacement files are stored uncompressed; compatibility with a particular game is not guaranteed. Keep backups.

## Documentation

- [Getting started and modding workflow](docs/en/01-quickstart.md)
- [Command-line reference](docs/en/02-cli.md)
- [LTAR v3 layout as implemented](docs/en/03-format.md)
- [Internals and function reference](docs/en/04-internals.md)
- [Safety, limitations, and troubleshooting](docs/en/05-safety.md)

These pages describe the current `arch00tool.py`, not a complete official format specification. Built-in help is available through `python arch00tool.py --help` and `python arch00tool.py <command> --help`.
