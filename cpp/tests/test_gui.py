import json
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

process = subprocess.Popen([sys.argv[1]], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
try:
    line = process.stdout.readline()
    match = re.search(r'(http://127\.0\.0\.1:\d+)/#([0-9a-f]{64})', line)
    assert match, line
    origin, token = match.groups()
    def request(path, body=None, headers=None):
        req = urllib.request.Request(origin+path, data=body, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
    status, page = request('/')
    assert status == 200 and b'Arch00 Tool' in page
    headers = {'Content-Type': 'application/json', 'Origin': origin, 'X-Arch00-Token': token}
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp); archive = root/'a.Arch00'
        names=b'folder\0file.txt\0'; offset=48+len(names)+32+16
        archive.write_bytes(struct.pack('<12I', int.from_bytes(b'LTAR','little'),3,len(names),1,1,0,0,0,0,0,0,0)+names+struct.pack('<IQQQI',7,offset,3,3,0)+struct.pack('<IIII',0,0,0,1)+b'abc')
        browse_body=json.dumps({'path':str(root)}).encode()
        assert request('/browse', browse_body, {'Content-Type':'application/json','Origin':origin})[0]==403
        assert request('/browse', browse_body, {**headers,'Origin':'https://example.com'})[0]==403
        assert request('/browse', browse_body, {**headers,'Host':'evil.example'})[0]==403
        status,browse_result=request('/browse',browse_body,headers)
        listing=json.loads(browse_result)
        assert status==200 and pathlib.Path(listing['path'])==root
        assert any(item['name']=='a.Arch00' and not item['directory'] for item in listing['entries'])
        assert request('/browse',json.dumps({'path':str(root/'missing')}).encode(),headers)[0]==400
        assert request('/browse',json.dumps({'path':'bad\0path'}).encode(),headers)[0]==400
        def action(name, **extra):
            body=json.dumps(dict(action=name,archive=str(archive),**extra)).encode()
            return request('/api',body,headers)
        body=json.dumps({'action':'list','archive':str(archive)}).encode()
        assert request('/api',body,{'Content-Type':'application/json','Origin':origin})[0]==403
        assert request('/api',body,{**headers,'Origin':'https://example.com'})[0]==403
        assert request('/api',body,{**headers,'Host':'evil.example'})[0]==403
        assert request('/api',body,{**headers,'X-Arch00-Token':'bad'})[0]==403
        status, result=action('list'); assert status==200 and 'folder\\file.txt' in json.loads(result)['message']
        assert action('test',jobs=4,compression='auto')[0]==200
        assert action('test',jobs=65,compression='auto')[0]==400
        assert action('test',jobs=1.5,compression='auto')[0]==400
        out=root/'out'; assert action('extract',output=str(out),jobs=2,compression='auto')[0]==200
        assert (out/'folder'/'file.txt').read_bytes()==b'abc'
        assert action('extract',output=str(out),jobs=2,compression='auto')[0]==400
        rebuilt=root/'new.Arch00'; assert action('repack',output=str(rebuilt),replace='',jobs=4)[0]==200
        assert rebuilt.exists()
        assert action('repack',output=str(root/'invalid.Arch00'),replace='',jobs=65)[0]==400
        assert action('repack',output=str(rebuilt),replace='')[0]==400
        patternout=root/'pattern'; status, result=action('extract',output=str(patternout),jobs=2,pattern='*.dds')
        assert status==200 and 'Extracted 0 files' in json.loads(result)['message']
        assert not (patternout/'folder'/'file.txt').exists()
        patternout2=root/'pattern2'; status, result=action('extract',output=str(patternout2),pattern='*.txt')
        assert status==200 and (patternout2/'folder'/'file.txt').read_bytes()==b'abc'
        archives=root/'archives'; archives.mkdir(); (archives/'a.Arch00').write_bytes(archive.read_bytes())
        (archives/'b.arch00').write_bytes(archive.read_bytes()); (archives/'ignored.txt').write_bytes(b'x')
        def batch(name, **extra):
            return request('/api',json.dumps(dict(action=name,archive=str(archives),**extra)).encode(),headers)
        assert batch('test-all',jobs=4)[0]==200
        batchout=root/'batch'
        status,result=batch('extract-all',output=str(batchout),jobs=2)
        assert status==200 and 'failed=0' in json.loads(result)['message']
        assert (batchout/'a.Arch00.extracted'/'folder'/'file.txt').read_bytes()==b'abc'
        assert batch('extract-all',output=str(batchout))[0]==400
        status,result=batch('extract-all',output=str(batchout),skip_existing=True)
        assert status==200 and 'skipped=2' in json.loads(result)['message']
        (archives/'bad.Arch00').write_bytes(b'bad')
        status,result=batch('test-all',jobs=3)
        assert status==400 and 'failed=1' in json.loads(result)['message']
        assert action('not-supported')[0]==400
finally:
    process.terminate()
    try: process.wait(timeout=5)
    except subprocess.TimeoutExpired: process.kill(); process.wait()
print('gui API tests passed')
