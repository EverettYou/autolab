// JSON client for the /api routes.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export async function api(path, params = {}, options = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    query.set(key, value === true ? "1" : String(value));
  }
  const text = query.toString();
  const url = `/api/${path}${text ? `?${text}` : ""}`;
  let response;
  try {
    response = await fetch(url, { signal: options.signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError(0, "The dashboard server is not reachable. Is it still running?");
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new ApiError(response.status, (payload && payload.error) || `HTTP ${response.status}`);
  }
  return payload;
}

export async function post(path, body, options = {}) {
  let response;
  try {
    response = await fetch(`/api/${path}`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: options.signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError(0, "The dashboard server is not reachable. Is it still running?");
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new ApiError(response.status, (payload && payload.error) || `HTTP ${response.status}`);
  }
  return payload;
}
