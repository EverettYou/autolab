// Shared lifecycle and presentation state. Document and attachment bytes never enter storage.
export const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const states = new Map(), mounted = new Map();
export function viewState(key, patch) {
  if (!key) return {};
  const next = {...states.get(key), ...patch};
  states.delete(key); states.set(key, next);
  while (states.size > 200) states.delete(states.keys().next().value);
  return next;
}
// Only tear down after a host has been connected. Callers often mount into a
// detached shell and append it on the next tick; destroying on that gap aborts
// PDF.js before pagesinit (stuck on "Opening PDF…").
const seenConnected = new WeakMap();
export function lifecycle(host, cleanup) {
  mounted.get(host)?.();
  let disposed = false;
  const destroy = () => {
    if (disposed) return;
    disposed = true;
    cleanup();
    if (mounted.get(host) === destroy) mounted.delete(host);
  };
  const scope = host.getRootNode?.();
  let shadowObserver;
  if (typeof ShadowRoot !== 'undefined' && scope instanceof ShadowRoot) {
    shadowObserver = new MutationObserver(() => {
      if (host.isConnected) seenConnected.set(host, true);
      else if (seenConnected.get(host)) destroy();
    });
    shadowObserver.observe(scope, { childList: true, subtree: true });
  }
  const originalCleanup = cleanup;
  cleanup = () => { shadowObserver?.disconnect(); originalCleanup(); };
  if (host.isConnected) seenConnected.set(host, true);
  mounted.set(host, destroy);
  return destroy;
}
new MutationObserver(() => {
  for (const [host, destroy] of mounted) {
    if (host.isConnected) { seenConnected.set(host, true); continue; }
    if (seenConnected.get(host)) destroy();
  }
}).observe(document.documentElement, { childList: true, subtree: true });
export function localURL(value) {
  const url = new URL(value, location.href);
  if (url.origin !== location.origin || !/^https?:$/.test(url.protocol)) throw new Error('Preview resources must belong to this dashboard.');
  return url.href;
}

export const fa = name => window.WorkbenchIcons.html(name);
