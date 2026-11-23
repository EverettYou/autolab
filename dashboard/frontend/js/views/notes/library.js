// Notes project library list.
import {
  icon, renderWorkspace, syncDashboardVisibility, esc, toast, modal, api, $, S, W, workspaceDate,
  workspaceContent, DataTables, SearchFields, ProjectUI, libraryColumnDirection, projectPreferences,
  saveProjectPreferences, libraryBadge, libraryURL, libraryError, invalidateProjectList, readProjectList,
  projectListCurrent,
} from './project-shared.js';
import { openProjectEditor, syncProjectLayers } from './project-editor.js';

async function renderProjectWorkspace(workspace,state){
 if(!state.source)state.source=workspace.sources[0]?.id;
 if(state.project===undefined)state.project=(state.document||state.path||'').split('/')[0];
 if(state.project){
  const searchLabel=$('workspace-search')?.closest('label');
  if(searchLabel)searchLabel.hidden=true;
  workspaceContent().innerHTML='<section class="dashboard-placeholder" aria-label="Project editor"></section>';
  syncDashboardVisibility();await openProjectEditor(workspace,state);return;
 }
 syncProjectLayers();
 const searchLabel=$('workspace-search')?.closest('label');
 if(searchLabel)searchLabel.hidden=false;
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

  // Catalog-style chrome: title + platform search-field slot above the table.
  workspaceContent().innerHTML=`<section class="project-library"><header class="library-toolbar"><h1>${esc(workspace.title)}</h1><div class="toolbar-search workspace-search-slot" data-workspace-search></div></header><div class="library-table-scroll" aria-label="${esc(workspace.title)}">${data?.errors?.length?`<details class="library-errors"><summary>Some project dates are incomplete</summary>${data.errors.map(e=>`<p>${esc(e)}</p>`).join('')}</details>`:''}${!data?'<div class="empty" role="status">Reading project dates…</div>':`<table class="library-table">${DataTables.header(visible)}<tbody>${entries.map((entry,i)=>`<tr data-library-row="${i}">${visible.map(c=>c.id==='name'?`<td data-library-cell="name"><button type="button" data-library-open="${i}" title="${esc(entry.name)}">${icon('folder')}<span>${esc(entry.name)}</span></button></td>`:c.id==='type'?`<td data-library-cell="type"><button type="button" class="paper-type-button" data-paper-type="${i}" aria-label="Change type for ${esc(entry.name)}"><span class="type-chip task-status paper-type-badge type-badge category-${esc(entry.paper_type||'other')}" data-type-owner="paper" data-type-id="${esc(entry.paper_type||'other')}">${esc(typeName(entry.paper_type))}</span></button></td>`:c.id==='status'?`<td data-library-cell="status">${libraryBadge(entry.status)}</td>`:`<td data-library-cell="${esc(c.id)}">${entry[dateKey]?`<time datetime="${esc(entry[dateKey])}">${dateKey==='period_start'?esc(entry.period_label):workspaceDate(entry.modified_at)}</time>`:'—'}</td>`).join('')}</tr>`).join('')}</tbody></table>${entries.length?'':'<div class="empty">No matching projects.</div>'}`}</div></section>`;
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

export { renderProjectWorkspace };
