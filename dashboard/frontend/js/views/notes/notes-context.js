// Shared Notes workspace state + API helpers (no dependency on projects.js).
import { api as platformGet, post as platformPost, ApiError } from '../../api.js';
import { toast } from '../../workbench-chrome.js';

export const $ = id => document.getElementById(id);
export const params = values => new URLSearchParams(values);

export const workspace = {
  id: 'papers',
  title: 'Notes',
  editor_layout: 'latex',
  file_operations: true,
  sources: [{ id: 'lab-notes' }],
};

export const S = { view: workspace.id, query: '' };
export const W = { config: { workspaces: [workspace] }, states: {} };
export const state = {
  source: workspace.sources[0].id,
  project: '',
  document: null,
  pdfReaders: [],
};
W.states[workspace.id] = state;

export const liveError = error => toast(error.message);

/** Notes-compatible client: api(url) GET, api(url, body) POST — routes through platform api/post. */
export async function api(url, body, { timeoutMs = 20000 } = {}) {
  const signal = AbortSignal.timeout(timeoutMs);
  try {
    if (body !== undefined) {
      const path = String(url).replace(/^\/api\//, '').split('?')[0];
      return await platformPost(path, body, { signal });
    }
    const parsed = new URL(String(url), location.origin);
    const path = parsed.pathname.replace(/^\/api\//, '');
    const query = Object.fromEntries(parsed.searchParams.entries());
    return await platformGet(path, query, { signal });
  } catch (error) {
    if (error instanceof ApiError) {
      throw Object.assign(new Error(error.message), { status: error.status });
    }
    throw error;
  }
}

export function workspaceURL(route, source, path) {
  return '/api/workspaces/' + route + '?' + params({ source, path });
}

export function workspaceResourceURL(source, path, href) {
  const root = new URL('/' + path.split('/').map(encodeURIComponent).join('/'), location.origin);
  const resource = new URL(href, root);
  if (resource.origin !== location.origin) return null;
  return workspaceURL('file', source, decodeURIComponent(resource.pathname.slice(1)));
}

export function workspaceDate(value) {
  return new Date(value).toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

export function positionDashboard(layer) {
  const host = $('workspace-content');
  if (!host) return;
  const { width, height, top, left } = host.getBoundingClientRect();
  Object.assign(layer.style, {
    width: width + 'px',
    height: height + 'px',
    top: top + 'px',
    left: left + 'px',
  });
}
