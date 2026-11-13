# fear-arch00-tool — experimental alpha

These are pre-release builds of the C++ port. Back up your files and work on copies. The tool has not yet been validated against original F.E.A.R. archives or in-game; the GUI has not been tested interactively on all platforms. Extract files only into a new private directory without symlinks. Cancellation or errors may leave partially extracted files; inspect incomplete output before removing it. Repack verifies copied bytes but cannot guarantee game compatibility. See the repository documentation for full safety limitations.

## Windows x86-64

Extract the ZIP and run `arch00tool-cpp.exe` from PowerShell or Command Prompt, or run `arch00tool-gui.exe` and open the complete URL printed in its console on the same machine. The C++ runtime distributed with Windows or Microsoft Visual C++ Redistributable may be required.

## Linux x86-64

Extract the ZIP. Make the executables runnable if your extraction program does not preserve permissions (`chmod +x arch00tool-cpp arch00tool-gui`). In a terminal run `./arch00tool-cpp` or `./arch00tool-gui` and open the printed URL locally. Built on Ubuntu 22.04; requires compatible glibc (2.35 or newer), libstdc++, and zlib runtime. Other Linux distributions and CPU architectures are not guaranteed to work.

## GUI and CLI

The GUI binds to loopback only. Its URL contains a session token: do not share it. Closing the browser does not stop the server; press Ctrl+C in its terminal. The interface lets you browse local paths, list, test, extract, and repack. Use a new output path for repacking. Test the rebuilt archive separately. The CLI prints usage when run without arguments; the number of workers is set with `--jobs N` (1–64).

Progress counts entries, not bytes; cancellation is cooperative and can be delayed during metadata parsing, blocking filesystem operations, syncing, or publication. Batch operations can leave completed outputs and `.incomplete` directories. Refer to the full C++ README and bilingual docs in the repository for details.
