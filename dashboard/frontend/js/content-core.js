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
export function lifecycle(host, cleanup) {
  mounted.get(host)?.();
  let disposed = false;
  const destroy = () => { if (disposed) return; disposed = true; cleanup(); if (mounted.get(host) === destroy) mounted.delete(host); };
    const scope = host.getRootNode?.();
  let shadowObserver;
  if (typeof ShadowRoot !== 'undefined' && scope instanceof ShadowRoot) {
    shadowObserver = new MutationObserver(() => { if (!host.isConnected) destroy(); });
    shadowObserver.observe(scope, {childList:true, subtree:true});
  }
  const originalCleanup = cleanup;
  cleanup = () => { shadowObserver?.disconnect(); originalCleanup(); };
  mounted.set(host, destroy);
  return destroy;
}
new MutationObserver(() => { for (const [host, destroy] of mounted) if (!host.isConnected) destroy(); })
  .observe(document.documentElement, {childList:true, subtree:true});
export function localURL(value) {
  const url = new URL(value, location.href);
  if (url.origin !== location.origin || !/^https?:$/.test(url.protocol)) throw new Error('Preview resources must belong to this dashboard.');
  return url.href;
}

export const fa = name => window.WorkbenchIcons.html(name);
