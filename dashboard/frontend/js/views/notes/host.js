// Notes workspace host: project list + LaTeX/PDF workbench, mounted in the main dashboard.
import { runtime as R } from './runtime.js';

const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
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

const FA = {
  previous: 'chevron-left', next: 'chevron-right',
  up: 'chevron-up', down: 'chevron-down',
  folder: 'folder', 'folder-open': 'folder-open',
  'folder-tree': 'folder-tree', 'folder-plus': 'folder-plus',
  document: 'file', 'file-code': 'file-code',
  'file-tex': 'file-lines', 'file-pdf': 'file-pdf',
  'file-plus': 'file-circle-plus', source: 'file-lines',
  pdf: 'file-pdf', play: 'play',
  'hourglass-half': 'hourglass-half', save: 'floppy-disk',
  'arrows-rotate': 'arrows-rotate', refresh: 'arrows-rotate',
  'lock-keyhole': 'lock', 'circle-small': 'circle',
  plus: 'plus', minus: 'minus',
  close: 'xmark', check: 'check',
  download: 'download', search: 'magnifying-glass',
  more: 'ellipsis', sortUp: 'sort-up', sortDown: 'sort-down',
  'cloud-check': 'cloud', code: 'code',
  preview: 'eye', markdown: 'file-lines',
  json: 'code', text: 'align-left',
  pen: 'pen', trash: 'trash',
};
function icon(name) {
  const glyph = Object.hasOwn(FA, name) ? FA[name] : 'file';
  return (window.faHtml || (() => ''))(glyph, 'app-icon');
}
window.WorkbenchIcons = {html: icon};

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

let toastTimer;
function toast(message) {
  const output = $('workspace-toast');
  if (!output) return;
  output.textContent = message;
  output.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { output.hidden = true; }, 4500);
}
function modal(title, body, actions, submit) {
  const dialog = $('workspace-modal');
  dialog.innerHTML = '<form><h2>' + esc(title) + '</h2>' + body +
    '<footer><button type="button" class="text-button" data-cancel>Cancel</button>' + actions + '</footer><p role="alert"></p></form>';
  dialog.querySelector('[data-cancel]').onclick = () => dialog.close();
  dialog.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    try { await submit(new FormData(event.target)); }
    catch (error) { dialog.querySelector('[role=alert]').textContent = error.message; }
  };
  dialog.showModal();
}

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
