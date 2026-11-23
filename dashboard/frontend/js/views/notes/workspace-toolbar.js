// Persistent Notes search field: park in #workspace-search-bank, move into a
// [data-workspace-search] slot when a library toolbar asks for it.
import { runtime as R } from './runtime.js';

let workspaceSearchFocus = null;
function workspaceContent() {
  const search = document.getElementById('workspace-search');
  const label = search?.closest('label');
  const bank = document.getElementById('workspace-search-bank');
  if (label && bank && label.parentElement !== bank) {
    workspaceSearchFocus = document.activeElement === search
      ? {start: search.selectionStart, end: search.selectionEnd}
      : null;
    bank.append(label);
  }
  return document.getElementById('workspace-content');
}
function mountWorkspaceSearch() {
  const input = document.getElementById('workspace-search');
  const label = input?.closest('label');
  const slot = document.querySelector('#workspace-content [data-workspace-search]');
  if (!label || !slot || label.parentElement === slot) return;
  slot.append(label);
  if (workspaceSearchFocus && !label.hidden) {
    input.focus({preventScroll: true});
    try { input.setSelectionRange(workspaceSearchFocus.start, workspaceSearchFocus.end); } catch { /* ignore */ }
  }
  workspaceSearchFocus = null;
}
new MutationObserver(mountWorkspaceSearch).observe(document.body, {childList: true, subtree: true});
R.workspaceContent = workspaceContent;
