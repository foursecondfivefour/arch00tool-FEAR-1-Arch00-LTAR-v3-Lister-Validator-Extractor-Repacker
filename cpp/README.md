# Experimental C++ port (incomplete)

This is a first-stage LTAR v3 metadata parser with `list`, `test`, `extract`, `test-all`, `extract-all`, and `repack` commands. Raw and zlib payloads are processed in bounded chunks; extraction creates files exclusively and rejects lexical traversal paths. The parser and extractor have been tested on generated fixtures on Linux, not on real game archives or Windows.

**Not yet a replacement for the Python tool:** Complete CLI compatibility has not been established. An experimental browser GUI is available separately, with cooperative progress and cancellation. Pattern matching supports `*`, `?` and character classes, but has not been exhaustively compared with Python for unusual patterns. Extraction does not protect against existing directory symlinks or races: use a new private output directory. Partial files remain on error. Do not use untrusted archives. See the synthetic benchmark below; its results do not establish real-game performance.

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
cpp/build/arch00tool-cpp repack archive.Arch00 modded.Arch00 --replace-dir mod --jobs 4
```

`test` and `extract` accept `--compression auto|raw`. `test`, `test-all`, `extract`, `extract-all` and `repack` also accept `--jobs N` (1–64, default 1) to process separate entries concurrently, with independent file handles and bounded per-worker buffers. Batch archives are still processed sequentially. Parallel extraction rejects duplicate normalized paths and file/directory target conflicts before writing; case-folding aliases may still collide at exclusive file creation. On failure, in-flight workers may finish and partial output remains. On error, parallel workers stop as soon as practical; which error is reported may differ from sequential order. Multiple readers can be slower on a hard disk or when I/O is the bottleneck. The existing Python tool remains authoritative until command behavior and real archives have been tested against the port.

`repack` copies unchanged stored payloads and stores replacements raw, then compares all rebuilt metadata and payload bytes against their sources before publication. With `--jobs` greater than 1, independent workers copy separate entries into disjoint output ranges; metadata processing and the byte-for-byte verification pass remain sequential. Small archives, one large entry, or slow storage may not benefit. It does not validate zlib or game compatibility; use `test` separately. Publication uses a hard link to prevent overwriting an existing output; filesystems without hard-link support cannot publish. The output and `.partial` must not exist. Keep source and replacements unchanged while running. Repacking may remove gaps and unreferenced trailing data.

## Experimental browser GUI (no Qt)

Build the optional GUI with a C++17 compiler, CMake and Git:

```sh
cmake -S cpp -B cpp/build-gui -DCMAKE_BUILD_TYPE=Release -DARCH00_BUILD_GUI=ON
cmake --build cpp/build-gui --config Release
ctest --test-dir cpp/build-gui --output-on-failure -C Release
./cpp/build-gui/arch00tool-gui
```

On Windows, run the generated `arch00tool-gui.exe` from the configuration directory (for example `cpp\build-gui\Release\arch00tool-gui.exe` with Visual Studio). CMake fetches pinned versions of cpp-httplib and nlohmann/json from GitHub for this optional target; the CLI-only build does not fetch them.

Copy the complete URL printed by the program into a browser **on the same computer**. Enter local paths manually or use the in-app directory browser; the interface can list (first 2,000 entries), test, extract, and repack one archive, or test/extract all archives in an input directory. Single-archive extraction supports an optional case-sensitive pattern; batch extraction supports skipping existing destinations. It does not automatically open the browser. For repacking, select the output folder and append a new archive filename manually. The picker lists at most 2,000 items per directory and runs with the same local filesystem privileges as the tool. The browser shows the current phase and completed-entry count, and offers cooperative cancellation while waiting. Progress resets for each phase and each archive in batch operations; it is not a byte-based percentage or time estimate. Metadata parsing, filesystem calls, syncing and publication may delay cancellation. During repack publication cancellation is rejected as too late. Extraction cancellation leaves completed and partially written files; batch extraction may retain completed archive directories and an `.incomplete` directory. Repack attempts to remove its `.partial` file when cancelled before publication, but a crash or cleanup failure can leave it behind. Batch errors are reported after processing; an incomplete extraction directory remains after failures and must be inspected and removed or moved manually before retrying. Stop the server with Ctrl+C after use. Closing the tab does not stop it.

The server binds only to IPv4 loopback, checks the host and origin, and requires a per-run token for operations. The URL contains that token: do not share it, expose the server to a network, or run it in a shared or untrusted local environment. It is not a multi-user service or a sandbox. A local process or browser extension with access to the token can invoke operations with the user's filesystem privileges. Source and destination safety limitations described above also apply. The GUI has been built and its HTTP API, including cooperative cancellation, tested on Linux using synthetic archives; Windows, interactive browsers, and real game archives have not been tested.

## Synthetic performance benchmark

After building the C++ CLI, run:

```sh
python cpp/benchmarks/benchmark.py --cpp cpp/build/arch00tool-cpp --files 48 --size-kib 1024 --repeat 3 --jobs 4
```

The benchmark creates a temporary LTAR v3 archive with deterministic mixed raw/zlib entries, runs Python and C++ `test`, `extract` and `repack`, and reports median wall times and nominal unpacked MiB/s. It SHA-256-checks extracted files and independently extracts every repacked archive with the Python tool, outside the timed section. Temporary files are deleted when the run ends. `--workdir` selects the parent directory for testing a particular drive; the temporary directory requires enough free disk space for multiple copies of the generated data. The benchmark limits the generated unpacked size to 1 GiB.

Measurements include process startup and are influenced by OS caching, CPU, filesystem, compression ratio, number/size of files and background activity. The runs occur in a fixed order and are not cold-cache or statistically controlled. Nominal unpacked MiB/s is not disk throughput, especially for repack which copies stored bytes. Use multiple runs and representative real archives before drawing performance conclusions. The tool never modifies real archives. Benchmark generation requires Python 3.9 or newer.

## Continuous integration and Unicode paths

`.github/workflows/cpp.yml` configures, builds, and runs the C++ tests with and without the optional GUI on Linux and Windows GitHub runners. The Windows CLI receives command-line arguments as UTF-16 and converts them to UTF-8 for the archive core; names printed by the CLI are UTF-8. Automated Unicode-path fixtures cover input, output, patterns, replacements, and batch operations. Windows console font and terminal encoding settings may still affect display. CI does not establish compatibility with actual game archives or test the GUI in an interactive browser.
