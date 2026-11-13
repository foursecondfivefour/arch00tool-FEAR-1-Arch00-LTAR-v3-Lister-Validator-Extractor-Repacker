import pathlib
import struct
import subprocess
import sys
import tempfile
import zlib

exe = sys.argv[1]
python_tool = pathlib.Path(__file__).resolve().parents[2] / 'arch00tool.py'
def run(*args):
    return subprocess.run([exe, *map(str, args)], capture_output=True, text=True)
def archive(path, payload, size, compression, name=b'file.bin'):
    names = b'folder\0' + name + b'\0'
    offset = 48 + len(names) + 32 + 16
    header = struct.pack('<12I', int.from_bytes(b'LTAR', 'little'), 3, len(names), 1, 1, 0, 0, 0, 0, 0, 0, 0)
    path.write_bytes(header + names + struct.pack('<IQQQI', 7, offset, len(payload), size, compression) + struct.pack('<IIII', 0, 0, 0, 1) + payload)

with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    source = root / 'sample.Arch00'
    data = b'ABCD' * 150000
    for payload, mode in ((data, 0), (zlib.compress(data), 6)):
        archive(source, payload, len(data), mode)
        assert run('test', source).returncode == 0
        dest = root / ('out' + str(mode))
        assert run('extract', source, dest).returncode == 0
        assert (dest / 'folder/file.bin').read_bytes() == data
        assert run('extract', source, dest).returncode != 0
        other = root / ('python' + str(mode))
        result = subprocess.run([sys.executable, str(python_tool), 'extract', str(source), str(other)], capture_output=True)
        assert result.returncode == 0
        assert (dest / 'folder/file.bin').read_bytes() == (other / 'folder/file.bin').read_bytes()
    for payload, size in ((zlib.compress(data)[:-1], len(data)), (zlib.compress(data)+b'x', len(data)), (zlib.compress(data), len(data)-1), (zlib.compress(data), len(data)+1)):
        archive(source, payload, size, 6)
        assert run('test', source).returncode != 0
        assert run('test', source, '--compression', 'raw').returncode == 0
    archive(source, b'a', 1, 0, b'../escape')
    assert run('extract', source, root/'unsafe').returncode != 0
    assert not (root/'escape').exists()
print('payload tests passed')
