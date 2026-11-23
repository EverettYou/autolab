// Notes project editor shell: open layer, source/PDF panes, save, layout.
import {
  icon, renderWorkspace, syncDashboardVisibility, NotesBrowsing,
  esc, toast, modal, api, $, S, W, workspaceURL, workspaceResourceURL, positionDashboard,
  workspaceContent, SplitPanes, DraftRecovery, isProjectTeX, ProjectUI, libraryURL, libraryError,
  libraryStatusNames, invalidateProjectList,
} from './project-shared.js';
import {
  renderProjectTree, bindProjectFiles, chooseProjectFolder, refreshProjectFiles,
  paintProjectTreeFocus, focusProjectEntry, projectFileSelection, paintProjectSelection,
  projectPDFPlaceholder,
} from './project-tree.js';
import {
  scheduleProjectCompile, compileProject, stopProjectBuild, resumeProjectBuild,
  watchProjectBuild, syncProjectPosition, paintProjectBuild,
} from './project-build.js';

function syncProjectLayers(){
 for(const item of ProjectUI.layers.values()){
  const state=W.states[item.workspace.id],wasHidden=item.layer.hidden;item.layer.hidden=S.view!==item.workspace.id||W.sourceOpening?.view===S.view||state?.sourceDocument||state?.project!==item.project||state?.source!==item.source;
  if(item.layer.hidden){closeMainTeXPicker(item);projectNotice(item,'');}
  if(!item.layer.hidden){
   positionDashboard(item.layer);
   if(wasHidden){
    projectNotice(item,'');
    if(item.pdf){item.pendingPDFReading={path:item.pdfPath,position:savedProjectPDFPosition(item,item.pdfPath)};restorePendingProjectPDF(item);}
   }
  }
 }
}
const projectEditorPanes=[['source','TeX','file-tex'],['pdf','PDF','file-pdf']];
function visibleProjectPDFPosition(item){
 const bounds=item.pdf?.root?.getBoundingClientRect();
 return bounds?.width>0&&bounds?.height>0?item.pdf.getReadingPosition?.():null;
}
function savedProjectPDFPosition(item,path){
 return W.states[item.workspace.id]?.pdfReaders?.find(record=>record.source===item.source&&record.project===item.project&&record.path===path)?.position;
}
function restorePendingProjectPDF(item){
 const pending=item.pendingPDFReading,reader=item.pdf;if(!pending?.position){item.pendingPDFReading=null;return;}if(!reader||pending.path!==item.pdfPath)return;
 // A hidden reader has no usable page geometry. Wait for the visible pane's
 // resize/fit work before applying the saved coordinates and allowing capture.
 requestAnimationFrame(()=>requestAnimationFrame(()=>{
  if(item.pdf!==reader||item.pendingPDFReading!==pending)return;
  const bounds=reader.root.getBoundingClientRect();if(!bounds.width||!bounds.height)return;
  if(reader.restoreReadingPosition?.(pending.position)){item.pendingPDFReading=null;rememberProjectEditor(item);}
 }));
}
function rememberProjectPDF(item){
 const state=W.states[item.workspace.id];if(state?.source!==item.source||state?.project!==item.project||!item.pdfPath)return;
 if(item.pendingPDFReading?.position&&item.pendingPDFReading.path===item.pdfPath)return;
 const position=visibleProjectPDFPosition(item);if(!position)return;
 const readers=state.pdfReaders||[],previous=readers.find(record=>record.source===item.source&&record.project===item.project&&record.path===item.pdfPath);
 const record=NotesBrowsing.clean(item.workspace.id,{pdfReaders:[{source:item.source,project:item.project,path:item.pdfPath,updatedAt:Date.now(),position}]}).pdfReaders?.[0];if(!record)return;
 if(previous&&JSON.stringify(previous.position)===JSON.stringify(record.position))return;
 state.pdfReaders=NotesBrowsing.clean(item.workspace.id,{pdfReaders:[...readers,record]}).pdfReaders;
}
function projectEditorLocation(item){
 rememberProjectPDF(item);
 return {source:item.source,project:item.project,layout:item.layout,treeVisible:!item.layer.classList.contains('hide-tree'),treeWidth:item.treeWidth,sourceRatio:item.ratio,
  folder:item.folder,focused:item.focused,openFolders:[...item.layer.querySelectorAll('[data-project-folder][open]')].map(node=>node.dataset.projectFolder)};
}
function rememberProjectEditor(item){
 const state=W.states[item.workspace.id];
 if(item.editorReady&&S.view===item.workspace.id&&state?.source===item.source&&state?.project===item.project)NotesBrowsing.checkpoint({route:false});
}
function setProjectTreeVisible(item,visible){
 item.layer.classList.toggle('hide-tree',!visible);item.layer.querySelector('[data-toggle-tree]')?.setAttribute('aria-pressed',String(visible));rememberProjectEditor(item);
}
function setProjectEditorLayout(item,layout){
 if(!['split','source','pdf'].includes(layout))return;
 rememberProjectPDF(item);
 if(item.pdf&&layout==='source')item.pendingPDFReading={path:item.pdfPath,position:savedProjectPDFPosition(item,item.pdfPath)};
 item.layout=layout;item.layer.dataset.layout=layout;
 item.layer.querySelectorAll('[data-project-layout]').forEach(button=>button.setAttribute('aria-pressed',String(layout==='split'||button.dataset.projectLayout===layout)));
 rememberProjectEditor(item);
 if(layout!=='source')restorePendingProjectPDF(item);
}
function toggleProjectEditorPane(item,pane){
 if(item.documentMode&&item.documentMode!=='latex')return;
 if(!projectEditorPanes.some(([key])=>key===pane))return;
 // A sole visible pane remains selected; otherwise toggle this pane independently.
 setProjectEditorLayout(item,item.layout==='split'?(pane==='source'?'pdf':'source'):item.layout===pane?item.layout:'split');
}
async function openProjectEditor(workspace,state){
 const source=state.source,project=state.project,key=JSON.stringify([workspace.id,source,project]);
 let item=ProjectUI.layers.get(key);
 if(item){syncProjectLayers();if(state.document&&state.document!==item.selected)await selectProjectFile(item,state.document);else{const draft=item.documents.get(item.activeSource);if(draft?.editor)await refreshProjectSource(item,draft).catch(error=>draft.editor.setStatus(error.message,true));}return;}
 const layer=document.createElement('section');layer.className='project-editor-layer';layer.setAttribute('aria-label',workspace.title+' project editor');
 const host=document.getElementById('workspace')||document.body;host.append(layer);
 const saved=NotesBrowsing.clean(workspace.id,state).editor,editor=saved?.source===source&&saved.project===project?saved:{};
 item={workspace,source,project,layer,documents:new Map(),request:0,pdfRequest:0,selected:null,layout:editor.layout||'split',treeWidth:editor.treeWidth??null,ratio:editor.sourceRatio??.5,savedEditor:editor};
 ProjectUI.layers.set(key,item);syncProjectLayers();layer.innerHTML=`<header class="project-toolbar"><h1>${esc(project)}</h1></header><div class="empty" role="status">Opening project…</div>`;
 item.observer=new ResizeObserver(()=>{if(!layer.hidden)positionDashboard(layer);});item.observer.observe($('workspace-content'));
 try{
  item.data=await api(libraryURL('project',source,project));
  try{const main=localStorage.getItem('notes-main-tex:'+JSON.stringify([source,project]));if(main===''){item.data.main=null;item.data.pdf=null;}else if(item.data.entries.some(e=>e.path===main&&isProjectTeX(e))){item.data.main=main;item.data.pdf=item.data.entries.find(e=>e.path===main.replace(/\.(tex|txt)$/i,'.pdf'))?.path||null;}}catch{}
  const data=item.data,latex=workspace.editor_layout==='latex';
  const statusOptions=workspace.status_options||['finished'];item.folder=project;
  const statusControl=workspace.id==='papers'?'':`<select data-project-status aria-label="Project status"><option value="automatic">${workspace.period_labels?'Automatic by folder date':workspace.status_options?'Unclassified':'Automatic activity'}</option>${statusOptions.map(s=>`<option value="${s}" ${data.status===s?'selected':''}>${libraryStatusNames[s]}</option>`).join('')}</select>`;
  layer.classList.toggle('project-latex',latex);
  layer.innerHTML=`<header class="project-toolbar"><button type="button" class="icon-button" data-project-back aria-label="Back to ${esc(workspace.title)}" title="Back to ${esc(workspace.title)}">${icon('previous')}</button><h1 title="${esc(project)}">${esc(project)}</h1>${workspace.id==='papers'?globalThis.WorkbenchReferences?.button('paper.project',{source,project},project)||'':''}${statusControl}<button type="button" class="icon-button" data-toggle-tree aria-label="File tree" title="File tree" aria-pressed="true">${icon('folder-tree')}</button>${latex?`<div class="project-layout-toggle" role="group" aria-label="Editor layout">${projectEditorPanes.map(([key,label,glyph])=>`<button type="button" class="icon-button" data-project-layout="${key}" aria-label="${label}" title="${label}" aria-pressed="${item.layout==='split'||item.layout===key}">${icon(glyph)}</button>`).join('')}</div><span class="project-compile-controls" data-project-compile-controls><button type="button" class="primary-button" data-project-compile>${icon('play')} Compile</button></span><button type="button" class="text-button" data-project-log hidden>View log</button><button type="button" class="text-button" data-project-stop hidden>Stop</button>`:''}</header><div class="project-error" role="alert" hidden></div><section class="project-build-log" aria-label="Compilation log" hidden><div><strong>Compilation log</strong><button type="button" class="text-button" data-project-log-close>Close log</button></div><pre data-project-log-output tabindex="0"></pre></section><div class="project-grid"><aside class="project-file-tree" aria-label="Project files">${latex?`<div class="project-tree-toolbar"><div class="project-main-picker" data-project-main-picker><span class="project-main-picker-caption">Main file:</span><button type="button" class="project-main-picker-trigger" data-project-main-trigger aria-haspopup="listbox" aria-expanded="false" aria-label="Main file"><span class="project-main-picker-value" data-project-main-label>Select main file</span>${icon('down')}</button><ul class="project-main-picker-menu" data-project-main-menu role="listbox" hidden></ul></div></div>`:''}${workspace.file_operations?`<div class="project-explorer-tools"><button type="button" data-folder-root class="project-folder-location" title="Select project root">${icon('folder')}<span data-folder-location>Project root</span></button><button type="button" class="icon-button" data-new-file title="New file" aria-label="New file">${icon('file-plus')}</button><button type="button" class="icon-button" data-new-folder title="New folder" aria-label="New folder">${icon('folder-plus')}</button></div><form class="project-create-form" data-create-form hidden><label data-create-label>File name<input name="name" required maxlength="255" autocomplete="off" aria-label="New item name"></label><div><button type="button" data-create-cancel class="text-button">Cancel</button><button type="submit" class="text-button">Create</button></div></form>`:''}${data.errors.length?data.errors.map(e=>`<p class="file-note">${esc(e)}</p>`).join(''):''}<div class="project-tree-entries"></div></aside><div class="project-pane-resizer" data-resize-tree role="separator" aria-label="Resize file tree" aria-orientation="vertical" tabindex="0"></div><section class="project-source-pane"><div class="project-file-toolbar"><span data-file-name>Select a file</span><button type="button" class="text-button" data-file-discard hidden>Discard changes</button></div><div class="project-documents"></div></section>${latex?`<div class="project-source-divider"><div class="project-pane-resizer" data-resize-source role="separator" aria-label="Resize source and PDF panes" aria-orientation="vertical" tabindex="0"></div><div class="project-sync-controls" role="group" aria-label="Synchronize TeX and PDF"><button type="button" class="icon-button" data-project-sync="inverse" aria-label="Sync PDF to TeX" title="Sync PDF to TeX">${icon('previous')}</button><button type="button" class="icon-button" data-project-sync="forward" aria-label="Sync TeX to PDF" title="Sync TeX to PDF">${icon('next')}</button></div></div><section class="project-pdf-pane"><div class="project-pdf-host"><div class="empty">Compile to preview this document.</div></div><div class="project-build-state" data-project-build-state role="status" aria-live="polite" aria-atomic="true" aria-hidden="true"></div></section>`:''}</div>`;
  setProjectTreeVisible(item,editor.treeVisible!==false);renderProjectTree(item);renderMainTeXSelector(item);bindProjectFiles(item);
  layer.querySelector('[data-project-back]').onclick=()=>{closeMainTeXPicker(item);rememberProjectEditor(item);state.project='';state.path='';state.document=null;renderWorkspace();};
  layer.querySelector('[data-toggle-tree]').onclick=()=>setProjectTreeVisible(item,layer.classList.contains('hide-tree'));
  const statusSelect=layer.querySelector('[data-project-status]');if(statusSelect)statusSelect.onchange=async e=>{const select=e.target;select.disabled=true;try{const result=await api('/api/workspaces/project/status',{source,project,status:select.value,revision:data.label_revision});data.status=select.value;data.label_revision=result.label_revision;invalidateProjectList(workspace);}catch(error){projectNotice(item,error.message);select.value=data.status;}finally{select.disabled=false;}};
  // Keep diagnostics below the editor; opening the log is always explicit.
  const buildLog=layer.querySelector('.project-build-log');if(buildLog)layer.append(buildLog);
  layer.querySelector('[data-file-discard]').onclick=()=>discardProjectFile(item);
  bindProjectPaneResize(item);
  if(latex){
   layer.querySelectorAll('[data-project-layout]').forEach(button=>button.onclick=()=>toggleProjectEditorPane(item,button.dataset.projectLayout));
   setProjectEditorLayout(item,item.layout);
   layer.querySelectorAll('[data-project-sync]').forEach(button=>button.onclick=()=>syncProjectPosition(item,button.dataset.projectSync));
   bindMainTeXPicker(item);
   layer.querySelector('[data-project-compile]').onclick=()=>compileProject(item);
   layer.querySelector('[data-project-log]').onclick=()=>{const log=layer.querySelector('.project-build-log');log.hidden=!log.hidden;};
   layer.querySelector('[data-project-log-close]').onclick=()=>{layer.querySelector('.project-build-log').hidden=true;};
   layer.querySelector('[data-project-stop]').onclick=()=>stopProjectBuild(item);
  }
  const first=(data.entries.some(entry=>entry.path===state.document&&!entry.directory)?state.document:null)||data.main||data.entries.find(e=>e.extension==='.pdf')?.path||data.entries.find(e=>!e.directory)?.path||data.entries[0]?.path||project;
  if(first)await selectProjectFile(item,first);else layer.querySelector('.project-documents').innerHTML='<div class="empty">This project is empty.</div>';
  // Restore the tree after selection's normal ancestor-opening behavior.
  if(editor.openFolders){const opened=new Set(editor.openFolders);layer.querySelectorAll('[data-project-folder]').forEach(node=>node.open=opened.has(node.dataset.projectFolder));}
  if(editor.folder&&(editor.folder===project||data.entries.some(entry=>entry.directory&&entry.path===editor.folder)))chooseProjectFolder(item,editor.folder);
  if(editor.focused&&(editor.focused===project||data.entries.some(entry=>entry.path===editor.focused))){item.focused=editor.focused;paintProjectTreeFocus(item);}
  item.editorReady=true;rememberProjectEditor(item);
  if(latex)resumeProjectBuild(item);
 }catch(error){libraryError(layer,error);const header=document.createElement('header');header.className='project-toolbar';header.innerHTML=`<h1>${esc(project)}</h1>`;layer.prepend(header);const back=document.createElement('button');back.className='text-button';back.textContent='Back to '+workspace.title;back.onclick=()=>{closeMainTeXPicker(item);item.mainPickerMenu?.remove();state.project='';state.path='';state.document=null;ProjectUI.layers.delete(key);item.observer.disconnect();layer.remove();renderWorkspace();};layer.append(back);}
 syncProjectLayers();
}
function projectNotice(item,text,{transient=false}={}){
 const error=item.layer.querySelector('.project-error');if(!error)return;
 clearTimeout(item.noticeTimer);item.noticeTimer=null;
 if(!text){error.hidden=true;error.replaceChildren();return;}
 const message=document.createElement('div');message.className='project-error-message';message.textContent=text;
 const dismiss=document.createElement('button');dismiss.type='button';dismiss.className='text-button project-error-dismiss';dismiss.textContent='Dismiss';dismiss.onclick=()=>projectNotice(item,'');
 error.replaceChildren(message,dismiss);error.hidden=false;
 if(transient)item.noticeTimer=setTimeout(()=>projectNotice(item,''),8000);
}
function updateProjectBuildState(item){
 paintProjectBuild(item);
}
function paintProjectMainBadge(item){
 item.layer.querySelectorAll('[data-project-file]').forEach(button=>{
  const badge=button.querySelector('.project-main-badge');
  if(button.dataset.projectFile!==item.data.main)badge?.remove();
  else if(!badge){const mark=document.createElement('small');mark.className='project-main-badge';mark.textContent='Main';button.insertBefore(mark,button.querySelector('.project-dirty-marker'));}
 });
}
function mainTeXPickerMenu(item){
 return item.mainPickerMenu||item.layer.querySelector('[data-project-main-menu]');
}
function renderMainTeXSelector(item){
 const picker=item.layer.querySelector('[data-project-main-picker]');if(!picker)return;
 const label=picker.querySelector('[data-project-main-label]');
 const menu=mainTeXPickerMenu(item);if(!menu)return;
 const options=item.data.entries.filter(entry=>!entry.directory&&isProjectTeX(entry));
 const current=item.data.main||'';
 const currentEntry=options.find(entry=>entry.path===current);
 label.textContent=currentEntry?currentEntry.path.slice(item.project.length+1):(options.length?'Select main file':'No TeX files');
 menu.innerHTML=options.map(entry=>{
  const rel=entry.path.slice(item.project.length+1);
  const selected=entry.path===current;
  return `<li role="option" data-value="${esc(entry.path)}" aria-selected="${selected?'true':'false'}" class="${selected?'is-selected':''}"><button type="button">${esc(rel)}</button></li>`;
 }).join('')||'<li class="project-main-picker-empty">No TeX files</li>';
 paintProjectMainBadge(item);
}
function closeMainTeXPicker(item){
 const picker=item.layer.querySelector('[data-project-main-picker]');if(!picker)return;
 const trigger=picker.querySelector('[data-project-main-trigger]');
 const menu=mainTeXPickerMenu(item);if(!menu)return;
 menu.hidden=true;trigger.setAttribute('aria-expanded','false');picker.classList.remove('is-open');
}
function placeMainTeXPickerMenu(item){
 const picker=item.layer.querySelector('[data-project-main-picker]');if(!picker)return;
 const trigger=picker.querySelector('[data-project-main-trigger]');
 const menu=mainTeXPickerMenu(item);if(!menu)return;
 const rect=trigger.getBoundingClientRect();
 const maxWidth=Math.max(120,Math.min(360,window.innerWidth-rect.left-12));
 const maxHeight=Math.max(120,Math.min(280,window.innerHeight-rect.bottom-12));
 menu.style.left=Math.round(rect.left)+'px';
 menu.style.top=Math.round(rect.bottom+4)+'px';
 menu.style.width='max-content';
 menu.style.maxWidth=maxWidth+'px';
 menu.style.maxHeight=maxHeight+'px';
}
function bindMainTeXPicker(item){
 const picker=item.layer.querySelector('[data-project-main-picker]');if(!picker||picker.dataset.bound)return;
 picker.dataset.bound='1';
 const trigger=picker.querySelector('[data-project-main-trigger]');
 const menu=picker.querySelector('[data-project-main-menu]');
 // Host on body so the file-tree overflow does not clip the floating menu.
 if(menu.parentElement!==document.body)document.body.append(menu);
 item.mainPickerMenu=menu;
 const open=()=>{
  renderMainTeXSelector(item);
  menu.hidden=false;trigger.setAttribute('aria-expanded','true');picker.classList.add('is-open');
  placeMainTeXPickerMenu(item);
 };
 trigger.addEventListener('click',event=>{
  event.preventDefault();event.stopPropagation();
  if(menu.hidden)open();else closeMainTeXPicker(item);
 });
 menu.addEventListener('click',event=>{
  const option=event.target.closest('[data-value]');if(!option)return;
  event.preventDefault();event.stopPropagation();
  closeMainTeXPicker(item);
  changeMainTeX(item,option.dataset.value);
 });
 document.addEventListener('click',event=>{if(!picker.contains(event.target)&&!menu.contains(event.target))closeMainTeXPicker(item);});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!menu.hidden){closeMainTeXPicker(item);trigger.focus();}});
 window.addEventListener('resize',()=>{if(!menu.hidden)placeMainTeXPickerMenu(item);});
 window.addEventListener('scroll',()=>{if(!menu.hidden)placeMainTeXPickerMenu(item);},true);
}
function changeMainTeX(item,path){
 if(!item.data.entries.some(entry=>entry.path===path&&!entry.directory&&isProjectTeX(entry))){renderMainTeXSelector(item);return;}
 if(item.data.main===path)return;
 item.data.main=path;
 try{localStorage.setItem('notes-main-tex:'+JSON.stringify([item.source,item.project]),path);}catch{}
 renderMainTeXSelector(item);
 if(item.documentMode==='latex'&&item.activeSource)return selectProjectFile(item,item.activeSource);
}
async function selectProjectFile(item,path){
 if(item.fileMutationPath&&projectPathWithin(path,item.fileMutationPath))return;
 rememberProjectPDF(item);
 const selection=projectFileSelection(item,path);
 if(selection.mode==='folder'){focusProjectEntry(item,path,true);return;}
 const current=item.selectionRequest=(item.selectionRequest||0)+1,layer=item.layer;
 item.pdfRequest++;item.selected=path;item.documentMode=selection.mode;item.activeSource=selection.source||null;
 focusProjectEntry(item,path);
 const toolbar=layer.querySelector('.project-file-toolbar');
 toolbar?.querySelector('[data-reference]')?.remove();
 if(item.workspace.id==='papers'&&item.source&&path)toolbar?.insertAdjacentHTML('beforeend',globalThis.WorkbenchReferences?.button('workspace.file',{source:item.source,path},path.split('/').at(-1))||'');
 const state=W.states[item.workspace.id];if(state?.project===item.project)state.document=path;
 const selected=[...layer.querySelectorAll('[data-project-file],[data-project-folder]')].find(node=>(node.dataset.projectFile||node.dataset.projectFolder)===path);
 for(let parent=selected?.parentElement;parent&&parent!==layer;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
 renderMainTeXSelector(item);paintProjectSelection(item);projectNotice(item,'');
 if(selection.source)await showProjectSource(item,selection.source,current);
 if(current!==item.selectionRequest)return;
 if(item.workspace.editor_layout==='latex'&&selection.source&&(
  selection.mode==='latex'||typeof item.documents.get(selection.source)?.doc?.text==='string')){
  item.documentMode=selection.mode='latex';
  const output=item.data.main?.replace(/\.(tex|txt)$/i,'.pdf');
  selection.pdf=item.data.entries.find(entry=>entry.path===output)?.path;
  paintProjectSelection(item);
 }
 if(selection.pdf){
  if(item.pdf&&item.pdfPath===selection.pdf){const host=layer.querySelector('.project-pdf-host');host?.querySelectorAll(':scope>.empty').forEach(node=>node.remove());const shown=host?.querySelector('.project-pdf-current');if(shown?.hidden)item.pendingPDFReading={path:selection.pdf,position:savedProjectPDFPosition(item,selection.pdf)};if(shown)shown.hidden=false;restorePendingProjectPDF(item);}
  else{projectPDFPlaceholder(item,'Opening PDF…');try{await showProjectPDF(item,{path:selection.pdf});}catch(error){if(current===item.selectionRequest){projectNotice(item,error.message);projectPDFPlaceholder(item,'This PDF could not be opened.');}}}
 }else if(selection.mode==='latex')projectPDFPlaceholder(item,'Compile to preview this document.');
 if(current===item.selectionRequest)updateProjectBuildState(item);
}
async function showProjectSource(item,path,current){
 const layer=item.layer;item.request++;
 layer.querySelector('[data-file-name]').textContent=path===item.project?'Project root':path.slice(item.project.length+1);
 layer.querySelectorAll('.project-document').forEach(node=>node.hidden=true);
 const discard=layer.querySelector('[data-file-discard]');discard.hidden=true;layer.querySelector('.project-file-toolbar').hidden=false;
 let draft=item.documents.get(path);
 if(draft){draft.host.hidden=false;discard.hidden=!draft.changed;layer.querySelector('.project-file-toolbar').hidden=item.workspace.editor_layout==='latex'&&draft.doc?.text!==undefined&&!['.md','.json'].includes(draft.doc.extension);if(draft.editor)await refreshProjectSource(item,draft).catch(error=>draft.editor.setStatus(error.message,true));return;}
 const host=document.createElement('div');host.className='project-document';host.innerHTML='<div class="empty">Opening file…</div>';layer.querySelector('.project-documents').append(host);
 draft={host,path,changed:false};item.documents.set(path,draft);
 try{
  const doc=await api(libraryURL('project/document',item.source,item.project,{path}));draft.doc=doc;draft.saved=doc.text;draft.text=doc.text;
  if(!host.isConnected)return;
  const ui=await import('/static/js/content.js');
  if(current===item.selectionRequest)layer.querySelector('.project-file-toolbar').hidden=item.workspace.editor_layout==='latex'&&doc.text!==undefined&&!['.md','.json'].includes(doc.extension);
  if(doc.text!==undefined){
   draft.editor=ui.mountContent(host,{source:doc.text,format:doc.extension==='.md'?'markdown':doc.extension==='.json'?'json':'text',extension:isProjectTeX(doc)?'tex':doc.extension.slice(1),sourceMode:item.workspace.editor_layout==='latex'||!['.md','.json','.txt'].includes(doc.extension),sourceOnly:item.workspace.editor_layout==='latex'&&!['.md','.json'].includes(doc.extension),sourceTitle:path.slice(item.project.length+1),readOnly:!doc.editable,stateKey:item.source+':'+path,recoveryContext:{capture:()=>({revision:doc.revision,saved:draft.saved}),restore:value=>{if(value?.revision){doc.revision=value.revision;draft.saved=value.saved;}}},ariaLabel:'Source editor: '+doc.name,resolveResource:(href,image)=>workspaceResourceURL(item.source,path,href,image),onInput:text=>{draft.text=text;draft.changed=text!==draft.saved;updateProjectDirty(item,draft);scheduleProjectSourceSave(item,draft);},onSave:doc.editable?text=>saveProjectSource(item,draft,doc,path,text):null,onReload:()=>refreshProjectSource(item,draft,{review:true})});
   startProjectSourceSync(item,draft);
  }else if(doc.extension==='.pdf')draft.reader=ui.mountPDF(host,{pages:doc.pages,title:doc.name,stateKey:item.source+':'+path,url:workspaceURL('file',item.source,path)});
  else if(['.png','.jpg','.jpeg','.svg'].includes(doc.extension)){host.innerHTML=`<div class="project-image"><img src="${esc(workspaceURL('image',item.source,path))}" alt="${esc(doc.name)}"></div>`;}
  else host.innerHTML=`<div class="project-file-placeholder">${icon('document')}<span>${esc(doc.name)}</span><small>No preview available</small></div>`;
  if(current!==item.selectionRequest)host.hidden=item.activeSource!==path;
 }catch(error){if(host.isConnected)libraryError(host,error);}
}
function scheduleProjectSourceSave(item,draft){
 clearTimeout(draft.autoSaveTimer);
 if(!draft.doc?.editable||!draft.changed||draft.conflict||draft.handoff)return;
 draft.autoSaveTimer=setTimeout(async()=>{
  if(item.documents.get(draft.path)!==draft||!draft.host.isConnected)return;
  if(draft.saving){scheduleProjectSourceSave(item,draft);return;}
  await draft.editor.save();
 },700);
}
function projectEditorSyncPayload(item,draft,extra={}){
 return {source:item.source,project:item.project,path:draft.path,session:draft.syncSession,...extra};
}
function releaseProjectEditorHandoff(draft){
 clearTimeout(draft.handoffTimer);
 if(draft.handoff){draft.host.inert=draft.handoffInert;draft.handoff=null;}
}
async function syncProjectEditorHandoff(item,draft){
 if(!draft.doc.editor_sync)return;
 if(!draft.syncSession){
  const key='notes-editor-session:'+JSON.stringify([item.source,item.project,draft.path]);
  try{draft.syncSession=sessionStorage.getItem(key);if(!draft.syncSession){draft.syncSession=crypto.randomUUID();sessionStorage.setItem(key,draft.syncSession);}}
  catch{draft.syncSession=crypto.randomUUID();}
 }
 const result=await api('/api/workspaces/project/editor-sync',projectEditorSyncPayload(item,draft));
 const request=result.handoff;
 if(!request){
  const held=!!draft.handoff;releaseProjectEditorHandoff(draft);
  if(held){await refreshProjectSource(item,draft);draft.editor.setStatus(draft.changed?'Unsaved changes':'Latest file loaded');scheduleProjectSourceSave(item,draft);}
  return;
 }
 if(draft.handoff===request.id)return;
 draft.handoff=request.id;draft.handoffInert=draft.host.inert;draft.host.inert=true;
 clearTimeout(draft.autoSaveTimer);
 // A failed connection cannot leave an editor locked indefinitely.
 draft.handoffTimer=setTimeout(()=>{releaseProjectEditorHandoff(draft);draft.editor.setStatus('Editor handoff expired. Your edits are kept.',true);},request.remaining_ms);
 let error=null;
 try{
  draft.editor.setStatus('Saving your edits before agent changes…');
  const deadline=Date.now()+request.remaining_ms;
  while(draft.saving||draft.refreshing){if(Date.now()>=deadline)throw Error('Editor save did not finish.');await new Promise(r=>setTimeout(r,20));}
  if(!await refreshProjectSource(item,draft)||draft.conflict)throw Error('Resolve overlapping changes before the agent edits.');
  if(draft.changed)await draft.editor.save();
  if(draft.changed||draft.saving)throw Error('Your edits could not be saved. Agent edit blocked.');
  draft.editor.setStatus('Your edits are saved. Applying agent changes…');
 }catch(problem){error=problem.message;draft.editor.setStatus(error,true);}
 await api('/api/workspaces/project/editor-sync',projectEditorSyncPayload(item,draft,{request:request.id,revision:draft.doc.revision,error}));
}
function closeProjectEditorSync(item,draft){
 if(!draft.syncSession||draft.changed||draft.saving||draft.handoff)return;
 void api('/api/workspaces/project/editor-sync',projectEditorSyncPayload(item,draft,{closed:true})).catch(()=>{});
}
window.addEventListener('pagehide',()=>{for(const item of ProjectUI.layers.values())for(const draft of item.documents.values())closeProjectEditorSync(item,draft);});
function startProjectSourceSync(item,draft){
 // Keep the mounted editor, selection and undo history; reconcile its source only.
 const poll=async()=>{
  if(item.documents.get(draft.path)!==draft||!draft.host.isConnected){closeProjectEditorSync(item,draft);return;}
  try{
   await syncProjectEditorHandoff(item,draft);
   if(!draft.handoff&&!item.fileBusy&&!draft.saving&&!draft.refreshing&&!document.hidden&&!draft.host.hidden)
    await refreshProjectSource(item,draft);
  }catch(error){draft.editor.setStatus(error.message,true);}
  finally{if(item.documents.get(draft.path)===draft&&draft.host.isConnected)draft.sourceSyncTimer=setTimeout(poll,1000);}
 };
 void poll();
}
async function adoptProjectSource(item,draft,latest,text,expected){
 if(item.documents.get(draft.path)!==draft||!draft.host.isConnected)return false;
 if(!await draft.editor.updateSource(text,{saved:latest.text,expected}))return false;
 Object.assign(draft.doc,latest);draft.saved=latest.text;draft.text=draft.editor.getSource();draft.changed=draft.text!==draft.saved;draft.conflict=null;
 const entry=item.data.entries.find(entry=>entry.path===draft.path);if(entry&&latest.file_revision)entry.file_revision=latest.file_revision;
 updateProjectDirty(item,draft);return true;
}
function projectSourceConflict(item,draft){
 const error=Error('File changed on disk. Click to merge the latest file with your edits.');
 error.recovery={label:'Merge latest file',run:()=>refreshProjectSource(item,draft,{review:true})};
 return error;
}
async function refreshProjectSource(item,draft,{review=false}={}){
 if(!draft.editor||draft.saving)return false;
 draft.refreshing=true;
 try{
 const serial=draft.refreshSerial=(draft.refreshSerial||0)+1;
 const metadata=await api(libraryURL('project/document',item.source,item.project,{path:draft.path,meta:'1'}));
 if(serial!==draft.refreshSerial||item.documents.get(draft.path)!==draft||draft.saving)return false;
 if(metadata.file_revision&&metadata.file_revision===draft.doc.file_revision&&!draft.conflict)return true;
 const latest=await api(libraryURL('project/document',item.source,item.project,{path:draft.path}));
 if(serial!==draft.refreshSerial||item.documents.get(draft.path)!==draft||draft.saving)return false;
 if(typeof latest.text!=='string'||!latest.revision||draft.doc.editable&&!latest.editable)throw Error('The latest file is no longer editable text. Your edits are kept.');
 if(latest.revision===draft.doc.revision&&!draft.conflict){Object.assign(draft.doc,latest);return true;}
 const ui=await import('/static/js/content.js');
 const local=draft.editor.getSource(),external=latest.revision!==draft.doc.revision,merged=ui.mergeSourceChanges(draft.saved,local,latest.text);
 if(merged===null){
  draft.conflict=latest;const error=projectSourceConflict(item,draft);draft.editor.setStatus('Changes overlap. Click to review both versions. Your edits are kept.',true,error.recovery);
  if(review)reviewProjectSource(item,draft,latest,local);
  return false;
 }
 if(!await adoptProjectSource(item,draft,latest,merged,local))throw Error('Your editor changed while loading. Your edits are kept; try Reload latest file again.');
 draft.editor.setStatus(draft.changed?(external?'Changes merged. Saving…':'Unsaved changes'):'Latest file loaded');
 scheduleProjectSourceSave(item,draft);
 return true;
 }finally{draft.refreshing=false;}
}
function reviewProjectSource(item,draft,latest,local){
 modal('Review changed file',`<p class="info-copy">Both versions changed the same text. Compare the latest file with your edits, then choose the text to keep. This updates the editor; Save changes writes the file.</p><label class="field">Latest file<textarea readonly aria-label="Latest file">${esc(latest.text)}</textarea></label><label class="field">Your reviewed text<textarea name="reviewed" aria-label="Your reviewed text">${esc(local)}</textarea></label>`,'<button type="button" class="text-button" data-source-review-cancel>Cancel</button><button type="submit" class="primary-button">Use reviewed text</button>',async form=>{
  if(draft.editor.getSource()!==local)throw Error('Your editor changed. Close this review and reload the latest file again.');
  const current=await api(libraryURL('project/document',item.source,item.project,{path:draft.path}));
  if(current.revision!==latest.revision)throw Error('The file changed again. Close this review and reload the latest file again.');
  if(!await adoptProjectSource(item,draft,current,String(form.get('reviewed')),local))throw Error('Your edits are kept. Reload the latest file again.');
  $('workspace-modal').close();scheduleProjectSourceSave(item,draft);
 });
 $('workspace-modal').querySelector('[data-source-review-cancel]').onclick=()=>$('workspace-modal').close();
}
async function saveProjectSource(item,draft,doc,path,text){
 if(draft.saving)return false;
 clearTimeout(draft.autoSaveTimer);
 draft.saving=true;
 let saved=false;
 try{
  let result;
  for(let attempt=0;attempt<3;attempt++){
   try{result=await api('/api/workspaces/project/save',{source:item.source,project:item.project,path,text,revision:doc.revision});break;}
   catch(error){
    if(error.status!==409)throw error;
    draft.saving=false;
    const reconciled=await refreshProjectSource(item,draft);
    draft.saving=true;
    if(!reconciled)throw projectSourceConflict(item,draft);
    text=draft.editor.getSource();
    if(!draft.changed){saved=true;return {savedSource:draft.saved};}
    if(attempt===2)throw projectSourceConflict(item,draft);
   }
  }
  doc.revision=result.revision;doc.file_revision=result.file_revision;const entry=item.data.entries.find(entry=>entry.path===path);if(entry)entry.file_revision=result.file_revision;
  draft.saved=text;draft.text=draft.editor.getSource();draft.changed=draft.text!==text;draft.conflict=null;item.sourceSavedSincePreview=true;item.sourceRevisionSerial=(item.sourceRevisionSerial||0)+1;
  updateProjectDirty(item,draft);invalidateProjectList(item.workspace);
  if(item.workspace.editor_layout==='latex'&&isProjectTeX(doc)&&!item.savingForCompile)scheduleProjectCompile(item);
  saved=true;return {savedSource:text};
 }finally{draft.saving=false;if(saved&&draft.changed&&!draft.conflict)scheduleProjectSourceSave(item,draft);}
}

function updateProjectDirty(item,draft){
 const button=[...item.layer.querySelectorAll('[data-project-file]')].find(b=>b.dataset.projectFile===draft.path);if(button)button.querySelector('.project-dirty-marker').hidden=!draft.changed;
 if((item.activeSource||item.selected)===draft.path)item.layer.querySelector('[data-file-discard]').hidden=!draft.changed;
 updateProjectBuildState(item);
}
async function discardProjectFile(item){
 const draft=item.documents.get(item.activeSource||item.selected);if(!draft||!draft.changed||draft.handoff)return;
 draft.editor?.destroy();draft.host.remove();item.documents.delete(draft.path);draft.changed=false;updateProjectDirty(item,draft);await selectProjectFile(item,item.selected||draft.path);
}
async function showProjectPDF(item,pdf){
 rememberProjectPDF(item);
 const request=++item.pdfRequest,host=item.layer.querySelector('.project-pdf-host');
 // Mount the replacement at full pane size while keeping the old reader visible.
 const staged=document.createElement('div');staged.className='project-pdf-swap';host.append(staged);let reader;
 try{
  const ui=await import('/static/js/content.js');let pages=pdf.pages;
  if(pdf.path&&!pages){const doc=await api(libraryURL('project/document',item.source,item.project,{path:pdf.path}));pages=doc.pages;}
  if(request!==item.pdfRequest){staged.remove();return;}
  reader=ui.mountPDF(staged,{pages,title:pdf.path?.split('/').at(-1)||'Compiled document',stateKey:item.source+':'+(pdf.path||item.project)+':pdf',url:pdf.build?libraryURL('build/file',item.source,item.project,{build:pdf.build}):workspaceURL('file',item.source,pdf.path)});
  await reader.ready;
  if(request!==item.pdfRequest){reader.destroy();staged.remove();return;}
  // Take the latest position while the previous PDF is still visible: the
  // user may have kept reading during compilation and replacement loading.
  const previous=item.pdfPath===pdf.path?item.pdf:null,position=(previous&&visibleProjectPDFPosition(item))||savedProjectPDFPosition(item,pdf.path);
  const page=Number(previous?.root?.querySelector('[data-page]')?.value),zoom=parseFloat(previous?.root?.querySelector('[data-zoom]')?.value);
  item.pdf?.destroy();host.replaceChildren(staged);staged.className='project-pdf-current';
  // Restore in the final layout. Moving a staged scroller can reset its offsets.
  const bounds=reader.root.getBoundingClientRect();
  item.pendingPDFReading=position&&(!bounds.width||!bounds.height)?{path:pdf.path,position}:null;
  if(!item.pendingPDFReading&&(!position||!reader.restoreReadingPosition?.(position))){
   if(Number.isFinite(zoom)&&zoom>0)reader.setZoom?.(zoom/100);
   if(Number.isFinite(page)&&page>0)reader.goToPage?.(page);
  }
  item.pdf=reader;item.pdfPath=pdf.path||null;item.pdfHash=pdf.pdf_sha256||null;
  if(pdf.sourceSerial===undefined||pdf.sourceSerial===(item.sourceRevisionSerial||0))item.sourceSavedSincePreview=false;
  updateProjectBuildState(item);rememberProjectEditor(item);
 }catch(error){reader?.destroy();staged.remove();throw error;}
}
function bindProjectPaneResize(item){
 const layer=item.layer,grid=layer.querySelector('.project-grid');
 item.treeWidth??=parseFloat(getComputedStyle(grid).getPropertyValue('--project-tree-width'))||210;
 grid.style.setProperty('--project-tree-width',item.treeWidth+'px');grid.style.setProperty('--source-share',item.ratio+'fr');grid.style.setProperty('--pdf-share',(1-item.ratio)+'fr');
 for(const [selector,kind] of [['[data-resize-tree]','tree'],['[data-resize-source]','source']]){
  const handle=layer.querySelector(selector);if(!handle)continue;
  const available=()=>Math.max(200,grid.clientWidth-(layer.classList.contains('hide-tree')?0:item.treeWidth));
  const get=()=>kind==='tree'?item.treeWidth:item.ratio*available();
  const set=value=>{if(kind==='tree'){item.treeWidth=Math.max(130,Math.min(430,value));grid.style.setProperty('--project-tree-width',item.treeWidth+'px');}else{item.ratio=Math.max(.2,Math.min(.8,value/available()));grid.style.setProperty('--source-share',item.ratio+'fr');grid.style.setProperty('--pdf-share',(1-item.ratio)+'fr');}handle.setAttribute('aria-valuenow',Math.round(get()));};
  handle.setAttribute('aria-valuenow',Math.round(get()));SplitPanes.drag(handle,{get,set,finish:()=>rememberProjectEditor(item)});
 }
}
window.addEventListener('workbench-before-update',e=>{if([...ProjectUI.layers.values()].some(item=>[...item.documents.values()].some(d=>d.changed&&!d.editor?.recoverySafe?.()))){e.detail?.block?.('project-document-unsaved');e.preventDefault();e.returnValue='';}});

export {
  syncProjectLayers, projectEditorLocation, openProjectEditor, projectNotice, updateProjectBuildState,
  paintProjectMainBadge, closeMainTeXPicker, selectProjectFile, showProjectSource, showProjectPDF,
  rememberProjectEditor, updateProjectDirty,
};
