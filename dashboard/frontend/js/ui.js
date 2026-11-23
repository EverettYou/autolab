// DOM helpers shared by the views.

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  return append(el, children);
}

export function append(el, children) {
  for (const child of [children].flat(Infinity)) {
    if (child === null || child === undefined || child === false || child === "") continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.firstChild.remove();
  return el;
}

// A stamp with a clock is UTC. Show it in the browser's timezone. A bare date, or midnight UTC,
// is a calendar day (a publication date, a lab day) and stays on that day.
const STAMP = /^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$/;

function utcMillis(value) {
  const match = STAMP.exec(String(value).trim());
  if (!match || !match[2]) return null;
  const seconds = match[4] || "00";
  const offset = match[5] || "";
  const midnight = match[2] === "00" && match[3] === "00" && seconds === "00"
    && (!offset || offset === "Z" || offset === "+00:00" || offset === "+0000" || offset === "-00:00" || offset === "-0000");
  if (midnight) return null;
  const iso = offset
    ? `${match[1]}T${match[2]}:${match[3]}:${seconds}${offset}`
    : `${match[1]}T${match[2]}:${match[3]}:${seconds}Z`;
  const time = Date.parse(iso);
  return Number.isNaN(time) ? null : time;
}

export function fmtDate(value) {
  if (!value) return "";
  const text = String(value).trim();
  const time = utcMillis(text);
  if (time === null) {
    const day = /^(\d{4}-\d{2}-\d{2})/.exec(text);
    return day ? day[1] : text;
  }
  return localStamp(time);
}

function localParts(time, kinds) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    ...kinds, hourCycle: "h23",
  }).formatToParts(new Date(time));
  const get = (type) => parts.find((part) => part.type === type)?.value || "";
  return get;
}

function localStamp(time) {
  const get = localParts(time, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}`;
}

function localClock(hour, minute) {
  const now = new Date();
  const time = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hour, minute);
  const get = localParts(time, { hour: "2-digit", minute: "2-digit" });
  return `${get("hour")}:${get("minute")}`;
}

// Prose writes UTC as 03:18Z or 2026-09-27T03:18:56Z. Show the same moment in local time,
// with no zone label, so the page reads as if the clock was always local.
const ZULU_STAMP = /\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})/g;
const ZULU_CLOCK = /(?<![A-Za-z0-9])(\d{1,2}):(\d{2})(?::\d{2})?Z\b/g;

export function showLocalTimes(text) {
  if (!text || !String(text).includes("Z")) return text;
  const stamps = String(text).replace(ZULU_STAMP, (stamp) => fmtDate(stamp) || stamp);
  return stamps.replace(ZULU_CLOCK, (all, hour, minute) => {
    const h = Number(hour);
    const m = Number(minute);
    if (h > 23 || m > 59) return all;
    return localClock(h, m);
  });
}

export function ago(value) {
  if (!value) return "";
  const parsed = utcMillis(value);
  const time = parsed === null ? Date.parse(value) : parsed;
  if (Number.isNaN(time)) return fmtDate(value);
  const seconds = (Date.now() - time) / 1000;
  if (seconds < 0) return fmtDate(value);
  const steps = [[60, "second"], [3600, "minute"], [86400, "hour"], [86400 * 30, "day"], [86400 * 365, "month"]];
  const units = { second: 1, minute: 60, hour: 3600, day: 86400, month: 86400 * 30, year: 86400 * 365 };
  let unit = "year";
  for (const [limit, name] of steps) {
    if (seconds < limit) { unit = name; break; }
  }
  const count = Math.max(1, Math.floor(seconds / units[unit]));
  if (unit === "second") return "just now";
  return `${count} ${unit}${count === 1 ? "" : "s"} ago`;
}

export function fmtSize(bytes) {
  if (bytes === null || bytes === undefined) return "";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[index]}`;
}

export function plural(count, word, many) {
  return `${count} ${count === 1 ? word : (many || `${word}s`)}`;
}

const TONES = {
  reproduced: "good", complete: "done", active: "info", running: "good", open: "info",
  partial: "warn", attempted: "warn", paused: "warn", blocked: "bad", failed: "bad",
  stale: "bad", unscheduled: "warn", missing: "warn", unknown: "warn",
  fetched: "neutral", pending: "muted", inactive: "muted", closed: "muted", idle: "muted",
  high: "bad", urgent: "bad", normal: "neutral", low: "muted",
};

export function tone(text) {
  return TONES[String(text || "").toLowerCase()] || "neutral";
}

export function badge(text, toneName) {
  if (!text) return null;
  return h("span", { class: `badge tone-${toneName || tone(text)}` }, text);
}

export function empty(title, detail) {
  return h("div", { class: "empty" }, h("p", { class: "empty-title" }, title),
    detail ? h("p", { class: "empty-detail" }, detail) : null);
}

export function warnings(list) {
  if (!list || !list.length) return null;
  return h("div", { class: "notice notice-warn", role: "status" },
    h("strong", null, list.length === 1 ? "Data warning" : "Data warnings"),
    h("ul", null, list.map((item) => h("li", null, item))));
}

export function errorView(error) {
  const status = error && error.status;
  const title = status === 404 ? "Not found" : status === 403 ? "Not available"
    : status === 0 ? "Server unreachable" : "Something went wrong";
  return h("div", { class: "page narrow" },
    h("div", { class: "empty error" }, h("p", { class: "empty-title" }, title),
      h("p", { class: "empty-detail" }, (error && error.message) || String(error)),
      h("p", null, h("a", { href: "/" }, "Back to the overview"))));
}

export function loading(text = "Loading") {
  return h("div", { class: "loading", role: "status" }, h("span", { class: "spinner" }), text);
}

let brandTitle = "Lab";

export function setBrandTitle(title) {
  brandTitle = (typeof title === "string" && title.trim()) ? title.trim() : "Lab";
}

export function setTitle(...parts) {
  document.title = [...parts.filter(Boolean), brandTitle].join(" \u00b7 ");
}

export function copyButton(text, label = "Copy") {
  const button = h("button", { class: "btn btn-small", type: "button" }, label);
  button.addEventListener("click", async () => {
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      const area = h("textarea", { class: "offscreen" });
      area.value = text;
      document.body.append(area);
      area.select();
      try { ok = document.execCommand("copy"); } catch { ok = false; }
      area.remove();
    }
    button.textContent = ok ? "Copied" : "Copy failed";
    setTimeout(() => { button.textContent = label; }, 1500);
  });
  return button;
}

export function debounce(fn, ms) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

export function keyValues(pairs, className = "kv") {
  const rows = pairs.filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (!rows.length) return null;
  return h("dl", { class: className }, rows.map(([key, value]) => [h("dt", null, key), h("dd", null, value)]));
}

export function pageHeader({ kicker, kickerEnd, title, subtitle, note, meta, actions }) {
  const top = kickerEnd
    ? h("div", { class: "kicker-row" },
        kicker ? h("div", { class: "kicker" }, kicker) : null,
        h("div", { class: "kicker-end" }, kickerEnd))
    : (kicker ? h("div", { class: "kicker" }, kicker) : null);
  return h("header", { class: "page-header" },
    top,
    h("div", { class: "title-row" }, h("h1", null, title), actions ? h("div", { class: "actions" }, actions) : null),
    subtitle ? h("p", { class: "subtitle" }, subtitle) : null,
    meta && meta.length ? h("div", { class: "meta-row" }, meta) : null,
    note || null);
}

export function card(title, body, extra) {
  return h("section", { class: `card${extra && extra.class ? ` ${extra.class}` : ""}` },
    title ? h("div", { class: "card-head" }, h("h2", null, title), extra && extra.action ? extra.action : null) : null,
    body);
}

export function encPath(path) {
  return String(path).split("/").map(encodeURIComponent).join("/");
}

export function filesRoute(path) {
  return `/files/${encPath(path)}`;
}

export function chips(items, render) {
  if (!items || !items.length) return null;
  return h("div", { class: "chips" }, items.map((item) => (render ? render(item) : h("span", { class: "chip" }, item))));
}
