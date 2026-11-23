// Notes workspace host: project list + LaTeX/PDF workbench, mounted in the main dashboard.
import { $, S, workspace, state, liveError } from './notes-context.js';
import { session } from './notes-session.js';
import {
  ProjectUI, renderProjectWorkspace, projectEditorLocation, syncProjectLayers,
} from './projects.js';

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

export const NotesHost = {
  open(project = '') { selectProject(project || ''); },
  wire: wireNotesHost,
  checkpoint: () => NotesBrowsing.checkpoint(),
};

Object.assign(session, {
  renderWorkspace,
  syncDashboardVisibility,
  NotesBrowsing,
});
