// Notes LaTeX compile, build watch, and SyncTeX position sync.
import {
  icon, esc, toast, api, libraryURL, workspaceURL,
} from './project-shared.js';
import {
  projectNotice, updateProjectBuildState, showProjectPDF, showProjectSource,
  rememberProjectEditor, selectProjectFile,
} from './project-editor.js';

function scheduleProjectCompile(item){
 item.compileQueued=true;clearTimeout(item.autoCompileTimer);
 const start=()=>{
  if(!item.compileQueued||item.compiling)return;
  if(item.fileBusy||[...item.documents.values()].some(draft=>draft.saving)){item.autoCompileTimer=setTimeout(start,150);return;}
  item.compileQueued=false;void compileProject(item,{automatic:true});
 };
 item.autoCompileTimer=setTimeout(start,150);
}
async function refreshProjectRepairEdits(item,job){
 item.repairRevisions??=new Map();
 for(const repair of new Map((job.repairs||[]).map(repair=>[repair.path,repair])).values()){
  if(item.repairRevisions.get(repair.path)===repair.revision)continue;
  const draft=item.documents.get(repair.path);
  if(draft?.changed||draft?.saving){projectNotice(item,'AI repaired '+repair.path+'. Your newer editor changes are retained; review them before saving.');continue;}
  if(draft){
   // A clean editor can adopt the saved repair; never replace a typing buffer.
   draft.editor?.destroy();draft.host.remove();item.documents.delete(repair.path);
   if(item.activeSource===repair.path)await showProjectSource(item,repair.path,item.selectionRequest);
  }
  item.repairRevisions.set(repair.path,repair.revision);
 }
}
const projectBuildTerminal=new Set(['succeeded','failed','cancelled','interrupted']);
function projectBuildKey(item){return 'notes-paper-build:'+JSON.stringify([item.source,item.project]);}
function paintProjectBuildNotice(item,text){
 const status=item.layer.querySelector('[data-project-build-state]');if(!status)return;
 if(item.compiling||item.buildFinishing){
  clearTimeout(item.buildNoticeTimer);item.buildNoticeTimer=null;item.buildNoticeActive=true;
  status.textContent=text;status.classList.add('is-visible');status.setAttribute('aria-hidden','false');
 }else if(item.buildNoticeActive){
  // Begin the completion hold only after the final PDF has been presented.
  // Repaints and old restored jobs must not restart or replay this notice.
  item.buildNoticeActive=false;status.textContent=text||'Compilation stopped';
  item.buildNoticeTimer=setTimeout(()=>{
   if(item.compiling||item.buildFinishing)return;
   status.classList.remove('is-visible');status.setAttribute('aria-hidden','true');item.buildNoticeTimer=null;
  },2000);
 }
}
function paintProjectBuild(item){
 const layer=item.layer,job=item.buildStatus;
 const seconds=Math.floor((job?.elapsed_seconds||0)+(item.compiling&&job?.state==='running'?(performance.now()-(item.buildReceivedAt||performance.now()))/1000:0));
 let text=job?`${job.detail} · ${seconds}s`:item.compiling?`Saving source and starting compilation… · ${Math.floor((performance.now()-(item.buildClientStart||performance.now()))/1000)}s`:'';
 if(item.buildConnectionError)text+=' · Reconnecting to build status';
 paintProjectBuildNotice(item,text);
 const compile=layer.querySelector('[data-project-compile]');if(compile){compile.disabled=!!item.compiling;compile.innerHTML=icon(item.compiling?'hourglass-half':'play')+(item.compiling?' Compiling…':' Compile');}
 const stop=layer.querySelector('[data-project-stop]');if(stop){stop.hidden=!item.compiling;stop.disabled=!job?.cancellable||!!item.stopPending;}
 const logs=layer.querySelector('[data-project-log]');if(logs)logs.hidden=!job||(item.documentMode&&item.documentMode!=='latex'&&!item.compiling);
 const output=layer.querySelector('[data-project-log-output]');if(output&&job){const bottom=output.scrollHeight-output.scrollTop-output.clientHeight<35;const text=(job.log_truncated?'Earlier output omitted. Showing the latest log.\n':'')+(job.log||job.error||'Waiting for compiler output…')+(job.log&&job.error&&!job.error.startsWith('Compilation failed:')&&!job.log.includes(job.error)?'\n\n'+job.error:'');if(output.textContent!==text){output.textContent=text;if(bottom)output.scrollTop=output.scrollHeight;}}
 const pdfHost=layer.querySelector('.project-pdf-host');
 if(pdfHost&&!item.pdf&&(!item.documentMode||item.documentMode==='latex')){let placeholder=pdfHost.querySelector('[data-build-placeholder]');if(!placeholder){pdfHost.querySelectorAll(':scope > .empty').forEach(node=>node.remove());placeholder=document.createElement('div');placeholder.className='empty';placeholder.dataset.buildPlaceholder='';pdfHost.prepend(placeholder);}placeholder.hidden=!!item.compiling||!!item.buildFinishing;placeholder.textContent=job?.state==='failed'?'Compilation failed. Open View log for details.':'Compile to preview this document.';}
 if(item.documentMode)paintProjectSelection(item);
}
function rememberProjectBuild(item){try{localStorage.setItem(projectBuildKey(item),JSON.stringify({job:item.buildStatus.job,main:item.buildStatus.main,sourceSerial:item.buildSourceSerial,state:item.buildStatus.state}));}catch{}}
async function watchProjectBuild(item,{restore=false}={}){
 clearTimeout(item.buildPoll);clearInterval(item.buildClock);item.buildClock=setInterval(()=>paintProjectBuild(item),1000);
 const poll=async()=>{
  if(!item.layer.isConnected){clearInterval(item.buildClock);clearTimeout(item.buildNoticeTimer);return;}
  try{
   const job=await api(libraryURL('project/build',item.source,item.project,{job:item.buildStatus.job}),undefined,{timeoutMs:8000});
   item.buildStatus=job;item.buildReceivedAt=performance.now();item.buildConnectionError=false;
   item.compiling=!projectBuildTerminal.has(job.state);item.buildFinishing=!item.compiling&&!!item.buildNoticeActive;paintProjectBuild(item);
   await refreshProjectRepairEdits(item,job);
   if(!item.compiling){
    clearInterval(item.buildClock);item.stopPending=false;rememberProjectBuild(item);
    if(job.state==='succeeded'&&job.result){
     const result=job.result;
     if(result.path&&!item.data.entries.some(e=>e.path===result.path)){item.data.entries.push({path:result.path,name:result.path.split('/').at(-1),extension:'.pdf',directory:false});renderProjectTree(item);renderMainTeXSelector(item);}
     invalidateProjectList(item.workspace);
     if(!restore&&result.main===item.data.main&&item.documentMode==='latex'){
      if(result.reused_pdf&&result.pdf_sha256&&item.pdf&&item.pdfPath===result.path&&item.pdfHash===result.pdf_sha256){
       if(item.buildSourceSerial===(item.sourceRevisionSerial||0))item.sourceSavedSincePreview=false;
      }else{
       const completeDetail=job.detail;job.detail='Loading the new PDF';paintProjectBuild(item);
       await showProjectPDF(item,{...result,sourceSerial:item.buildSourceSerial,state:item.buildStatus.state});job.detail=completeDetail;
      }
     }
    }
    item.buildFinishing=false;paintProjectBuild(item);if(item.compileQueued)scheduleProjectCompile(item);return;
   }
  }catch(error){
   item.buildFinishing=false;
   if([403,404].includes(error.status)){
    // Stale job ids (server restart, expired in-memory job) should not keep failing on every refresh.
    item.compiling=false;clearInterval(item.buildClock);
    try{localStorage.removeItem(projectBuildKey(item));}catch{}
    item.buildStatus={...item.buildStatus,state:'interrupted',cancellable:false,detail:'Compilation status unavailable'};
    if(!restore)projectNotice(item,'Previous compilation status is no longer available. The current PDF is unchanged.',{transient:true});
    else projectNotice(item,'');
    paintProjectBuild(item);return;
   }
   item.buildConnectionError=true;paintProjectBuild(item);
  }
  restore=false;item.buildPoll=setTimeout(poll,item.layer.hidden?2500:650);
 };
 await poll();
}
async function resumeProjectBuild(item){
 try{
  const saved=JSON.parse(localStorage.getItem(projectBuildKey(item))||'null');if(!saved?.job)return;
  item.buildSourceSerial=saved.sourceSerial;
  // Terminal builds are only kept to restore sourceSerial; the server job may already be gone.
  if(projectBuildTerminal.has(saved.state))return;
  item.buildStatus={job:saved.job,state:'running',main:saved.main,detail:'Checking compilation status',elapsed_seconds:0};
  await watchProjectBuild(item);
 }catch{}
}
async function stopProjectBuild(item){
 item.compileQueued=false;clearTimeout(item.autoCompileTimer);
 if(!item.buildStatus?.job||item.stopPending)return;
 item.stopPending=true;paintProjectBuild(item);
 try{item.buildStatus=await api('/api/workspaces/project/compile/stop',{source:item.source,project:item.project,job:item.buildStatus.job});item.buildReceivedAt=performance.now();}
 catch(error){projectNotice(item,'Could not confirm stopping. '+error.message);item.stopPending=false;}
 paintProjectBuild(item);
}
async function compileProject(item,{automatic=false}={}){
 if(item.fileBusy){projectNotice(item,'Wait for the file operation to finish before compiling.');return;}
 if(item.compiling||!automatic&&item.documentMode&&item.documentMode!=='latex')return;const main=item.data.main;
 if(!main){projectNotice(item,'Select the main TeX document before compiling.');return;}
 item.compileQueued=false;clearTimeout(item.autoCompileTimer);
 clearInterval(item.buildClock);item.buildClientStart=performance.now();item.buildClock=setInterval(()=>paintProjectBuild(item),1000);
 item.compiling=true;item.buildFinishing=false;item.buildStatus=null;item.stopPending=false;item.buildConnectionError=false;projectNotice(item,'');paintProjectBuild(item);
 try{
  item.savingForCompile=true;
  try{
   const changed=[...item.documents.values()].filter(draft=>draft.changed);
   for(const draft of changed)await draft.editor?.save();
   if([...item.documents.values()].some(draft=>draft.changed))throw Error('Source changes could not be saved. Review the editor error before compiling.');
  }finally{item.savingForCompile=false;}
  item.buildSourceSerial=item.sourceRevisionSerial||0;
  const job=await api('/api/workspaces/project/compile/start',{source:item.source,project:item.project,main,auto_repair:true});
  item.buildStatus=job;item.buildReceivedAt=performance.now();rememberProjectBuild(item);paintProjectBuild(item);
  watchProjectBuild(item);
 }catch(error){clearInterval(item.buildClock);item.compiling=false;projectNotice(item,error.message);paintProjectBuild(item);}
}

async function syncProjectPosition(item,direction){
 if(item.syncing||item.compiling)return;
 const reader=item.pdf,chosen=item.selected,selected=item.activeSource||item.selected,draft=item.documents.get(selected),main=item.data.main;
 if(!reader||!main){toast('Open a compiled PDF first.');return;}
 if(item.pdfPath!==main.replace(/\.(tex|txt)$/i,'.pdf')){toast('Open the PDF for the selected main TeX file first.');return;}
 const sequence=item.syncSequence=(item.syncSequence||0)+1,current=()=>item.syncSequence===sequence&&item.pdf===reader&&item.selected===chosen;
 item.syncing=true;item.layer.querySelectorAll('[data-project-sync]').forEach(button=>{button.disabled=true;button.setAttribute('aria-busy','true')});
 try{
  const sync=await import('/static/js/latex-sync.js'),dirty=item.sourceSavedSincePreview||[...item.documents.values()].some(doc=>doc.changed);
  if(direction==='forward'){
   const selection=draft?.editor?.getSelection();if(!selection||!isProjectTeX({path:selected})){toast('Place the cursor in a TeX file, or select source text.');return;}
   const query=sync.sourceSnippet(draft.editor.getSource(),selection);
   const exact=dirty?null:await api(libraryURL('project/sync',item.source,item.project,{main,direction,path:selected,line:selection.line,column:selection.column}));if(!current())return;
   if(exact?.available){await reader.goToPosition({...exact,screenY:selection.screenY});if(selection.to>selection.from&&query)await reader.findText(query,{pageHint:exact.page});if(current())toast('Located PDF from the TeX cursor.');}
   else{const result=await reader.findText(query,{highlight:selection.to>selection.from,screenY:selection.screenY});if(!current())return;toast(result.matched?(selection.to===selection.from?'Located the corresponding PDF line.':result.partial?'Located matching passage in the PDF.':'Highlighted matching text in the PDF.'):'No matching PDF text. Compile the current source for precise positioning.');}
  }else{
   const context=await reader.getSyncContext();if(!context||!current())return;
   const exact=dirty?null:await api(libraryURL('project/sync',item.source,item.project,{main,direction,page:context.page,x:context.x,y:context.y}));if(!current())return;
   const archivePrefix=item.project+'/backup/';
   const isSource=path=>isProjectTeX({path})&&
    (main.startsWith(archivePrefix)||!path.startsWith(archivePrefix));
   let match=null,path=exact?.available&&isSource(exact.path)?exact.path:null,line=path?exact.line:null;
   const read=async target=>{const open=item.documents.get(target);return open?.editor?.getSource()??(await api(libraryURL('project/document',item.source,item.project,{path:target}))).text;};
   if(path){const text=await read(path);if(!current())return;match=sync.chooseSourceMatch(text,context.text,line)||{line};}
   else{
    if(!context.text||context.text.trim().length<10){toast('Select a meaningful PDF phrase, or compile once for coordinate positioning.');return;}
    const paths=[...new Set([selected,main,...item.data.entries.filter(entry=>isProjectTeX(entry)).map(entry=>entry.path)])].filter(isSource);
    const matches=[];let bytes=0;
    for(const target of paths){if(!current())return;const text=await read(target);if(typeof text!=='string')continue;bytes+=text.length;if(bytes>8*1024*1024||matches.length>5)break;const found=sync.sourceMatches(text,context.text,{limit:6});for(const range of found)matches.push({path:target,range});if(target===selected&&found.length===1)break;}
    if(!current())return;
    if(matches.length!==1){toast(matches.length?'This text occurs more than once. Select a longer PDF phrase.':'No matching source text. Select a longer phrase, or compile for precise positioning.');return;}
    path=matches[0].path;match=matches[0].range;
   }
   if(!current())return;await selectProjectFile(item,path);if(item.syncSequence!==sequence||item.pdf!==reader)return;
   const target=item.documents.get(path);await target?.editor?.revealRange(match);toast(match.from===undefined?'Located the source line; the full selected passage could not be matched.':exact?.available?'Located TeX from the PDF position.':'Selected matching text in TeX.');
  }
 }catch(error){if(current())toast(error.message);}
 finally{item.syncing=false;item.layer.querySelectorAll('[data-project-sync]').forEach(button=>{button.disabled=false;button.removeAttribute('aria-busy')});}
}


export {
  scheduleProjectCompile, refreshProjectRepairEdits, paintProjectBuildNotice, paintProjectBuild,
  rememberProjectBuild, watchProjectBuild, resumeProjectBuild, stopProjectBuild, compileProject,
  syncProjectPosition, projectBuildTerminal, projectBuildKey,
};
