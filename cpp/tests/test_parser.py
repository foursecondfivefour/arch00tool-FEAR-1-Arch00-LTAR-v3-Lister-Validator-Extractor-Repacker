import pathlib
import struct
import subprocess
import sys
import tempfile

exe = sys.argv[1]

def run(path, *args):
    return subprocess.run([exe, 'list', str(path), *args], capture_output=True, text=True)

with tempfile.TemporaryDirectory() as temp:
    path = pathlib.Path(temp) / 'test.Arch00'
    names = b'folder\0file.txt\0'
    offset = 48 + len(names) + 32 + 16
    header = struct.pack('<12I', int.from_bytes(b'LTAR', 'little'), 3, len(names), 1, 1, 0, 0, 0, 0, 0, 0, 0)
    file = struct.pack('<IQQQI', 7, offset, 3, 3, 0)
    folder = struct.pack('<IIII', 0, 0, 0, 1)
    path.write_bytes(header + names + file + folder + b'abc')
    result = run(path, '-v')
    assert result.returncode == 0, result.stderr
    assert 'folder\\file.txt' in result.stdout and '3 -> 3 raw' in result.stdout
    for data in (b'bad', b'NOPE' + (header + names + file + folder + b'abc')[4:], header + names + file + folder):
        path.write_bytes(data)
        assert run(path).returncode == 2
    path.write_bytes(header + names + file + struct.pack('<IIII', 0, 0, 0, 0) + b'abc')
    assert run(path).returncode == 2
print('parser tests passed')
