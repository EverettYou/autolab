// Notes project file tree, rename, drop-import, and menus.
import {
  icon, esc, toast, api, $, W, libraryURL, filesToData, isProjectTeX, ActionMenu,
  invalidateProjectList,
} from './project-shared.js';
import {
  projectNotice, selectProjectFile, rememberProjectEditor, paintProjectMainBadge,
  closeMainTeXPicker, updateProjectDirty, renderMainTeXSelector, updateProjectBuildState,
} from './project-editor.js';

function paintProjectTreeFocus(item){
 const path=item.focused??item.selected;
 item.layer.querySelectorAll('[data-project-file]').forEach(button=>button.classList.toggle('selected',button.dataset.projectFile===path));
 item.layer.querySelectorAll('[data-project-folder]').forEach(folder=>{
  const focused=folder.dataset.projectFolder===path;folder.parentElement.classList.toggle('tree-focused',focused);
  const heading=folder.querySelector(':scope>summary');if(focused)heading?.setAttribute('aria-current','true');else heading?.removeAttribute('aria-current');
 });
 item.layer.querySelector('[data-folder-root]')?.classList.toggle('selected',path===item.project);
}
function focusProjectEntry(item,path,folder=false){
 item.focused=path;chooseProjectFolder(item,folder?path:path.slice(0,path.lastIndexOf('/')));paintProjectTreeFocus(item);
 if(folder){const node=[...item.layer.querySelectorAll('[data-project-folder]')].find(node=>node.dataset.projectFolder===path);(node?.querySelector(':scope>summary')||(path===item.project?item.layer.querySelector('[data-folder-root]'):null))?.focus({preventScroll:true});}
}
function projectFileSelection(item,path){
 const entry=item.data.entries.find(entry=>entry.path===path),extension=entry?.extension||'';
 if(path===item.project||entry?.directory)return {mode:'folder',source:path};
 if(item.workspace.editor_layout==='latex'){
  if(isProjectTeX(entry))return {mode:'latex',source:path};
  if(extension==='.pdf'){
   const main=item.data.main;
   return path===main?.replace(/\.(tex|txt)$/i,'.pdf')?{mode:'latex',source:main}:{mode:'pdf',pdf:path};
  }
 }
 return {mode:'file',source:path};
}
function paintProjectSelection(item){
 const mode=item.documentMode||'latex',latex=mode==='latex',pdf=mode==='pdf',layer=item.layer;
 layer.dataset.documentMode=mode;
 const controls=layer.querySelector('[data-project-compile-controls]');if(controls)controls.hidden=!latex;
 const toggles=layer.querySelector('.project-layout-toggle');if(toggles)toggles.hidden=!latex;
 layer.querySelectorAll('[data-project-layout]').forEach(button=>{button.hidden=pdf&&button.dataset.projectLayout!=='pdf';button.disabled=pdf;button.setAttribute('aria-pressed',String(pdf||item.layout==='split'||button.dataset.projectLayout===item.layout));});
 const divider=layer.querySelector('.project-source-divider');if(divider)divider.hidden=!latex;
 const log=layer.querySelector('[data-project-log]');if(log)log.hidden=!item.buildStatus||(!latex&&!item.compiling);
}
function projectPDFPlaceholder(item,text){
 const host=item.layer.querySelector('.project-pdf-host');if(!host)return;
 const current=host.querySelector('.project-pdf-current');if(current)current.hidden=true;
 host.querySelectorAll(':scope>.empty').forEach(node=>node.remove());const message=document.createElement('div');message.className='empty';message.textContent=text;host.append(message);
}
function chooseProjectFolder(item,path){
 item.folder=path;
 const label=item.layer.querySelector('[data-folder-location]');if(label){label.textContent=path===item.project?'Project root':path.slice(item.project.length+1);label.parentElement.title='Current folder: '+path;}
}
async function refreshProjectFiles(item){
 const previous=item.data.main,next=await api(libraryURL('project',item.source,item.project));
 next.main=next.entries.some(entry=>entry.path===previous&&isProjectTeX(entry))?previous:null;
 item.data=next;renderProjectTree(item);renderMainTeXSelector(item);
 paintProjectTreeFocus(item);
 for(const draft of item.documents.values())updateProjectDirty(item,draft);
 invalidateProjectList(item.workspace);
}
function bindProjectFiles(item){
 if(!item.workspace.file_operations)return;
 const tree=item.layer.querySelector('.project-file-tree'),form=tree.querySelector('[data-create-form]');
 const input=form.elements.name;
 tree.querySelector('[data-folder-root]').onclick=()=>selectProjectFile(item,item.project);
 const start=kind=>{if(item.fileBusy)return;form.dataset.kind=kind;form.hidden=false;form.querySelector('[data-create-label]').firstChild.textContent=kind==='folder'?'Folder name':'File name';input.value='';input.placeholder=kind==='folder'?'figures':'section.tex';input.focus();};
 tree.querySelector('[data-new-file]').onclick=()=>start('file');tree.querySelector('[data-new-folder]').onclick=()=>start('folder');
 tree.querySelector('[data-create-cancel]').onclick=()=>{if(!item.fileBusy)form.hidden=true;};
 input.onkeydown=event=>{if(event.key==='Escape'&&!item.fileBusy){event.preventDefault();form.hidden=true;}};
 form.onsubmit=async event=>{
  event.preventDefault();if(item.fileBusy)return;
  item.fileBusy=true;form.querySelector('[type=submit]').disabled=true;projectNotice(item,'');
  try{
   const result=await api('/api/workspaces/project/create',{source:item.source,project:item.project,parent:item.folder,name:input.value,kind:form.dataset.kind});
   form.hidden=true;await refreshProjectFiles(item);
   await selectProjectFile(item,result.path);
  }catch(error){projectNotice(item,error.message);}
  finally{item.fileBusy=false;form.querySelector('[type=submit]').disabled=false;}
 };
 const destination=event=>event.target.closest('[data-project-folder]')?.dataset.projectFolder||item.folder||item.project;
 const clear=()=>{tree.classList.remove('project-drop-active');tree.querySelectorAll('.project-drop-target').forEach(el=>el.classList.remove('project-drop-target'));};
 tree.ondragover=event=>{
  if(![...event.dataTransfer.types].includes('Files'))return;
  event.preventDefault();event.stopPropagation();event.dataTransfer.dropEffect='copy';clear();tree.classList.add('project-drop-active');event.target.closest('[data-project-folder]>summary')?.classList.add('project-drop-target');
 };
 tree.ondragleave=event=>{if(!tree.contains(event.relatedTarget))clear();};
 tree.ondrop=async event=>{
  event.preventDefault();event.stopPropagation();clear();if(item.fileBusy)return;
  const files=[...event.dataTransfer.files],parent=destination(event);
  if([...event.dataTransfer.items].some(entry=>entry.webkitGetAsEntry?.()?.isDirectory)){projectNotice(item,'Drop files into a folder. Create folders with New folder.');return;}
  if(!files.length)return;
  if(files.length>100||files.some(file=>file.size>25*1024*1024)||files.reduce((sum,file)=>sum+file.size,0)>100*1024*1024){projectNotice(item,'Copy up to 100 files at a time, 25 MB per file and 100 MB in total.');return;}
  item.fileBusy=true;projectNotice(item,'');const errors=[];let copied=0;
  try{
   for(const file of files){try{const [data]=await filesToData([file]);await api('/api/workspaces/project/import',{source:item.source,project:item.project,parent,name:file.name,data:data.data});copied++;}catch(error){errors.push(file.name+': '+error.message);}}
   if(copied)await refreshProjectFiles(item);
   chooseProjectFolder(item,parent);projectNotice(item,errors.join('\n'));
  }catch(error){projectNotice(item,error.message);}finally{item.fileBusy=false;}
 };
}
function renderProjectTree(item){
 item.renameCancel?.();
 const opened=new Set(item.treeInitialized?[...item.layer.querySelectorAll('[data-project-folder][open]')].map(el=>el.dataset.projectFolder):item.savedEditor?.openFolders||[]);
 const root={folders:new Map(),files:[]};
 for(const entry of item.data.entries){const parts=entry.path.slice(item.project.length+1).split('/');let node=root;for(const part of parts.slice(0,-1)){if(!node.folders.has(part))node.folders.set(part,{folders:new Map(),files:[]});node=node.folders.get(part);}if(entry.directory){const name=parts.at(-1);if(!node.folders.has(name))node.folders.set(name,{folders:new Map(),files:[]});}else node.files.push(entry);}
 const menu=(path,name,folder=false)=>item.workspace.file_operations?`<button type="button" class="project-file-more" data-file-menu="${esc(path)}" ${folder?'data-folder-menu':''} title="Options for ${esc(name)}" aria-label="Options for ${esc(name)}" aria-haspopup="menu" aria-expanded="false">${icon('more')}</button>`:'';
 const render=(node,parent=item.project)=>[...node.folders].map(([name,folder])=>`<div class="project-folder-item"><details class="project-tree-folder" data-project-folder="${esc(parent+'/'+name)}"><summary><span class="project-folder-caption">${icon('folder')}<span>${esc(name)}</span></span></summary>${render(folder,parent+'/'+name)}</details>${menu(parent+'/'+name,name,true)}</div>`).join('')+node.files.map(entry=>`<div class="project-file-row"><button type="button" data-project-file="${esc(entry.path)}" class="${entry.path===(item.focused??item.selected)?'selected':''}" title="${esc(entry.path.slice(item.project.length+1))}">${icon(entry.extension==='.pdf'?'file-pdf':isProjectTeX(entry)?'file-code':'document')}<span>${esc(entry.name)}</span>${entry.path===item.data.main?'<small class="project-main-badge">Main</small>':''}<span class="project-dirty-marker" ${item.documents.get(entry.path)?.changed?'':'hidden'} aria-label="Unsaved changes">${icon('circle-small')}</span></button>${menu(entry.path,entry.name)}</div>`).join('');
 item.layer.querySelector('.project-tree-entries').innerHTML=render(root);
 item.layer.querySelectorAll('[data-project-file]').forEach(b=>b.onclick=()=>{chooseProjectFolder(item,b.dataset.projectFile.slice(0,b.dataset.projectFile.lastIndexOf('/')));selectProjectFile(item,b.dataset.projectFile);});
 item.layer.querySelectorAll('[data-file-menu]').forEach(button=>button.onclick=async()=>{
  const path=button.dataset.fileMenu,folder=button.hasAttribute('data-folder-menu');
  if((item.focused??item.selected)!==path){try{await selectProjectFile(item,path);}catch(error){projectNotice(item,error.message);return;}}
  if(!button.isConnected||(item.focused??item.selected)!==path)return;
  ActionMenu.actions(button,{label:folder?'Folder actions':'File actions',items:[
   {label:'Rename',icon:'pen',run:()=>beginProjectFileRename(item,path,folder?button.parentElement.querySelector(':scope>.project-tree-folder>summary'):button.closest('.project-file-row'))},
   {label:'Show in Finder',icon:'folder-open',run:()=>projectFileAction(item,path,'reveal')},
   {separator:true},{label:'Delete',icon:'trash',danger:true,run:()=>{if(confirm('Move “'+path.split('/').at(-1)+'”'+(folder?' and all its contents':'')+' to Trash? You can restore it in Finder.'))projectFileAction(item,path,'delete');}}
  ]});
 });
 item.layer.querySelectorAll('[data-project-folder]>summary').forEach(summary=>summary.onclick=event=>{if(summary.querySelector('form')){event.preventDefault();return;}selectProjectFile(item,summary.parentElement.dataset.projectFolder);});
 item.layer.querySelectorAll('[data-project-folder]').forEach(el=>{el.open=opened.has(el.dataset.projectFolder);el.addEventListener('toggle',()=>rememberProjectEditor(item));});item.treeInitialized=true;
 chooseProjectFolder(item,item.folder||item.project);paintProjectTreeFocus(item);
}
function projectPathWithin(value,path){return typeof value==='string'&&(value===path||value.startsWith(path+'/'));}
function projectFileCanChange(item,path){
 if(item.fileBusy){projectNotice(item,'Wait for the current file operation to finish.');return false;}
 if(item.compiling){projectNotice(item,'Wait for compilation to finish before changing files.');return false;}
 if([...item.documents].some(([key,draft])=>projectPathWithin(key,path)&&(draft.changed||draft.handoff))){projectNotice(item,'Save or discard unsaved changes in this file or folder before renaming or deleting it.');return false;}
 return true;
}
function beginProjectFileRename(item,path,row){
 if(!projectFileCanChange(item,path))return;
 item.renameCancel?.();
 const form=document.createElement('form');form.className='project-file-rename';
 const folder=item.data.entries.find(entry=>entry.path===path)?.directory;
 form.innerHTML=`<input aria-label="${folder?'New folder name':'New file name'}" maxlength="255" required><button type="submit" aria-label="Save file name" title="Save file name">${icon('check')}</button><button type="button" aria-label="Cancel rename" title="Cancel rename">${icon('close')}</button>`;
 const nodes=[...row.childNodes];row.replaceChildren(form);const input=form.querySelector('input');input.value=path.split('/').at(-1);
 const cancel=()=>{row.replaceChildren(...nodes);item.renameCancel=null;};item.renameCancel=cancel;
 form.querySelector('[type=button]').onclick=()=>{if(!item.fileBusy)cancel();};
 input.onkeydown=event=>{if(event.key==='Escape'&&!item.fileBusy){event.preventDefault();cancel();row.querySelector('[data-file-menu]')?.focus();}};
 form.onsubmit=async event=>{event.preventDefault();if(item.fileBusy)return;form.querySelectorAll('input,button').forEach(node=>node.disabled=true);const ok=await projectFileAction(item,path,'rename',input.value);if(ok)cancel();else{form.querySelectorAll('input,button').forEach(node=>node.disabled=false);input.focus();}};
 form.onclick=event=>event.stopPropagation();
 input.focus();input.setSelectionRange(0,!folder&&input.value.lastIndexOf('.')>0?input.value.lastIndexOf('.'):input.value.length);
}
async function projectFileAction(item,path,action,name){
 if(action!=='reveal'&&!projectFileCanChange(item,path))return false;
 if(item.fileBusy)return false;
 item.fileBusy=true;projectNotice(item,'');
 const targets=action==='reveal'?[]:[...item.documents].filter(([key])=>projectPathWithin(key,path)).map(([,draft])=>({host:draft.host,inert:draft.host?.inert}));
 item.fileMutationPath=action==='reveal'?null:path;
 for(const {host} of targets)if(host)host.inert=true;
 try{
  let entry=item.data.entries.find(entry=>entry.path===path);
  if(!entry?.file_revision){await refreshProjectFiles(item);entry=item.data.entries.find(entry=>entry.path===path);}
  const result=await api('/api/workspaces/project/'+action,{source:item.source,project:item.project,path,revision:entry?.file_revision,...(name===undefined?{}:{name})});
  if(action==='reveal')return true;
  const selected=projectPathWithin(item.selected,path),main=projectPathWithin(item.data.main,path),preview=projectPathWithin(item.pdfPath,path);
  const remap=value=>action==='rename'?result.path+value.slice(path.length):null;
  const nextSelected=selected?remap(item.selected):null;
  const nextFocus=projectPathWithin(item.focused,path)?(action==='rename'?remap(item.focused):path.slice(0,path.lastIndexOf('/'))):item.focused;
  for(const [key,draft] of [...item.documents])if(projectPathWithin(key,path)){draft.editor?.destroy();draft.reader?.destroy();draft.host.remove();item.documents.delete(key);}
  if(selected){item.layer.querySelector('.project-file-toolbar [data-reference]')?.remove();item.request++;item.selected=null;item.layer.querySelector('[data-file-name]').textContent='Select a file';item.layer.querySelector('[data-file-discard]').hidden=true;item.layer.querySelector('.project-file-toolbar').hidden=false;}
  if(main)item.data.main=remap(item.data.main);
  if(preview){item.pdfRequest++;item.pdf?.destroy();item.pdf=null;item.pdfPath=null;const host=item.layer.querySelector('.project-pdf-host');if(host)host.innerHTML='<div class="empty">Select a PDF or compile to preview this document.</div>';}
  if(projectPathWithin(item.folder,path))item.folder=action==='rename'?remap(item.folder):path.slice(0,path.lastIndexOf('/'));
  if(action==='rename')item.layer.querySelectorAll('[data-project-folder]').forEach(node=>{if(projectPathWithin(node.dataset.projectFolder,path))node.dataset.projectFolder=remap(node.dataset.projectFolder);});
  const state=W.states[item.workspace.id];if(selected&&state?.project===item.project)state.document=nextSelected;
  await refreshProjectFiles(item);
  if(main){try{const key='notes-main-tex:'+JSON.stringify([item.source,item.project]);localStorage.setItem(key,item.data.main||'');}catch{}}
  item.fileMutationPath=null;
  if(nextSelected||item.selected)await selectProjectFile(item,nextSelected||item.selected);
  else if(item.documentMode){item.documentMode='file';item.activeSource=null;paintProjectSelection(item);}
  if(nextFocus)focusProjectEntry(item,nextFocus,nextFocus===item.project||item.data.entries.some(entry=>entry.path===nextFocus&&entry.directory));
  item.sourceSavedSincePreview=true;item.sourceRevisionSerial=(item.sourceRevisionSerial||0)+1;updateProjectBuildState(item);
  return true;
 }catch(error){projectNotice(item,error.message);return false;}
 finally{for(const {host,inert} of targets)if(host)host.inert=inert||false;item.fileMutationPath=null;item.fileBusy=false;}
}

export {
  paintProjectTreeFocus, focusProjectEntry, projectFileSelection, paintProjectSelection,
  projectPDFPlaceholder, chooseProjectFolder, refreshProjectFiles,
  bindProjectFiles, renderProjectTree, projectPathWithin, projectFileCanChange,
  beginProjectFileRename, projectFileAction,
};
