import pathlib
import struct
import subprocess
import sys
import tempfile

exe = sys.argv[1]
def run(*args):
    return subprocess.run([exe, *map(str, args)], capture_output=True, text=True, encoding='utf-8')

with tempfile.TemporaryDirectory() as temp:
    root = pathlib.Path(temp) / 'путь-資料'; root.mkdir()
    source = root / 'архив.Arch00'
    names = 'ресурсы\0файл.txt\0'.encode('utf-8')
    name_offset = len('ресурсы\0'.encode('utf-8'))
    data_offset = 48 + len(names) + 32 + 16
    header = struct.pack('<12I',int.from_bytes(b'LTAR','little'),3,len(names),1,1,0,0,0,0,0,0,0)
    source.write_bytes(header + names + struct.pack('<IQQQI',name_offset,data_offset,3,3,0) + struct.pack('<IIII',0,0,0,1) + b'old')
    r=run('list', source); assert r.returncode==0, r.stderr
    assert 'ресурсы\\файл.txt' in r.stdout
    output = root / 'выход'
    r=run('extract', source, output, '--pattern', '*файл.txt', '--jobs', '2')
    assert r.returncode == 0, r.stderr
    assert (output/'ресурсы'/'файл.txt').read_bytes()==b'old'
    mod = root/'замена'; (mod/'ресурсы').mkdir(parents=True)
    (mod/'ресурсы'/'файл.txt').write_bytes(b'new')
    new_archive=root/'новый.Arch00'
    r=run('repack',source,new_archive,'--replace-dir',mod); assert r.returncode==0, r.stderr
    r=run('extract',new_archive,root/'проверка'); assert r.returncode==0, r.stderr
    assert (root/'проверка'/'ресурсы'/'файл.txt').read_bytes()==b'new'
    batch=root/'все'; batch.mkdir(); (batch/'архив.Arch00').write_bytes(source.read_bytes())
    r=run('test-all',batch); assert r.returncode==0, r.stderr
    r=run('extract-all',batch,root/'пакет'); assert r.returncode==0, r.stderr
    assert (root/'пакет'/'архив.Arch00.extracted'/'ресурсы'/'файл.txt').read_bytes()==b'old'
print('Unicode paths passed')
