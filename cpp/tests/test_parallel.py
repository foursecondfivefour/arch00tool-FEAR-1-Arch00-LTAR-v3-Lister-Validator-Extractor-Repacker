import pathlib
import struct
import subprocess
import sys
import tempfile
import zlib

exe = sys.argv[1]
def run(*args):
    return subprocess.run([exe, *map(str, args)], capture_output=True, text=True)
def build(path, corrupt=False):
    count = 48
    names = bytearray(b'folder\0')
    offsets = []
    payloads = []
    for i in range(count):
        offsets.append(len(names)); names += f'{i}.bin'.encode() + b'\0'
        data = bytes([i]) * 200_000
        payload = zlib.compress(data) if i % 2 else data
        if corrupt and i == 17:
            payload = payload[:-1] + bytes([payload[-1] ^ 1])
        payloads.append((data, payload, 6 if i % 2 else 0))
    data_offset = 48 + len(names) + count * 32 + 16
    records = bytearray()
    for i, (data, payload, method) in enumerate(payloads):
        records += struct.pack('<IQQQI', offsets[i], data_offset, len(payload), len(data), method)
        data_offset += len(payload)
    header = struct.pack('<12I', int.from_bytes(b'LTAR', 'little'), 3, len(names), 1, count, 0, 0, 0, 0, 0, 0, 0)
    path.write_bytes(header + names + records + struct.pack('<IIII', 0, 0, 0, count) + b''.join(x[1] for x in payloads))

with tempfile.TemporaryDirectory() as tmp:
    root=pathlib.Path(tmp); good=root/'good.Arch00'; build(good)
    for n in (1, 2, 4, 64):
        r=run('test',good,'--jobs',n)
        assert r.returncode==0 and '48 files' in r.stdout, r.stderr
    for n in ('0','65','-1','foo','9999999999999999999999999999'):
        assert run('test',good,'--jobs',n).returncode==2
    for n in (1, 2, 4, 64):
        out = root/f'out{n}'
        r = run('extract', good, out, '--jobs', n, '-v')
        assert r.returncode == 0, r.stderr
        for i in range(48):
            assert (out/'folder'/f'{i}.bin').read_bytes() == bytes([i]) * 200_000
        # Re-extraction must not overwrite files.
        assert run('extract', good, out, '--jobs', n).returncode == 2
    out = root/'selected'
    assert run('extract', good, out, '--jobs', 4, '--pattern', '*1.bin').returncode == 0
    assert sorted(p.name for p in (out/'folder').iterdir()) == ['1.bin','11.bin','21.bin','31.bin','41.bin']
    batchout=root/'batch'
    assert run('extract-all',root,batchout,'--jobs',4).returncode==0
    assert (batchout/'good.Arch00.extracted'/'folder'/'17.bin').read_bytes()==bytes([17])*200_000
    # Two entries sharing a name must fail before writing anything in parallel.
    dup=root/'duplicate.Arch00'
    data=bytearray(good.read_bytes()); names_size=struct.unpack_from('<I',data,8)[0]
    first=struct.unpack_from('<I',data,48+names_size)[0]
    struct.pack_into('<I',data,48+names_size+32,first); dup.write_bytes(data)
    dupout=root/'duplicate-out'
    assert run('extract',dup,dupout,'--jobs',4).returncode==2
    assert not dupout.exists()
    dup.unlink()
    # A path used as both a file and an ancestor directory is rejected.
    conflict=root/'conflict.Arch00'
    names=b'folder\0file\0file/child\0'; start=48+len(names)+64+16
    header=struct.pack('<12I',int.from_bytes(b'LTAR','little'),3,len(names),1,2,0,0,0,0,0,0,0)
    rec=struct.pack('<IQQQI',7,start,1,1,0)+struct.pack('<IQQQI',12,start+1,1,1,0)
    conflict.write_bytes(header+names+rec+struct.pack('<IIII',0,0,0,2)+b'ab')
    conflictout=root/'conflict-out'
    assert run('extract',conflict,conflictout,'--jobs',4).returncode==2
    assert not conflictout.exists()
    conflict.unlink()
    # Existing file must never be overwritten.
    existing=root/'existing'; (existing/'folder').mkdir(parents=True)
    sentinel=existing/'folder'/'0.bin'; sentinel.write_bytes(b'keep')
    assert run('extract',good,existing,'--jobs',4).returncode==2
    assert sentinel.read_bytes()==b'keep'
    bad=root/'bad.Arch00'; build(bad, True)
    for n in (1,2,4):
        assert run('test',bad,'--jobs',n).returncode==2
        assert run('test',bad,'--jobs',n,'--compression','raw').returncode==0
    assert run('extract',bad,root/'bad-out','--jobs',4).returncode==2
    assert run('test-all',root,'--jobs',4).returncode==1
    assert run('test-all',root,'--jobs',4,'--compression','raw').returncode==0
print('parallel tests passed')
