// Notes workspace host: project list + LaTeX/PDF workbench, mounted in the main dashboard.
import { runtime as R } from './runtime.js';
import { esc, toast, modal } from '../../workbench-chrome.js';
import { iconHtml } from '../../icons.js';
import {
  $, api, S, W, workspace, state, liveError,
  workspaceURL, workspaceResourceURL, workspaceDate, positionDashboard, params,
} from './notes-context.js';
import {
  ProjectUI, renderProjectWorkspace, projectEditorLocation, syncProjectLayers,
} from './projects.js';

const icon = name => iconHtml(name);

function syncDashboardVisibility() { syncProjectLayers(); }

const projectStorage = 'lab.notes.positions';
function savedPositions() {
  try { return JSON.parse(localStorage.getItem(projectStorage) || '{}'); } catch { return {}; }
}
const NotesBrowsing = {
  clean(_id, current) {
    return { ...current, pdfReaders: (current.pdfReaders || []).slice(-25) };
  },
  currentLocation() { return { view: workspace.id, location: state }; },
  checkpoint() {
    const saved = savedPositions();
    for (const item of ProjectUI.layers.values()) {
      if (item.project !== state.project || !item.editorReady) continue;
      saved[item.project] = {
        editor: projectEditorLocation(item),
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
  await renderProjectWorkspace(workspace, state);
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

// Remaining bridges for projects.js call-time host helpers.
Object.assign(R, {
  $, esc, params, api, toast, modal, icon, S, W, workspace, state,
  workspaceURL, workspaceResourceURL, workspaceDate, liveError,
  renderWorkspace, selectProject, NotesBrowsing, positionDashboard,
  syncDashboardVisibility,
});
