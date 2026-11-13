import pathlib
import struct
import subprocess
import sys
import tempfile

exe = sys.argv[1]
def run(*args):
    return subprocess.run([exe, *map(str, args)], capture_output=True, text=True)
def archive(path, name):
    names = b'folder\0' + name.encode('utf-8') + b'\0'
    offset = 48 + len(names) + 32 + 16
    h = struct.pack('<12I', int.from_bytes(b'LTAR', 'little'), 3, len(names), 1, 1, 0, 0, 0, 0, 0, 0, 0)
    path.write_bytes(h + names + struct.pack('<IQQQI', 7, offset, 3, 3, 0) + struct.pack('<IIII', 0, 0, 0, 1) + b'abc')

with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp); inputs = root/'archives'; inputs.mkdir()
    archive(inputs/'a.Arch00', 'файл.dds')
    archive(inputs/'b.arch00', 'image.txt')
    for pattern, matches in [('*.dds', True), ('*.DDS', False), ('*ф?йл.[dt]ds', True), ('*ф[!a]йл.dds', True), ('[', False)]:
        out = root/('pattern'+str(len(list(root.iterdir()))))
        result=run('extract', inputs/'a.Arch00', out, '--pattern', pattern, '-v')
        assert result.returncode == 0, result.stderr
        assert (out/'folder'/'файл.dds').exists() == matches
    result=run('test-all', inputs)
    assert result.returncode==0 and result.stdout.count('OK ')==2
    out=root/'batch'; result=run('extract-all', inputs, out, '-v')
    assert result.returncode==0, result.stderr
    assert (out/'a.Arch00.extracted'/'folder'/'файл.dds').read_bytes()==b'abc'
    assert run('extract-all', inputs, out).returncode==2
    assert run('extract-all', inputs, out, '--skip-existing').returncode==0
    (inputs/'bad.Arch00').write_bytes(b'bad')
    assert run('test-all', inputs).returncode==1
    assert run('extract-all', inputs, root/'batch2').returncode==1
    empty=root/'empty'; empty.mkdir(); assert run('test-all', empty).returncode==2
print('cli tests passed')
