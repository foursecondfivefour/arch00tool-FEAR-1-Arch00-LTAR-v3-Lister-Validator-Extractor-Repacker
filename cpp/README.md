# Experimental C++ port (incomplete)

This is a first-stage LTAR v3 metadata parser with `list`, `test`, `extract`, `test-all`, `extract-all`, and `repack` commands. Raw and zlib payloads are processed in bounded chunks; extraction creates files exclusively and rejects lexical traversal paths. The parser and extractor have been tested on generated fixtures on Linux, not on real game archives or Windows.

**Not yet a replacement for the Python tool:** GUI, parallelism and complete CLI compatibility are not implemented. Pattern matching supports `*`, `?` and character classes, but has not been exhaustively compared with Python for unusual patterns. Extraction does not protect against existing directory symlinks or races: use a new private output directory. Partial files remain on error. Do not use untrusted archives. Performance has not been benchmarked.

## Build and test

Requires a C++17 compiler, CMake, and zlib development files. If zlib is not installed, CMake downloads a pinned zlib release from GitHub. Tests require Python 3.

```sh
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build --config Release
ctest --test-dir cpp/build --output-on-failure -C Release
cpp/build/arch00tool-cpp list archive.Arch00 -v
cpp/build/arch00tool-cpp test archive.Arch00
cpp/build/arch00tool-cpp extract archive.Arch00 output --pattern '*.dds'
cpp/build/arch00tool-cpp test-all archives
cpp/build/arch00tool-cpp extract-all archives extracted --skip-existing
cpp/build/arch00tool-cpp repack archive.Arch00 modded.Arch00 --replace-dir mod
```

`test` and `extract` accept `--compression auto|raw`. The existing Python tool remains authoritative until command behavior and real archives have been tested against the port.

`repack` copies unchanged stored payloads and stores replacements raw, then compares all rebuilt metadata and payload bytes against their sources before publication. It does not validate zlib or game compatibility; use `test` separately. Publication uses a hard link to prevent overwriting an existing output; filesystems without hard-link support cannot publish. The output and `.partial` must not exist. Keep source and replacements unchanged while running. Repacking may remove gaps and unreferenced trailing data.
