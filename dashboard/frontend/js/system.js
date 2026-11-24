// Live machine status from /api/auto-research/system. The Auto Research page and the
// homepage both read that route and draw GPU use with the same meter.

import { api } from "./api.js";
import { h } from "./ui.js";

function loadClass(percent) {
  if (percent == null) return "";
  if (percent >= 90) return " is-full";
  if (percent >= 75) return " is-high";
  if (percent >= 50) return " is-mid";
  return "";
}

export function usage(percent, text, label, kind) {
  const value = percent == null ? 0 : Math.max(0, Math.min(100, percent));
  const meter = h("span", {
    class: `mini-meter${loadClass(percent)}`, role: "meter", "aria-label": label,
    "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(value)),
  }, h("span", { style: `width:${value}%` }));
  if (!text) return h("span", { class: "usage" }, meter);
  return h("span", { class: "usage" }, meter, h("span", { class: `usage-text ${kind || ""}` }, text));
}

export function watchSystem(signal, onStatus, onError) {
  let timer = 0;
  async function load() {
    if (signal.aborted) return;
    try {
      const status = await api("auto-research/system", {}, { signal });
      if (!signal.aborted) onStatus(status);
    } catch (err) {
      if (signal.aborted || err.name === "AbortError") return;
      if (onError) onError(err);
    }
  }
  load();
  // Backend GPU probe is cached (~15s) with a cooldown after timeouts. Polling
  // faster than that only multiplies /api hits; it must not hammer nvidia-smi.
  timer = setInterval(load, 15000);
  signal.addEventListener("abort", () => clearInterval(timer));
}
