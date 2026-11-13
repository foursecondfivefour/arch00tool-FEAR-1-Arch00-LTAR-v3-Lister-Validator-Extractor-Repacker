#!/usr/bin/env python3
"""Create one release ZIP from an already tested CMake GUI build."""
import argparse
from pathlib import Path
import zipfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--build', required=True, type=Path)
p.add_argument('--platform', required=True, choices=('windows', 'linux'))
p.add_argument('--output', required=True, type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
exe = '.exe' if a.platform == 'windows' else ''
bindir = a.build / 'Release' if a.platform == 'windows' else a.build
files = [(bindir / ('arch00tool-cpp' + exe), 'arch00tool-cpp' + exe, 0o755),
         (bindir / ('arch00tool-gui' + exe), 'arch00tool-gui' + exe, 0o755),
         (root / 'RELEASE.md', 'README.md', 0o644)]
for src, _, _ in files:
    if not src.is_file():
        p.error(f'missing build output: {src}')
a.output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(a.output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for src, name, mode in files:
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = (0o100000 | mode) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, src.read_bytes())
print(a.output)
