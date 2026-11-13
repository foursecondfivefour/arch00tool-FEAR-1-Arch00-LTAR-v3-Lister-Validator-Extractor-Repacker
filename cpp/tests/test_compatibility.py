"""Differential tests against arch00tool.py on generated LTAR v3 archives."""
import importlib.util
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import zlib

CPP = Path(sys.argv[1])
PY_TOOL = Path(__file__).resolve().parents[2] / 'arch00tool.py'
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location('arch00tool_reference', PY_TOOL)
REFERENCE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REFERENCE
SPEC.loader.exec_module(REFERENCE)


def run(cmd, *args):
    env = dict(os.environ, PYTHONUTF8='1')
    return subprocess.run([*map(str, cmd), *map(str, args)], capture_output=True,
                          text=True, encoding='utf-8', errors='replace', env=env)


def make_archive(path, entries):
    # File records stay in logical order while payloads are in reverse physical
    # order, with gaps and an unreferenced trailer, to exercise repacking.
    folder = b'assets'
    names = bytearray(folder + b'\0')
    name_offsets = []
    for name, *_ in entries:
        name_offsets.append(len(names))
        names.extend(name + b'\0')
    metadata_size = 48 + len(names) + 32 * len(entries) + 16
    offsets = [0] * len(entries)
    body = bytearray()
    for index in reversed(range(len(entries))):
        body.extend(b'gap')
        offsets[index] = metadata_size + len(body)
        body.extend(entries[index][1])
    records = b''.join(struct.pack('<IQQQI', name_offsets[i], offsets[i], len(payload), unpacked, method)
                       for i, (_, payload, unpacked, method) in enumerate(entries))
    header = struct.pack('<12I', int.from_bytes(b'LTAR', 'little'), 3, len(names), 1, len(entries),
                         3, 4, 0, 11, 22, 33, 44)
    path.write_bytes(header + names + records + struct.pack('<IIII', 0, 10, 11, len(entries)) + body + b'trailer')


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def equal_status(left, right, context):
    assert (left.returncode == 0) == (right.returncode == 0), (
        f'{context}: Python={left.returncode}, C++={right.returncode}\n{left.stderr}\n{right.stderr}')


python = [sys.executable, PY_TOOL]
cpp = [CPP]
rng = random.Random(405)
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    # Mixture covers raw size mismatches, empty entries, zlib 1–9, UTF-8 and CP1252.
    raw = bytes(rng.randrange(256) for _ in range(5000))
    text = (b'compressed-data-' * 10000) + raw
    entries = [(b'raw.bin', raw, len(raw) + 37, 0),
               (b'empty.bin', b'', 0, 0),
               (b'caf\xe9.bin', b'legacy', 6, 0),
               ('текст.bin'.encode(), zlib.compress(text, 6), len(text), 6)]
    for level in range(1, 10):
        content = bytes([level]) * (300 + level)
        entries.append((f'level{level}.bin'.encode(), zlib.compress(content, level), len(content), level))
    source = root/'source.Arch00'
    make_archive(source, entries)
    header, expected, folders = REFERENCE.parse_archive(source)
    listing = run(cpp, 'list', source)
    assert listing.returncode == 0, listing.stderr
    for entry in expected:
        assert entry.name in listing.stdout, entry.name
    assert len(expected) == len(entries) and folders == ['assets']

    for mode in ('auto', 'raw'):
        py_test = run(python, 'test', source, '--compression', mode)
        for workers in (1, 4):
            c_test = run(cpp, 'test', source, '--compression', mode, '--jobs', workers)
            equal_status(py_test, c_test, f'test {mode} jobs={workers}')
            assert c_test.returncode == 0, c_test.stderr
        for pattern in ('', '*.bin', '*level[2-4].bin', '*текст.bin', '*.missing'):
            py_out = root/f'py-{mode}-{len(list(root.iterdir()))}'
            c_out = root/f'cpp-{mode}-{len(list(root.iterdir()))}'
            opts = ['--compression', mode] + (['--pattern', pattern] if pattern else [])
            py_extract = run(python, 'extract', source, py_out, *opts)
            c_extract = run(cpp, 'extract', source, c_out, *opts, '--jobs', '4')
            equal_status(py_extract, c_extract, f'extract {mode} {pattern}')
            assert py_extract.returncode == 0, py_extract.stderr
            assert files(py_out) == files(c_out), (mode, pattern)

    mod = root/'mod'/'assets'; mod.mkdir(parents=True)
    (mod/'level1.bin').write_bytes(b'replaced')
    (mod/'empty.bin').write_bytes(b'')
    for replace in (False, True):
        py_repack = root/f'python-{replace}.Arch00'
        options = ['--replace-dir', root/'mod'] if replace else []
        py_result = run(python, 'repack', source, py_repack, *options)
        assert py_result.returncode == 0, py_result.stderr
        for workers in (1, 4):
            c_repack = root/f'cpp-{replace}-{workers}.Arch00'
            c_result = run(cpp, 'repack', source, c_repack, *options, '--jobs', workers)
            equal_status(py_result, c_result, f'repack {replace} jobs={workers}')
            assert c_result.returncode == 0, c_result.stderr
            assert py_repack.read_bytes() == c_repack.read_bytes()

    # Validate outcomes for unsupported fields and corrupt or truncated streams.
    packed = zlib.compress(b'payload' * 1000)
    variants = [(packed[:-1], 7000, 6), (packed+b'extra', 7000, 6),
                (packed, 6999, 6), (packed, 7001, 6),
                (b'bytes', 5, 10), (b'', 5, 0), (b'', 0, 99),
                (b'not zlib', 9, 3), (b'bytes', 99, 0)]
    for i, (payload, size, method) in enumerate(variants):
        malformed = root/f'case-{i}.Arch00'
        make_archive(malformed, [(b'file.bin', payload, size, method)])
        for mode in ('auto', 'raw'):
            py = run(python, 'test', malformed, '--compression', mode)
            c = run(cpp, 'test', malformed, '--compression', mode, '--jobs', '4')
            equal_status(py, c, f'case {i} {mode}')
            # Compare successfully extracted bytes too; failure remnants may differ.
            py_dir, c_dir = root/f'p-{i}-{mode}', root/f'c-{i}-{mode}'
            pe = run(python, 'extract', malformed, py_dir, '--compression', mode)
            ce = run(cpp, 'extract', malformed, c_dir, '--compression', mode)
            equal_status(pe, ce, f'extract case {i} {mode}')
            if pe.returncode == 0:
                assert files(py_dir) == files(c_dir)
    # Structural failures: signature/version, table bounds, missing/invalid names,
    # file range, and folder counts. Both parsers should reject each fixture.
    valid = bytearray(source.read_bytes())
    name_size = struct.unpack_from('<I', valid, 8)[0]
    file_table = 48 + name_size
    folder_table = file_table + len(entries) * 32
    mutations = {}
    mutations['short-header'] = bytes(valid[:12])
    data = bytearray(valid); data[:4] = b'NOPE'; mutations['signature'] = bytes(data)
    data = bytearray(valid); struct.pack_into('<I', data, 4, 2); mutations['version'] = bytes(data)
    data = bytearray(valid); struct.pack_into('<I', data, 8, 0xffffffff); mutations['name-limit'] = bytes(data)
    data = bytearray(valid); struct.pack_into('<I', data, 16, 2000001); mutations['entry-limit'] = bytes(data)
    data = bytearray(valid); struct.pack_into('<I', data, file_table, name_size); mutations['name-offset'] = bytes(data)
    data = bytearray(valid); struct.pack_into('<Q', data, file_table+4, len(data)+1); mutations['data-offset'] = bytes(data)
    data = bytearray(valid); struct.pack_into('<Q', data, file_table+12, len(data)); mutations['data-length'] = bytes(data)
    data = bytearray(valid); struct.pack_into('<I', data, folder_table+12, len(entries)+1); mutations['folder-overflow'] = bytes(data)
    data = bytearray(valid); struct.pack_into('<I', data, folder_table+12, len(entries)-1); mutations['folder-underflow'] = bytes(data)
    for name, blob in mutations.items():
        malformed = root/f'metadata-{name}.Arch00'; malformed.write_bytes(blob)
        a, b = run(python, 'list', malformed), run(cpp, 'list', malformed)
        equal_status(a,b,f'metadata {name}')
        assert a.returncode != 0, name

    # Path checks are performed by extraction/repack, not by list or test.
    for index, unsafe_name in enumerate((b'../escape', b'C:drive', b'../a/b')):
        unsafe = root/f'unsafe-{index}.Arch00'
        make_archive(unsafe, [(unsafe_name,b'data',4,0)])
        assert run(python,'list',unsafe).returncode == 0
        assert run(cpp,'list',unsafe).returncode == 0
        py_out, c_out = root/f'unsafe-py-{index}', root/f'unsafe-cpp-{index}'
        a, b = run(python,'extract',unsafe,py_out), run(cpp,'extract',unsafe,c_out)
        equal_status(a,b,f'unsafe path {unsafe_name!r}')
        assert a.returncode != 0
        a = run(python,'repack',unsafe,root/f'unsafe-python-{index}', '--replace-dir',root/'mod')
        b = run(cpp,'repack',unsafe,root/f'unsafe-cpp-output-{index}', '--replace-dir',root/'mod')
        equal_status(a,b,f'unsafe replacement {unsafe_name!r}')
        assert a.returncode != 0

    # Plain parsing accepts in-bounds raw data inside metadata, while both
    # repackers intentionally reject it.
    metadata_payload = root/'metadata-payload.Arch00'
    data = bytearray(source.read_bytes())
    struct.pack_into('<Q',data,file_table+4,0)
    struct.pack_into('<Q',data,file_table+12,4)
    struct.pack_into('<Q',data,file_table+20,4)
    metadata_payload.write_bytes(data)
    assert run(python,'test',metadata_payload).returncode == 0
    assert run(cpp,'test',metadata_payload).returncode == 0
    a = run(python,'repack',metadata_payload,root/'metadata-output-py')
    b = run(cpp,'repack',metadata_payload,root/'metadata-output-cpp')
    equal_status(a,b,'metadata payload repack')
    assert a.returncode != 0
print('Python/C++ differential tests passed')
