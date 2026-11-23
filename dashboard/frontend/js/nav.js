// History navigation shared by the router and the views.

let routeHandler = null;

export function setRouteHandler(handler) {
  routeHandler = handler;
}

export function navigate(url, { replace = false } = {}) {
  const target = new URL(url, window.location.href);
  if (target.origin !== window.location.origin) {
    window.location.href = target.href;
    return;
  }
  const next = target.pathname + target.search + target.hash;
  if (replace) {
    window.history.replaceState({}, "", next);
  } else {
    window.history.replaceState({ ...(window.history.state || {}), scroll: window.scrollY }, "");
    window.history.pushState({}, "", next);
  }
  if (routeHandler) routeHandler();
}

// Update the query string of the current page without re-rendering (filters, toggles).
export function updateQuery(values) {
  const url = new URL(window.location.href);
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value === undefined || value === "" || value === false) url.searchParams.delete(key);
    else url.searchParams.set(key, value === true ? "1" : String(value));
  }
  window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
}

export function safeDecode(part) {
  try {
    return decodeURIComponent(part);
  } catch {
    return part;
  }
}

export function scrollToHash(hash) {
  if (!hash || hash === "#") return false;
  const target = document.getElementById(safeDecode(hash.slice(1)));
  if (!target) return false;
  target.scrollIntoView({ block: "start" });
  target.classList.add("flash");
  setTimeout(() => target.classList.remove("flash"), 1600);
  return true;
}
