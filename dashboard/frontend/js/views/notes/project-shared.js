// Shared Notes project state, URL helpers, and host runtime bridges.
import { esc, toast, modal } from '../../workbench-chrome.js';
import { iconHtml } from '../../icons.js';
import { DataTables } from '../../table.js';
import { SearchFields } from '../../search-fields.js';
import { ActionMenu } from '../../action-menu.js';
import { SplitPanes } from '../../splitpanes.js';
import { DraftRecovery } from '../../draft-recovery.js';
import {
  $, params, api, S, W, workspaceURL, workspaceResourceURL, workspaceDate, positionDashboard,
} from './notes-context.js';
import { workspaceContent } from './workspace-toolbar.js';
import { session } from './notes-session.js';

const icon = name => iconHtml(name);
const renderWorkspace = (...a) => session.renderWorkspace(...a);
const syncDashboardVisibility = (...a) => session.syncDashboardVisibility(...a);
const NotesBrowsing = {
  clean: (...a) => session.NotesBrowsing.clean(...a),
  checkpoint: (...a) => session.NotesBrowsing.checkpoint(...a),
  currentLocation: (...a) => session.NotesBrowsing.currentLocation(...a),
};

function filesToData(files) {
  return Promise.all([...files].map(file => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || '');
      const comma = text.indexOf(',');
      resolve({ name: file.name, data: comma >= 0 ? text.slice(comma + 1) : text });
    };
    reader.onerror = () => reject(reader.error || new Error('Failed to read ' + file.name));
    reader.readAsDataURL(file);
  })));
}

const isProjectTeX = entry => Boolean(entry?.path && /(?:\.tex|\/main\.txt)$/i.test(entry.path));
const ProjectUI={layers:new Map(),lists:new Map(),request:0};
const libraryStatusNames={active:'Active',inactive:'Inactive',finished:'Finished',planning:'Planning',archived:'Archived',unknown:'Unclassified'};
const libraryStatusTone={active:'info',inactive:'muted',finished:'done',planning:'warn',archived:'muted',unknown:'muted'};
function libraryColumnDirection(key,columns=[]){const direction=columns.find(column=>column.id===key)?.direction;return direction==='asc'?1:direction==='desc'?-1:['modified_at','period_start'].includes(key)?-1:1;}
function projectPreferences(workspace){
 let saved={};try{saved=JSON.parse(localStorage.getItem('notes-library:'+workspace.id)||'{}');}catch{}
 const sort=['name','type','modified_at','period_start','status'].includes(saved.sort)?saved.sort:workspace.date_field||'modified_at';
 const columns=typeof SectionSettings!=='undefined'?SectionSettings.columns(workspace.id):[];
 return {sort,direction:[1,-1].includes(saved.direction)?saved.direction:libraryColumnDirection(sort,columns),widths:saved.widths&&typeof saved.widths==='object'?saved.widths:null};
}
function saveProjectPreferences(workspace,prefs){try{localStorage.setItem('notes-library:'+workspace.id,JSON.stringify(prefs));}catch{}}
function libraryBadge(status){return `<span class="badge tone-${libraryStatusTone[status]||'neutral'}">${esc(libraryStatusNames[status]||status)}</span>`;}
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

export {
  icon, renderWorkspace, syncDashboardVisibility, NotesBrowsing,
  esc, toast, modal, api, $, params, S, W, workspaceURL, workspaceResourceURL, workspaceDate,
  positionDashboard, workspaceContent, DataTables, SearchFields, ActionMenu, SplitPanes, DraftRecovery,
  filesToData, isProjectTeX, ProjectUI, libraryStatusNames, libraryStatusTone, libraryColumnDirection,
  projectPreferences, saveProjectPreferences, libraryBadge, libraryURL, libraryError,
  invalidateProjectList, readProjectList, projectListCurrent,
};
