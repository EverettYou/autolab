'use strict';
// One project-list/reader contract for configured folder libraries.
const isProjectTeX = entry => Boolean(entry?.path && /(?:\.tex|\/main\.txt)$/i.test(entry.path));
const ProjectUI={layers:new Map(),lists:new Map(),request:0};
const libraryStatusNames={active:'Active',inactive:'Inactive',finished:'Finished',planning:'Planning',archived:'Archived',unknown:'Unclassified'};
function libraryColumnDirection(key,columns=[]){const direction=columns.find(column=>column.id===key)?.direction;return direction==='asc'?1:direction==='desc'?-1:['modified_at','period_start'].includes(key)?-1:1;}
function projectPreferences(workspace){
 let saved={};try{saved=JSON.parse(localStorage.getItem('notes-library:'+workspace.id)||'{}');}catch{}
 const sort=['name','type','modified_at','period_start','status'].includes(saved.sort)?saved.sort:workspace.date_field||'modified_at';
 const columns=typeof SectionSettings!=='undefined'?SectionSettings.columns(workspace.id):[];
 return {sort,direction:[1,-1].includes(saved.direction)?saved.direction:libraryColumnDirection(sort,columns),widths:saved.widths&&typeof saved.widths==='object'?saved.widths:null};
}
function saveProjectPreferences(workspace,prefs){try{localStorage.setItem('notes-library:'+workspace.id,JSON.stringify(prefs));}catch{}}
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
function libraryBadge(status){return `<span class="task-status library-status status-${esc(status)}">${esc(libraryStatusNames[status]||status)}</span>`;}
function libraryURL(route,source,project,extra={}){return '/api/workspaces/'+route+'?'+params({source,project,...extra});}
function libraryError(host,error){host.innerHTML=`<div class="empty" role="alert">${esc(error.message)}</div>`;}
function invalidateProjectList(workspace){const list=ProjectUI.lists.get(workspace.id);if(list){list.generation=(list.generation||0)+1;list.data=null;list.pending=null;list.loadedAt=0;list.error=null;}}
function readProjectList(list,source){
 if(list.data&&Date.now()-(list.loadedAt||0)<30000)return Promise.resolve(list.data);
 if(list.pending)return list.pending;
 const generation=list.generation||0;
 const pending=api(libraryURL('projects',source,'')).then(data=>{
  if((list.generation||0)!==generation)return null;
  // Keep completed metadata even when the user navigates away during a scan.
  list.data=data;list.loadedAt=Date.now();list.error=null;return data;
 });
 list.pending=pending;const clear=()=>{if(list.pending===pending)list.pending=null;};pending.then(clear,clear);return pending;
}
function projectListCurrent(workspace,state,view){return S.view===view&&!state.project&&(!workspace.calendar_view||state.archive===true);}
async function renderProjectWorkspace(workspace,state){
 if(!state.source)state.source=workspace.sources[0]?.id;
 if(state.project===undefined)state.project=(state.document||state.path||'').split('/')[0];
 if(state.project){
  $('workspace-search').closest('label').hidden=true;
  workspaceContent().innerHTML='<section class="dashboard-placeholder" aria-label="Project editor"></section>';
  syncDashboardVisibility();await openProjectEditor(workspace,state);return;
 }
 syncProjectLayers();$('workspace-search').closest('label').hidden=true;
 const request=++ProjectUI.request,view=S.view;
 let list=ProjectUI.lists.get(workspace.id);
 if(!list){list={prefs:projectPreferences(workspace),filter:['all','active','inactive','finished','planning','archived'].includes(state.libraryFilter)?state.libraryFilter:'all',data:null};ProjectUI.lists.set(workspace.id,list);}
 if(list.source!==state.source){invalidateProjectList(workspace);list.source=state.source;}
 const draw=()=>{
  if(!projectListCurrent(workspace,state,view))return;
  const canonical=DataTables.settings?.('projects.'+workspace.id,{sort:{key:list.prefs.sort,direction:list.prefs.direction}})?.sort;if(canonical&&['name','type','modified_at','period_start','status'].includes(canonical.key)){list.prefs.sort=canonical.key;list.prefs.direction=canonical.direction;}
  const data=list.data,prefs=list.prefs,q=S.query.toLocaleLowerCase(),dateKey=workspace.date_field||'modified_at';
  const catalog=data?.paper_types?.types||[],typeName=id=>catalog.find(t=>t.id===id)?.name||'Other';
  if(data?.paper_types)window.TypeBadges?.setCatalog('paper',catalog);
  const columns=typeof SectionSettings!=='undefined'?SectionSettings.columns(workspace.id):[];
  list.columnDirections=Object.fromEntries(columns.map(column=>[column.id,libraryColumnDirection(column.id,columns)]));
  const visible=columns.length?columns.filter(c=>c.visible):[{id:'name',name:'Name'},{id:'status',name:'Status'},{id:dateKey,name:workspace.date_label||'Modified'}];
  if(!visible.some(column=>column.id===prefs.sort)){prefs.sort=visible[0].id;prefs.direction=libraryColumnDirection(prefs.sort,columns);}
  const entries=(data?.entries||[]).filter(e=>(!q||SearchFields.matches({...e,type:typeName(e.paper_type)},q)));
  if(prefs.sort==='type')entries.forEach(e=>e.type=typeName(e.paper_type));
  entries.sort((a,b)=>{if(['modified_at','period_start'].includes(prefs.sort)&&(!a[prefs.sort]||!b[prefs.sort]))return Number(!a[prefs.sort])-Number(!b[prefs.sort]);return prefs.direction*String(a[prefs.sort]||'').localeCompare(String(b[prefs.sort]||''),'en',{numeric:true})||a.name.localeCompare(b.name);});
  const statuses=workspace.status_options||['active','inactive','finished'];

  // Landing is only the project table — lab chrome already provides Notes/search.
  workspaceContent().innerHTML=`<section class="project-library"><div class="library-table-scroll" aria-label="${esc(workspace.title)}">${data?.errors?.length?`<details class="library-errors"><summary>Some project dates are incomplete</summary>${data.errors.map(e=>`<p>${esc(e)}</p>`).join('')}</details>`:''}${!data?'<div class="empty" role="status">Reading project dates…</div>':`<table class="library-table">${DataTables.header(visible)}<tbody>${entries.map((entry,i)=>`<tr data-library-row="${i}">${visible.map(c=>c.id==='name'?`<td data-library-cell="name"><button type="button" data-library-open="${i}" title="${esc(entry.name)}">${icon('folder')}<span>${esc(entry.name)}</span></button></td>`:c.id==='type'?`<td data-library-cell="type"><button type="button" class="paper-type-button" data-paper-type="${i}" aria-label="Change type for ${esc(entry.name)}"><span class="type-chip task-status paper-type-badge type-badge category-${esc(entry.paper_type||'other')}" data-type-owner="paper" data-type-id="${esc(entry.paper_type||'other')}">${esc(typeName(entry.paper_type))}</span></button></td>`:c.id==='status'?`<td data-library-cell="status">${libraryBadge(entry.status)}</td>`:`<td data-library-cell="${esc(c.id)}">${entry[dateKey]?`<time datetime="${esc(entry[dateKey])}">${dateKey==='period_start'?esc(entry.period_label):workspaceDate(entry.modified_at)}</time>`:'—'}</td>`).join('')}</tr>`).join('')}</tbody></table>${entries.length?'':'<div class="empty">No matching projects.</div>'}`}</div></section>`;
  const root=document.querySelector('.project-library');
  root.querySelectorAll('[data-paper-type]').forEach(b=>b.onclick=e=>{e.stopPropagation();editPaperType(state.source,entries[Number(b.dataset.paperType)],()=>{invalidateProjectList(workspace);renderWorkspace();});});
  root.querySelectorAll('[data-library-row]').forEach(row=>row.onclick=()=>{state.project=entries[Number(row.dataset.libraryRow)].path;state.path=state.project;state.document=null;S.query='';$('workspace-search').value='';renderWorkspace();});
  if(data)bindLibraryColumns(root,workspace,prefs,draw);
 };
 draw();
 try{const data=await readProjectList(list,state.source);if(!data||request!==ProjectUI.request||!projectListCurrent(workspace,state,view))return;draw();}
 catch(error){if(request===ProjectUI.request&&projectListCurrent(workspace,state,view)){if(list.data){toast(error.message);return;}libraryError(document.querySelector('.library-table-scroll'),error);}}
}
function bindLibraryColumns(root,workspace,prefs,redraw){
 const table=root.querySelector('table'),scroll=root.querySelector('.library-table-scroll');
 const legacy=Array.isArray(prefs.widths)?Object.fromEntries(['name','status',workspace.date_field||'modified_at'].map((k,i)=>[k,prefs.widths[i]])):prefs.widths||{};
 const columns=typeof SectionSettings!=='undefined'?SectionSettings.columns(workspace.id):[];

 DataTables.mount(table,{
  navigation:{key:row=>row.querySelector('[data-library-open]')?.title,focus:row=>row.querySelector('[data-library-open]')},
  layout:{id:'projects.'+workspace.id,values:()=>Array.isArray(prefs.widths)?legacy:prefs.widths||legacy,defaults:{name:Math.max(240,scroll.clientWidth-480),type:140,status:140,modified_at:200,period_start:200},min:90,persist:widths=>{prefs.widths=widths;saveProjectPreferences(workspace,prefs);}},
  state:key=>({active:prefs.sort===key,direction:prefs.sort===key?prefs.direction:libraryColumnDirection(key,columns)}),
  sort:key=>{const next=DataTables.nextSort({key:prefs.sort,direction:prefs.direction},key,libraryColumnDirection(key,columns));prefs.sort=next.key;prefs.direction=next.direction;saveProjectPreferences(workspace,prefs);redraw();document.querySelector(`[data-table-sort="${key}"]`)?.focus({preventScroll:true});},
 });
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

async function editPaperType(source,entry,done){
 try{
  const catalog=await api('/api/papers/types');
  window.TypeBadges?.setCatalog('paper',catalog.types);
  modal('Paper type',`<p class="info-copy">${esc(entry.name)}</p><div class="label-options">${catalog.types.filter(t=>t.enabled||t.id===entry.paper_type).map(t=>`<label><input type="radio" name="type" value="${esc(t.id)}" ${entry.paper_type===t.id?'checked':''}><span class="type-chip type-badge category-${esc(t.id)}" data-type-owner="paper" data-type-id="${esc(t.id)}">${esc(t.name)}</span></label>`).join('')}</div>`,'<button type="submit" class="primary-button">Save type</button>',async form=>{await api('/api/papers/type',{source,project:entry.path,type:form.get('type'),revision:entry.paper_type_revision});$('workspace-modal').close();done();});
 }catch(error){toast(error.message);}
}
document.addEventListener('section-settings-changed',e=>{
 const view=e.detail.view,list=ProjectUI.lists.get(view),workspace=W.config.workspaces.find(item=>item.id===view);
 if(list&&workspace&&typeof SectionSettings!=='undefined'){
  const columns=SectionSettings.columns(view),key=list.prefs.sort,direction=libraryColumnDirection(key,columns);
  if(list.columnDirections?.[key]!==undefined&&list.columnDirections[key]!==direction){list.prefs.direction=direction;saveProjectPreferences(workspace,list.prefs);}
  list.columnDirections=Object.fromEntries(columns.map(column=>[column.id,libraryColumnDirection(column.id,columns)]));
 }
 if(view===S.view&&['papers','travel'].includes(S.view))renderWorkspace();
});
document.addEventListener('paper-types-changed',()=>{const workspace=W.config.workspaces.find(w=>w.id==='papers');if(workspace)invalidateProjectList(workspace);if(S.view==='papers')renderWorkspace();});
