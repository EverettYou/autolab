// Notes projects barrel — re-exports for host.js.
import { ProjectUI, invalidateProjectList } from './project-shared.js';
import { renderProjectWorkspace } from './library.js';
import { syncProjectLayers, projectEditorLocation } from './project-editor.js';
import './project-tree.js';
import './project-build.js';

export {
  ProjectUI,
  renderProjectWorkspace,
  syncProjectLayers,
  invalidateProjectList,
  projectEditorLocation,
};
