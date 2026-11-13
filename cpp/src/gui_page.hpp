#pragma once
static constexpr const char* gui_page = R"ARCH00HTML(<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Arch00 Tool</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#111927;color:#e5ecf5}body{margin:0;padding:2rem}main{max-width:900px;margin:auto}h1{margin-bottom:.2rem}p,.hint{color:#b4c2d3}section{background:#1c293b;padding:1.3rem;border:1px solid #36465a;border-radius:12px;margin:1rem 0}label{display:block;margin:.8rem 0 .3rem;font-weight:600}input,select,button{box-sizing:border-box;font:inherit;padding:.6rem;border-radius:6px;border:1px solid #506078}input:not([type=checkbox]){width:100%;background:#0e1926;color:#fff}select{background:#0e1926;color:#fff}button{background:#69b8f2;color:#102033;font-weight:700;cursor:pointer;margin:.5rem .3rem .2rem 0}button:disabled{opacity:.5}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:26rem;overflow:auto;background:#0e1926;padding:1rem;border-radius:6px}dialog{background:#1c293b;color:#e5ecf5;border:1px solid #506078;border-radius:12px;max-width:750px;width:90%;max-height:80vh}dialog::backdrop{background:#0009}#browse-list{max-height:40vh;overflow:auto}#browse-list button{display:block;text-align:left;width:100%;background:#263b50;color:#e5ecf5} .warn{border-left:4px solid #e3a946;padding-left:1rem}
</style></head><body><main><h1>Arch00 Tool</h1><p>Experimental local interface · LTAR v3</p><p class="warn">Use trusted archives and a new private output directory. No overwrite is intended, but extraction can leave partial files. Keep backups.</p>
<section><label for="archive">Archive or input directory path</label><input id="archive" placeholder="/path/to/archive.Arch00" autocomplete="off"><button type="button" data-browse="archive">Browse archive or input folder…</button><label for="output">Output path (extract directory or new archive for repack)</label><input id="output" placeholder="/path/to/output" autocomplete="off"><button type="button" data-browse="output">Browse output folder…</button><label for="replace">Replacement directory (optional, repack only)</label><input id="replace" placeholder="/path/to/mod" autocomplete="off"><button type="button" data-browse="replace">Browse replacement folder…</button><label for="pattern">Pattern (optional; single-archive extract only)</label><input id="pattern" placeholder="*.dds" autocomplete="off"><p><label><input type="checkbox" id="skip"> Skip existing destinations (extract all)</label></p><label for="mode">Compression mode (test / extract)</label><select id="mode"><option value="auto">Auto</option><option value="raw">Raw stored bytes</option></select><label for="jobs">Workers (test / extract / repack, 1–64)</label><input id="jobs" type="number" min="1" max="64" value="1"><p class="hint">Paths refer to this computer. For batch operations, enter an input directory as the archive path. Repacking stores replacements uncompressed. A successful test does not guarantee game compatibility.</p><div><button data-action="list">List</button><button data-action="test">Test</button><button data-action="extract">Extract</button><button data-action="repack">Repack</button><button data-action="test-all">Test all</button><button data-action="extract-all">Extract all</button></div></section><section><strong id="status" role="status" aria-live="polite">Ready</strong><p><progress id="progress" max="1" aria-label="Current operation progress" hidden></progress> <button id="cancel" type="button" disabled>Cancel operation</button></p><pre id="result">Results will appear here.</pre></section></main>
<dialog id="browser"><h2>Choose a local path</h2><p class="hint">Select an archive or navigate into a folder. For repack output, select the parent folder and append a new filename manually.</p><label for="browse-path">Current folder</label><input id="browse-path" autocomplete="off"><button type="button" id="browse-go">Go</button><button type="button" id="browse-up">Up</button><button type="button" id="browse-select">Use this folder</button><button type="button" id="browse-close">Close</button><p id="browse-status" role="status"></p><div id="browse-list"></div></dialog>
<script>
'use strict';
const fragment=location.hash.slice(1); if(fragment){sessionStorage.setItem('arch00-token',fragment);history.replaceState(null,'',location.pathname)}
const token=sessionStorage.getItem('arch00-token')||'';
const buttons=document.querySelectorAll('button[data-action]');
const progress=document.getElementById('progress'), cancelButton=document.getElementById('cancel');
let currentRequest='';
async function control(endpoint,id){
 const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json','X-Arch00-Token':token},body:JSON.stringify({request_id:id})});
 return {response,data:await response.json()};
}
async function poll(id){
 try { const {response,data}=await control('/status',id); if(currentRequest!==id || !response.ok)return;
  const label=data.cancelling?'Cancelling…':data.phase;
  document.getElementById('status').textContent=data.total?`${label}: ${data.completed}/${data.total} entries`:label+'…';
  if(data.total){progress.max=data.total;progress.value=data.completed}else progress.removeAttribute('value');
  cancelButton.disabled=data.cancelling||data.publishing;
 }catch(_) { /* Request can finish before polling begins. */ }
}
cancelButton.addEventListener('click',async()=>{const id=currentRequest;if(!id)return;cancelButton.disabled=true;try{const {data}=await control('/cancel',id);if(currentRequest===id)document.getElementById('status').textContent=data.message;}catch(err){if(currentRequest===id)document.getElementById('status').textContent=String(err)}});

const dialog=document.getElementById('browser'), browsePath=document.getElementById('browse-path'), browseStatus=document.getElementById('browse-status'), browseList=document.getElementById('browse-list');
let browseTarget='', browseParent='', currentBrowsePath='';
async function browse(path) {
 browseStatus.textContent='Loading…'; browseList.replaceChildren(); currentBrowsePath=''; document.getElementById('browse-select').disabled=true;
 try {
  const response=await fetch('/browse',{method:'POST',headers:{'Content-Type':'application/json','X-Arch00-Token':token},body:JSON.stringify({path})});
  const data=await response.json(); if(!response.ok)throw new Error(data.message||'Cannot read directory');
  browsePath.value=data.path; currentBrowsePath=data.path; browseParent=data.parent; document.getElementById('browse-select').disabled=false;
  browseStatus.textContent=data.truncated?'Showing the first 2,000 items; enter a path to navigate further.':`${data.entries.length} items`;
  for(const entry of data.entries){
   if(!entry.directory && browseTarget!=='archive')continue;
   const item=document.createElement('button'); item.type='button'; item.textContent=(entry.directory?'📁 ':'📄 ')+entry.name;
   item.addEventListener('click',()=>{if(entry.directory)browse(entry.path);else{document.getElementById(browseTarget).value=entry.path;dialog.close()}}); browseList.append(item);
  }
 } catch(error) {browseStatus.textContent=String(error)}
}
for(const button of document.querySelectorAll('button[data-browse]'))button.addEventListener('click',()=>{if(!token){document.getElementById('status').textContent='Open the session URL printed by the program.';return}browseTarget=button.dataset.browse;dialog.showModal();browse(document.getElementById(browseTarget).value)});
document.getElementById('browse-go').addEventListener('click',()=>browse(browsePath.value));
document.getElementById('browse-up').addEventListener('click',()=>browse(browseParent));
document.getElementById('browse-select').addEventListener('click',()=>{if(!currentBrowsePath)return;document.getElementById(browseTarget).value=currentBrowsePath;dialog.close()});
document.getElementById('browse-close').addEventListener('click',()=>dialog.close());

for(const button of buttons)button.addEventListener('click',async()=>{
 const action=button.dataset.action, status=document.getElementById('status'), result=document.getElementById('result');
 if(!token){status.textContent='Missing session token. Open the URL printed by the program.';return}
 if((action==='extract'||action==='extract-all'||action==='repack')&&!confirm('Write output to the specified path? Existing files are not meant to be overwritten.'))return;
 const request_id=Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
 const data={request_id,action,archive:document.getElementById('archive').value,output:document.getElementById('output').value,replace:document.getElementById('replace').value,pattern:document.getElementById('pattern').value,skip_existing:document.getElementById('skip').checked,compression:document.getElementById('mode').value,jobs:Number(document.getElementById('jobs').value)};
 buttons.forEach(b=>b.disabled=true);currentRequest=request_id; progress.hidden=false; progress.removeAttribute('value');cancelButton.disabled=false;status.textContent='Working…';result.textContent='Please wait; large archives may take time.';
 const timer=setInterval(()=>poll(request_id),500);poll(request_id);
 try{const response=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Arch00-Token':token},body:JSON.stringify(data)});const body=await response.json();status.textContent=response.ok?'Done':'Error';result.textContent=body.message||'No result';}catch(err){status.textContent='Error';result.textContent=String(err)}finally{clearInterval(timer);currentRequest='';cancelButton.disabled=true;progress.hidden=true;buttons.forEach(b=>b.disabled=false)}
});
</script></body></html>)ARCH00HTML";
