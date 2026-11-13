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

def build(path):
    names=b'dir\0one.txt\0two.bin\0'
    packed=zlib.compress(b'original compressed'*100)
    metadata_end=48+len(names)+2*32+16
    # Reverse physical order, include gap and trailing unreferenced bytes.
    first_offset=metadata_end+3+4
    header=struct.pack('<12I',int.from_bytes(b'LTAR','little'),3,len(names),1,2,2,3,0,1,2,3,4)
    records=struct.pack('<IQQQI',4,first_offset,len(packed),1900,6)+struct.pack('<IQQQI',12,metadata_end,3,3,0)
    folder=struct.pack('<IIII',0,99,123,2)
    path.write_bytes(header+names+records+folder+b'raw'+b'GAP!'+packed+b'TRAILER')

with tempfile.TemporaryDirectory() as tmp:
    root=pathlib.Path(tmp); source=root/'source.Arch00'; build(source); original=source.read_bytes()
    rebuilt=root/'repacked.Arch00'
    r=run('repack', source, rebuilt); assert r.returncode==0, r.stderr
    assert 'replaced=0' in r.stdout and source.read_bytes()==original
    assert not pathlib.Path(str(rebuilt)+'.partial').exists()
    assert run('test',rebuilt).returncode==0
    out=root/'out'
    py=subprocess.run([sys.executable,str(python_tool),'extract',str(rebuilt),str(out)],capture_output=True,text=True)
    assert py.returncode==0, py.stderr
    assert (out/'dir/one.txt').read_bytes()==b'original compressed'*100
    assert (out/'dir/two.bin').read_bytes()==b'raw'
    assert rebuilt.stat().st_size < source.stat().st_size
    assert run('repack',source,rebuilt).returncode==2
    replacement=root/'mod/dir'; replacement.mkdir(parents=True)
    (replacement/'one.txt').write_bytes(b'modified')
    (replacement/'extra').write_bytes(b'ignored')
    modded=root/'modded.Arch00'
    r=run('repack',source,modded,'--replace-dir',root/'mod'); assert r.returncode==0,r.stderr
    assert 'replaced=1' in r.stdout and run('test',modded).returncode==0
    out2=root/'out2'; assert run('extract',modded,out2).returncode==0
    assert (out2/'dir/one.txt').read_bytes()==b'modified'
    assert (out2/'dir/two.bin').read_bytes()==b'raw'
    # Both original output and pre-existing partial are preserved.
    blocked=root/'blocked.Arch00'; partial=root/'blocked.Arch00.partial'; partial.write_bytes(b'keep')
    assert run('repack',source,blocked).returncode==2 and partial.read_bytes()==b'keep'
    assert run('repack',source,source).returncode==2 and source.read_bytes()==original
    assert not blocked.exists()
    # Refuse entries pointing into metadata, even though list can parse them.
    damaged=root/'metadata.Arch00'; data=bytearray(original)
    names_size=struct.unpack_from('<I',data,8)[0]; struct.pack_into('<Q',data,48+names_size+4,0); damaged.write_bytes(data)
    assert run('repack',damaged,root/'bad-output').returncode==2
print('repack tests passed')
