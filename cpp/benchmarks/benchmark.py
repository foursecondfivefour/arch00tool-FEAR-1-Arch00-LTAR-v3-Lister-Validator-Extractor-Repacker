#!/usr/bin/env python3
"""Benchmark both tools on a generated LTAR v3 archive; never touches game files."""
import argparse
import hashlib
import os
from pathlib import Path
import random
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import zlib

PYTHON_TOOL = Path(__file__).resolve().parents[2] / 'arch00tool.py'
MIB = 1024 * 1024


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return number


def make_archive(path, count, size):
    # A reproducible mixture of raw and zlib payloads, half compressible and
    # half pseudorandom. One file at a time is held in memory.
    rng = random.Random(8300)
    names = bytearray(b'assets\0')
    offsets = []
    for index in range(count):
        offsets.append(len(names))
        names.extend(f'{index:06}.bin\0'.encode())
    data_start = 48 + len(names) + count * 32 + 16
    expected = {}
    records = bytearray()
    with path.open('wb') as archive:
        archive.write(b'\0' * data_start)
        for index in range(count):
            half = size // 2
            data = rng.randbytes(half) + bytes([index % 251]) * (size - half)
            expected[f'{index:06}.bin'] = hashlib.sha256(data).digest()
            payload = zlib.compress(data, 6) if index % 2 else data
            offset = archive.tell()
            archive.write(payload)
            records.extend(struct.pack('<IQQQI', offsets[index], offset, len(payload), len(data), 6 if index % 2 else 0))
        archive.seek(0)
        archive.write(struct.pack('<12I', int.from_bytes(b'LTAR', 'little'), 3, len(names), 1, count, 0, 0, 0, 0, 0, 0, 0))
        archive.write(names)
        archive.write(records)
        archive.write(struct.pack('<IIII', 0, 0, 0, count))
    return expected


def verify_tree(root, expected):
    files = {p.name: p for p in (root / 'assets').iterdir() if p.is_file()}
    all_files = [p for p in root.rglob('*') if p.is_file()]
    if set(files) != set(expected) or len(all_files) != len(expected):
        raise RuntimeError(f'extracted filenames differ in {root}')
    for name, digest in expected.items():
        h = hashlib.sha256()
        with files[name].open('rb') as f:
            for chunk in iter(lambda: f.read(MIB), b''):
                h.update(chunk)
        if h.digest() != digest:
            raise RuntimeError(f'extracted data mismatch: {name}')


def execute(command):
    start = time.perf_counter()
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    elapsed = time.perf_counter() - start
    if result.returncode:
        raise RuntimeError(f'{command[0]} failed ({result.returncode}): {result.stderr}\n{result.stdout}')
    return elapsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpp', required=True, type=Path, help='path to arch00tool-cpp executable')
    parser.add_argument('--files', type=positive, default=48)
    parser.add_argument('--size-kib', type=positive, default=1024, help='unpacked KiB per file')
    parser.add_argument('--repeat', type=positive, default=3)
    parser.add_argument('--jobs', type=positive, default=4, help='C++ test/extract worker count (1–64)')
    parser.add_argument('--workdir', type=Path, help='parent for a new temporary directory, e.g. a selected drive')
    args = parser.parse_args()
    if args.jobs > 64 or args.files > 10000 or args.files * args.size_kib > 1024 * 1024:
        parser.error('jobs must be <= 64, files <= 10000, total unpacked size <= 1 GiB')
    exe = args.cpp.resolve()
    if not exe.is_file():
        parser.error('C++ executable does not exist')
    size = args.size_kib * 1024
    total = size * args.files
    with tempfile.TemporaryDirectory(prefix='arch00-bench-', dir=args.workdir) as temp:
        root = Path(temp); archive = root / 'synthetic.Arch00'
        expected = make_archive(archive, args.files, size)
        implementations = [('Python', [sys.executable, str(PYTHON_TOOL)], []),
                           ('C++ single', [str(exe)], ['--jobs', '1']),
                           (f'C++ {args.jobs} jobs', [str(exe)], ['--jobs', str(args.jobs)])]
        print(f'Synthetic archive: {args.files} files, {total / MIB:.2f} MiB unpacked, {archive.stat().st_size / MIB:.2f} MiB stored')
        print(f'Repetitions: {args.repeat}; workdir: {root}; timings include process startup and filesystem cache effects')
        print('Median wall time; throughput is unpacked MiB/s, not disk throughput.')
        for label, command, jobs in implementations:
            for mode in ('test', 'extract', 'repack'):
                # Repack has no jobs option; avoid reporting the same single-threaded operation twice.
                if mode == 'repack' and jobs and jobs[-1] != '1':
                    continue
                samples = []
                for iteration in range(args.repeat):
                    target = root / f'result-{iteration}'
                    if mode == 'test':
                        cmd = command + ['test', str(archive)] + jobs
                    elif mode == 'extract':
                        cmd = command + ['extract', str(archive), str(target)] + jobs
                    else:
                        cmd = command + ['repack', str(archive), str(target)]
                    samples.append(execute(cmd))
                    if mode == 'extract':
                        verify_tree(target, expected)
                        shutil.rmtree(target)
                    elif mode == 'repack':
                        # Verify independently using the original Python extractor, outside the timed section.
                        verify_dir = root / f'verify-{iteration}'
                        execute([sys.executable, str(PYTHON_TOOL), 'extract', str(target), str(verify_dir)])
                        verify_tree(verify_dir, expected)
                        shutil.rmtree(verify_dir)
                        target.unlink()
                median = statistics.median(samples)
                print(f'{label:14} {mode:7} {median:8.3f} s  {total / MIB / median:9.1f} MiB/s')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f'benchmark error: {exc}', file=sys.stderr)
        raise SystemExit(1)
