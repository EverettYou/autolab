// Notes workspace host: project list + LaTeX/PDF workbench, mounted in the main dashboard.
import { runtime as R } from './runtime.js';
import { esc, toast, modal } from '../../workbench-chrome.js';
import { iconHtml } from '../../icons.js';

const $ = id => document.getElementById(id);
const params = values => new URLSearchParams(values);
const workspace = {
  id: 'papers',
  title: 'Notes',
  editor_layout: 'latex',
  file_operations: true,
  sources: [{id: 'lab-notes'}],
};
const S = {view: workspace.id, query: ''};
const W = {config: {workspaces: [workspace]}, states: {}};
const state = {source: workspace.sources[0].id, project: '', document: null, pdfReaders: []};
W.states[workspace.id] = state;
const liveError = error => toast(error.message);
const icon = name => iconHtml(name);

async function api(url, body, {timeoutMs = 20000} = {}) {
  const options = {signal: AbortSignal.timeout(timeoutMs), headers: {Accept: 'application/json'}};
  if (body !== undefined) {
    options.method = 'POST';
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.error || 'Request failed'), {status: response.status});
  return data;
}

function workspaceURL(route, source, path) {
  return '/api/workspaces/' + route + '?' + params({source, path});
}
function workspaceResourceURL(source, path, href) {
  const root = new URL('/' + path.split('/').map(encodeURIComponent).join('/'), location.origin);
  const resource = new URL(href, root);
  if (resource.origin !== location.origin) return null;
  return workspaceURL('file', source, decodeURIComponent(resource.pathname.slice(1)));
}
function workspaceDate(value) {
  return new Date(value).toLocaleDateString('en-US', {year: 'numeric', month: '2-digit', day: '2-digit'});
}
function positionDashboard(layer) {
  const host = $('workspace-content');
  if (!host) return;
  const {width, height, top, left} = host.getBoundingClientRect();
  Object.assign(layer.style, {width: width + 'px', height: height + 'px', top: top + 'px', left: left + 'px'});
}
function syncDashboardVisibility() { R.syncProjectLayers?.(); }

const projectStorage = 'lab.notes.positions';
function savedPositions() {
  try { return JSON.parse(localStorage.getItem(projectStorage) || '{}'); } catch { return {}; }
}
const NotesBrowsing = {
  clean(_id, current) {
    return {...current, pdfReaders: (current.pdfReaders || []).slice(-25)};
  },
  currentLocation() { return {view: workspace.id, location: state}; },
  checkpoint() {
    const saved = savedPositions();
    const layers = R.ProjectUI?.layers;
    if (!layers) return;
    for (const item of layers.values()) {
      if (item.project !== state.project || !item.editorReady) continue;
      saved[item.project] = {
        editor: R.projectEditorLocation(item),
        document: item.selected,
        pdfReaders: state.pdfReaders,
      };
    }
    try { localStorage.setItem(projectStorage, JSON.stringify(saved)); } catch {}
  },
};
window.NotesBrowsing = NotesBrowsing;

let onLocation = null;

async function renderWorkspace() {
  const saved = savedPositions()[state.project];
  if (saved && state.project !== state.editor?.project) {
    state.editor = saved.editor;
    state.document ||= saved.document;
    state.pdfReaders = saved.pdfReaders || [];
  }
  await R.renderProjectWorkspace(workspace, state);
  onLocation?.(state.project || '');
}

function selectProject(project) {
  NotesBrowsing.checkpoint();
  state.project = project;
  state.path = project;
  state.document = null;
  S.query = '';
  const search = $('workspace-search');
  if (search) search.value = '';
  void renderWorkspace().catch(liveError);
}

function wireNotesHost(options = {}) {
  onLocation = typeof options.onLocation === 'function' ? options.onLocation : null;
  const search = $('workspace-search');
  if (search && !search.dataset.notesWired) {
    search.dataset.notesWired = '1';
    search.addEventListener('input', event => {
      S.query = event.target.value;
      void renderWorkspace().catch(liveError);
    });
  }
  if (!window.__notesPagehideWired) {
    window.__notesPagehideWired = true;
    window.addEventListener('pagehide', () => NotesBrowsing.checkpoint());
  }
}

window.NotesHost = {
  open(project = '') { selectProject(project || ''); },
  wire: wireNotesHost,
  checkpoint: () => NotesBrowsing.checkpoint(),
};

Object.assign(R, {
  $, esc, params, api, toast, modal, icon, S, W, workspace, state,
  workspaceURL, workspaceResourceURL, workspaceDate, liveError,
  renderWorkspace, selectProject, NotesBrowsing, positionDashboard,
  syncDashboardVisibility,
});
