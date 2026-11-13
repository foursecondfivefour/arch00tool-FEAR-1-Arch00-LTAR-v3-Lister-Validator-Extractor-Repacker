# Experimental C++ port (incomplete)

This is a first-stage LTAR v3 metadata parser with `list`, `test`, `extract`, `test-all`, `extract-all`, and `repack` commands. Raw and zlib payloads are processed in bounded chunks; extraction creates files exclusively and rejects lexical traversal paths. The parser and extractor have been tested on generated fixtures on Linux, not on real game archives or Windows.

**Not yet a replacement for the Python tool:** Parallel repacking and complete CLI compatibility are not implemented. An experimental browser GUI is available separately, but it does not implement live progress or cancellation. Pattern matching supports `*`, `?` and character classes, but has not been exhaustively compared with Python for unusual patterns. Extraction does not protect against existing directory symlinks or races: use a new private output directory. Partial files remain on error. Do not use untrusted archives. See the synthetic benchmark below; its results do not establish real-game performance.

## Build and test

Requires a C++17 compiler, CMake, and zlib development files. If zlib is not installed, CMake downloads a pinned zlib release from GitHub. Tests require Python 3.

```sh
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build --config Release
ctest --test-dir cpp/build --output-on-failure -C Release
cpp/build/arch00tool-cpp list archive.Arch00 -v
cpp/build/arch00tool-cpp test archive.Arch00 --jobs 4
cpp/build/arch00tool-cpp extract archive.Arch00 output --pattern '*.dds' --jobs 4
cpp/build/arch00tool-cpp test-all archives
cpp/build/arch00tool-cpp extract-all archives extracted --skip-existing
cpp/build/arch00tool-cpp repack archive.Arch00 modded.Arch00 --replace-dir mod
```

`test` and `extract` accept `--compression auto|raw`. `test`, `test-all`, `extract` and `extract-all` also accept `--jobs N` (1–64, default 1) to process separate entries concurrently, with independent file handles and bounded per-worker buffers. Batch archives are still processed sequentially. Parallel extraction rejects duplicate normalized paths and file/directory target conflicts before writing; case-folding aliases may still collide at exclusive file creation. On failure, in-flight workers may finish and partial output remains. On error, parallel workers stop as soon as practical; which error is reported may differ from sequential order. Multiple readers can be slower on a hard disk or when I/O is the bottleneck. The existing Python tool remains authoritative until command behavior and real archives have been tested against the port.

`repack` copies unchanged stored payloads and stores replacements raw, then compares all rebuilt metadata and payload bytes against their sources before publication. It does not validate zlib or game compatibility; use `test` separately. Publication uses a hard link to prevent overwriting an existing output; filesystems without hard-link support cannot publish. The output and `.partial` must not exist. Keep source and replacements unchanged while running. Repacking may remove gaps and unreferenced trailing data.

## Experimental browser GUI (no Qt)

Build the optional GUI with a C++17 compiler, CMake and Git:

```sh
cmake -S cpp -B cpp/build-gui -DCMAKE_BUILD_TYPE=Release -DARCH00_BUILD_GUI=ON
cmake --build cpp/build-gui --config Release
ctest --test-dir cpp/build-gui --output-on-failure -C Release
./cpp/build-gui/arch00tool-gui
```

On Windows, run the generated `arch00tool-gui.exe` from the configuration directory (for example `cpp\build-gui\Release\arch00tool-gui.exe` with Visual Studio). CMake fetches pinned versions of cpp-httplib and nlohmann/json from GitHub for this optional target; the CLI-only build does not fetch them.

Copy the complete URL printed by the program into a browser **on the same computer**. Enter local paths manually; the interface can list (first 2,000 entries), test, extract, and repack one archive, or test/extract all archives in an input directory. Single-archive extraction supports an optional case-sensitive pattern; batch extraction supports skipping existing destinations. It does not automatically open the browser, browse files, show live progress or cancel an operation. The browser waits for each operation to finish. Batch errors are reported after processing; an incomplete extraction directory remains after failures and must be inspected and removed or moved manually before retrying. Stop the server with Ctrl+C after use. Closing the tab does not stop it.

The server binds only to IPv4 loopback, checks the host and origin, and requires a per-run token for operations. The URL contains that token: do not share it, expose the server to a network, or run it in a shared or untrusted local environment. It is not a multi-user service or a sandbox. A local process or browser extension with access to the token can invoke operations with the user's filesystem privileges. Source and destination safety limitations described above also apply. The GUI has been built and its HTTP API tested on Linux using synthetic archives; Windows, interactive browsers, and real game archives have not been tested.

## Synthetic performance benchmark

After building the C++ CLI, run:

```sh
python cpp/benchmarks/benchmark.py --cpp cpp/build/arch00tool-cpp --files 48 --size-kib 1024 --repeat 3 --jobs 4
```

The benchmark creates a temporary LTAR v3 archive with deterministic mixed raw/zlib entries, runs Python and C++ `test`, `extract` and single-worker `repack`, and reports median wall times and nominal unpacked MiB/s. It SHA-256-checks extracted files and independently extracts every repacked archive with the Python tool, outside the timed section. Temporary files are deleted when the run ends. `--workdir` selects the parent directory for testing a particular drive; the temporary directory requires enough free disk space for multiple copies of the generated data. The benchmark limits the generated unpacked size to 1 GiB.

Measurements include process startup and are influenced by OS caching, CPU, filesystem, compression ratio, number/size of files and background activity. The runs occur in a fixed order and are not cold-cache or statistically controlled. Nominal unpacked MiB/s is not disk throughput, especially for repack which copies stored bytes. Use multiple runs and representative real archives before drawing performance conclusions. The tool never modifies real archives. Benchmark generation requires Python 3.9 or newer.
