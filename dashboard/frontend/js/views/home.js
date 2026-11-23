// Overview built from the live catalog: a standing title and intro, counts, Auto Research,
// Lab Overview, and the Knowledge Graph. Title/intro come from config.yml (via /static/site.json).
// The next action comes from the research queue; a lab's focus is its lab.json.

import { api } from "../api.js";
import { siteSettings } from "../site-config.js";
import { renderInline } from "../markdown.js";
import { ago, badge, empty, fmtDate, h, plural, setTitle, tone, warnings } from "../ui.js";
import { mountGraph } from "./graph.js";
import { usage, watchSystem } from "../system.js";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function monthKey(lab) {
  const value = lab.created || lab.updated || "";
  return /^\d{4}-\d{2}/.test(value) ? value.slice(0, 7) : "undated";
}

function monthLabel(key) {
  if (key === "undated") return "Undated";
  const [year, month] = key.split("-");
  return `${MONTHS[Number(month) - 1] || month} ${year}`;
}

function statusBar(counts, hrefFor) {
  const entries = Object.entries(counts || {});
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  if (!total) return null;
  return h("div", { class: "stack" },
    h("div", { class: "stackbar", role: "img", "aria-label": entries.map(([key, count]) => `${key} ${count}`).join(", ") },
      entries.map(([key, count]) => h("span", { class: `seg tone-${tone(key)}`, style: `flex-grow:${count}`, title: `${key}: ${count}` }))),
    h("ul", { class: "legend" }, entries.map(([key, count]) => h("li", null,
      h("a", { href: hrefFor(key) }, h("span", { class: `dot tone-${tone(key)}` }), key, h("strong", null, count))))));
}

function statCard(label, value, unit, body, href) {
  return h("section", { class: "stat-card" },
    h("a", { class: "stat-head", href },
      h("span", { class: "stat-label" }, label),
      h("span", { class: "stat-value" }, value),
      h("span", { class: "stat-unit" }, unit)),
    body);
}

function folderLegend(folders, limit) {
  const entries = Object.entries(folders || {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (!entries.length) return null;
  const shown = entries.slice(0, limit);
  const rest = entries.slice(limit).reduce((sum, [, count]) => sum + count, 0);
  return h("ul", { class: "legend" },
    shown.map(([key, count]) => h("li", null, h("a", { href: `/wiki/${encodeURIComponent(key)}` }, key, h("strong", null, count)))),
    rest ? h("li", { class: "muted" }, `+${entries.length - shown.length} folders`) : null);
}

const ISO_DATE = /\d{4}-\d{2}-\d{2}/g;

function reportTitle(title) {
  let text = String(title || "").replace(ISO_DATE, " ");
  text = text.replace(/\s*[—–-]+\s*(?=\()/g, " ");
  text = text.replace(/\(\s*\)/g, " ");
  text = text.replace(/\(\s*,\s*/g, "(").replace(/\s*,\s*\)/g, ")");
  text = text.replace(/^\s*[—–:\-]+\s*/, "").replace(/\s*[—–:\-]+\s*$/, "");
  text = text.replace(/\s{2,}/g, " ").trim();
  return text;
}

function labCard(lab) {
  const title = reportTitle(lab.title);
  return h("a", { class: `tl-card tone-${tone(lab.stage)}`, href: `/labs/${encodeURIComponent(lab.id)}`, title: lab.id },
    h("span", { class: "tl-top" }, h("span", { class: `dot tone-${tone(lab.stage)}` }), h("span", { class: "tl-stage" }, lab.stage),
      h("time", { datetime: lab.created || null }, fmtDate(lab.created))),
    h("span", { class: "tl-title" }, title || "\u00a0"));
}

function timeline(labs, rows = 4, signal) {
  const groups = new Map();
  for (const lab of labs) {
    const key = monthKey(lab);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(lab);
  }
  const dated = [...groups.keys()].filter((key) => key !== "undated").sort();
  if (!dated.length && !groups.has("undated")) return empty("No labs yet");

  const cells = [];
  const yearSpans = [];
  if (dated.length) {
    let key = dated[0];
    const last = dated.at(-1);
    while (key <= last) {
      const year = Number(key.slice(0, 4));
      const month = Number(key.slice(5, 7));
      const span = yearSpans.at(-1);
      if (!span || span.year !== year) yearSpans.push({ year, start: cells.length, end: cells.length + 1 });
      else span.end = cells.length + 1;
      cells.push({ key, label: SHORT_MONTHS[month - 1], name: monthLabel(key), count: (groups.get(key) || []).length });
      if (key === last) break;
      const nextMonth = month === 12 ? 1 : month + 1;
      key = `${month === 12 ? year + 1 : year}-${String(nextMonth).padStart(2, "0")}`;
    }
  }
  if (groups.has("undated")) {
    cells.push({ key: "undated", label: "—", name: "Undated", count: groups.get("undated").length });
  }
  const selected = dated.at(-1) || "undated";

  const track = h("div", { class: "tl-track" });
  const yearRow = h("div", { class: "tl-years", "aria-hidden": "true" });
  const scroller = h("div", { class: "tl-scroll" });
  const line = h("div", { class: "tl-line", role: "tablist", "aria-label": "Months" });
  const grid = h("div", { class: "tl-grid", id: "lab-overview-months", role: "tabpanel" });
  const watcher = new ResizeObserver(() => fitRows());
  let aligned = false;

  function metrics() {
    const style = getComputedStyle(track);
    return {
      slot: parseFloat(style.getPropertyValue("--tl-slot")) || 72,
      label: parseFloat(style.getPropertyValue("--tl-label")) || 48,
    };
  }

  function layout() {
    const { slot } = metrics();
    const view = scroller.clientWidth;
    const width = cells.length * slot;
    line.style.width = `${width}px`;
    const fits = view <= 0 || width <= view + 1;
    scroller.classList.toggle("is-scrollable", !fits);
    if (view > 0 && !aligned) {
      aligned = true;
      if (!fits) {
        const index = Math.max(0, cells.findIndex((cell) => cell.key === selected));
        scroller.scrollLeft = Math.max(0, index * slot - view / 2 + slot / 2);
      }
    } else if (fits) {
      scroller.scrollLeft = 0;
    }
    placeYears();
  }

  function fitRows() {
    const card = grid.querySelector(".tl-card");
    const row = card ? card.getBoundingClientRect().height : 0;
    if (!row) return;
    const gap = parseFloat(getComputedStyle(grid).rowGap) || 0;
    grid.style.maxHeight = `${row * rows + gap * Math.max(0, rows - 1)}px`;
  }

  function placeYears() {
    const { slot, label } = metrics();
    const scrollLeft = scroller.scrollLeft;
    const viewWidth = scroller.clientWidth;
    for (const el of yearRow.children) {
      const yearStart = Number(el.dataset.start) * slot;
      const yearEnd = Number(el.dataset.end) * slot;
      const start = Math.max(yearStart, scrollLeft);
      const end = Math.min(yearEnd, scrollLeft + viewWidth);
      if (end <= start || viewWidth <= 0) {
        el.hidden = true;
        continue;
      }
      el.hidden = false;
      const center = (start + end) / 2;
      const left = Math.min(Math.max(center - label / 2, yearStart), yearEnd - label);
      el.style.left = `${left - scrollLeft}px`;
    }
  }

  function show(key) {
    for (const button of line.querySelectorAll("button")) {
      const on = button.dataset.month === key;
      button.classList.toggle("active", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
      button.tabIndex = on ? 0 : -1;
    }
    const items = groups.get(key) || [];
    watcher.disconnect();
    if (!items.length) {
      grid.style.maxHeight = "";
      grid.replaceChildren(h("p", { class: "muted tl-month-empty" }, "No labs were created this month."));
      return;
    }
    grid.replaceChildren(...items.map(labCard));
    const card = grid.querySelector(".tl-card");
    if (card) watcher.observe(card);
    fitRows();
  }

  yearRow.append(...yearSpans.map((span) => h("span", {
    class: "tl-year", dataset: { start: String(span.start), end: String(span.end) }, hidden: true,
  }, String(span.year))));
  const bounds = yearSpans.length > 1 ? yearSpans.slice(1).map((span) => span.start) : [];
  line.append(
    ...bounds.map((index) => h("span", { class: "tl-bound", style: `--i:${index}` })),
    h("span", { class: "tl-axis" }),
    ...cells.map((cell, index) => {
      const button = h("button", {
        type: "button",
        class: cell.count ? "tl-month" : "tl-month is-empty",
        role: "tab",
        style: `--i:${index}`,
        dataset: { month: cell.key },
        "aria-selected": "false",
        "aria-controls": "lab-overview-months",
        "aria-label": `${cell.name}, ${cell.count} ${cell.count === 1 ? "lab" : "labs"}`,
        tabindex: "-1",
      }, cell.label, cell.count ? h("span", { class: "tl-badge" }, String(cell.count)) : null);
      button.addEventListener("click", () => show(cell.key));
      button.addEventListener("keydown", (event) => {
        const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
        if (!delta) return;
        event.preventDefault();
        const next = cells[index + delta];
        if (!next) return;
        show(next.key);
        const target = line.querySelector(`[data-month="${next.key}"]`);
        if (target) {
          target.focus();
          target.scrollIntoView({ inline: "nearest", block: "nearest" });
        }
      });
      return button;
    }));
  scroller.append(line);
  scroller.addEventListener("scroll", placeYears);
  track.append(yearRow, scroller);

  function wheelDistance(event) {
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? scroller.clientWidth : 1;
    const x = event.deltaX * unit;
    const y = event.deltaY * unit;
    if (event.shiftKey && Math.abs(x) <= Math.abs(y)) return y;
    return Math.abs(x) > Math.abs(y) ? x : y;
  }

  function onWheel(event) {
    const max = scroller.scrollWidth - scroller.clientWidth;
    if (max <= 1) return;
    const delta = wheelDistance(event);
    if (!delta) return;
    const next = Math.min(max, Math.max(0, scroller.scrollLeft + delta));
    if (next === scroller.scrollLeft) return;
    event.preventDefault();
    scroller.scrollLeft = next;
  }

  let drag = null;
  function onPointerDown(event) {
    if (scroller.scrollWidth - scroller.clientWidth <= 1) return;
    if (event.button !== 0 || event.pointerType === "touch") return;
    drag = { id: event.pointerId, x: event.clientX, left: scroller.scrollLeft, moved: false };
  }
  function onPointerMove(event) {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX - drag.x;
    if (!drag.moved && Math.abs(dx) < 4) return;
    if (!drag.moved) {
      drag.moved = true;
      scroller.classList.add("is-dragging");
      scroller.setPointerCapture(event.pointerId);
    }
    scroller.scrollLeft = drag.left - dx;
  }
  function onPointerUp(event) {
    if (!drag || event.pointerId !== drag.id) return;
    if (drag.moved) {
      const swallow = (click) => {
        click.preventDefault();
        click.stopPropagation();
        scroller.removeEventListener("click", swallow, true);
      };
      scroller.addEventListener("click", swallow, true);
    }
    drag = null;
    scroller.classList.remove("is-dragging");
  }

  scroller.addEventListener("wheel", onWheel, { passive: false });
  scroller.addEventListener("pointerdown", onPointerDown);
  scroller.addEventListener("pointermove", onPointerMove);
  scroller.addEventListener("pointerup", onPointerUp);
  scroller.addEventListener("pointercancel", onPointerUp);

  const frame = new ResizeObserver(() => layout());
  frame.observe(scroller);
  if (signal) signal.addEventListener("abort", () => { frame.disconnect(); watcher.disconnect(); }, { once: true });

  show(selected);
  return h("div", { class: "tl" }, track, grid);
}

function facts(pairs) {
  return h("dl", { class: "status-facts" }, pairs.map(([key, value]) => [h("dt", null, key), h("dd", null, value)]));
}

function mountMachine(agentValue, machineValue, gpuHost, signal, onStatus) {
  function show(el, text) {
    el.textContent = text;
    el.classList.toggle("muted", text === "—");
  }
  watchSystem(signal, (status) => {
    show(agentValue, (status.agent && status.agent.name) || "—");
    show(machineValue, (status.runtime && status.runtime.machine) || "—");
    const gpus = [...(status.gpus || [])].sort((a, b) => a.index - b.index);
    gpuHost.replaceChildren(...gpus.map((gpu) => {
      const bar = usage(gpu.util_pct, "", `GPU ${gpu.index} utilization`, "util");
      bar.title = `GPU ${gpu.index}`;
      return bar;
    }));
    if (onStatus) onStatus(status);
  }, () => {
    show(agentValue, "—");
    show(machineValue, "—");
    gpuHost.replaceChildren();
  });
}

function researchPanel(research, signal) {
  const agentValue = h("span", { class: "muted" }, "—");
  const machineValue = h("span", { class: "muted" }, "—");
  const gpuHost = h("span", { class: "home-gpu" });
  const statusSlot = h("span", null, badge((research && research.status) || "unknown"));
  const flagNote = h("span", { class: "muted small" }, "");
  function applyLoop(mon) {
    if (!mon) return;
    statusSlot.replaceChildren(badge(mon.status || "unknown"));
    flagNote.textContent = mon.flag_status && mon.flag_status !== mon.status
      ? ` state flag: ${mon.flag_status}` : "";
  }
  if (research && research.exists) applyLoop(research);
  mountMachine(agentValue, machineValue, gpuHost, signal, (sys) => applyLoop(sys && sys.loop));
  const system = h("div", null,
    h("h3", null, "System status"),
    facts([
      ["Agent", agentValue],
      ["Machine", h("span", { class: "home-machine" }, machineValue, gpuHost)],
    ]));
  const head = h("div", { class: "panel-head" },
    h("div", null, h("h2", null, "Auto Research"),
      h("p", { class: "muted" }, "Monitored status (scheduler + last action), polled live; not the state.json flag alone.")),
    h("a", { class: "more", href: "/auto-research" }, "Open details"));
  if (!research || !research.exists) {
    return h("section", { class: "panel" }, head,
      h("div", { class: "home-split" }, h("div", null, h("h3", null, "Loop state"), empty("No loop state yet")), system));
  }
  const pending = research.pending_threads || [];
  const links = research.links;
  const tasks = research.tasks || [];
  const blocked = (research.counts && research.counts.blocked) || 0;
  const waiting = !pending.length ? h("span", { class: "muted" }, "nothing")
    : h("span", null, pending.map((item, i) => h("span", null,
        i ? ", " : null,
        item.exists
          ? h("a", { href: `/threads/${encodeURIComponent(item.id)}` }, renderInline(item.title || item.id, links))
          : h("span", { class: "missing" }, item.id))));
  const loop = h("div", null,
    h("h3", null, "Loop state"),
    facts([
      ["Status", h("span", null, statusSlot, flagNote)],
      ["Updated", research.updated ? `${fmtDate(research.updated)} (${ago(research.updated)})` : h("span", { class: "muted" }, "—")],
      ["Deliverable", research.active_deliverable ? renderInline(research.active_deliverable, links) : h("span", { class: "muted" }, "none")],
      ["Waiting", waiting],
    ]));
  return h("section", { class: "panel" }, head,
    h("div", { class: "home-split" }, loop, system),
    h("h3", { class: "loop-queue-title" }, `Tasks · ${plural(tasks.length, "task")}${blocked ? `, ${blocked} blocked` : ""}`),
    tasks.length ? h("ol", { class: "loop-queue" }, tasks.map((item) => h("li", { class: item.blocked ? "is-blocked" : null },
      h("span", { class: "loop-pos" }, item.position),
      h("div", { class: "loop-body" },
        item.detail ? h("a", { href: `/auto-research/${encodeURIComponent(item.detail)}` }, renderInline(item.title, links))
          : renderInline(item.title, links),
        item.blocked_on ? h("div", { class: "small muted" }, `blocked on ${item.blocked_on}`) : null,
        item.related_labs && item.related_labs.length ? h("div", { class: "chips" },
          item.related_labs.map((lab) => h("a", { class: "chip chip-link", href: `/labs/${encodeURIComponent(lab)}` }, lab))) : null),
      h("span", { class: "loop-meta" },
        item.blocked ? badge("blocked", "warn") : null,
        item.for ? h("span", null, item.for) : null,
        item.gpu ? h("span", null, item.gpu) : null,
        item.time ? h("span", null, item.time) : null)))) : empty("No tasks yet."));
}

async function siteCopy(signal) {
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  const site = await siteSettings();
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  return {
    title: site.title || "Lab",
    intro: site.intro || "",
    wikiFolders: site.home.wiki_folders,
    labRows: site.home.lab_rows,
  };
}

export async function render({ signal }) {
  const [data, labs, site] = await Promise.all([
    api("home", {}, { signal }), api("labs", {}, { signal }), siteCopy(signal)]);
  setTitle();
  const threads = Object.values(data.thread_counts || {}).reduce((sum, count) => sum + count, 0);
  const open = (data.thread_counts && data.thread_counts.open) || 0;
  const wiki = data.wiki;

  const stats = h("section", { class: "stat-grid", "aria-label": "Repository counts" },
    statCard("References", data.reference_total, data.reference_total === 1 ? "reference" : "references",
      statusBar(data.reference_counts, (key) => `/references?q=${encodeURIComponent(key)}`), "/references"),
    statCard("Labs", data.lab_total, data.lab_total === 1 ? "lab" : "labs",
      statusBar(data.lab_counts, (key) => `/labs?q=${encodeURIComponent(key)}`), "/labs"),
    statCard("Wiki", wiki.pages, wiki.pages === 1 ? "page" : "pages",
      h("div", null,
        h("p", { class: "stat-note" }, `${wiki.compiled} compiled, ${wiki.records} records`),
        folderLegend(wiki.folders, site.wikiFolders)), "/wiki"),
    statCard("Threads", threads, threads === 1 ? "thread" : "threads",
      h("ul", { class: "legend" },
        h("li", null, h("a", { href: "/threads?status=open" }, h("span", { class: "dot tone-warn" }), "open", h("strong", null, open))),
        h("li", null, h("a", { href: "/threads?status=closed" }, h("span", { class: "dot tone-done" }), "closed",
          h("strong", null, (data.thread_counts && data.thread_counts.closed) || 0)))), "/threads"));

  const graphHost = h("div", { class: "graph-stage" }, h("p", { class: "muted graph-loading" }, "Building the knowledge graph…"));
  const graphSection = h("section", { class: "panel" },
    h("div", { class: "panel-head" },
      h("div", null, h("h2", null, "Knowledge Graph"),
        h("p", { class: "muted" }, "Compiled pages and the links between them. A node opens the page. The catalog and dated records are left out.")),
      h("a", { class: "more", href: "/wiki" }, "Open the wiki")),
    graphHost);

  const page = h("div", { class: "page home" }, warnings(data.warnings), warnings(labs.warnings),
    h("header", { class: "home-title" },
      h("h1", null, site.title),
      site.intro ? h("p", { class: "home-intro" }, site.intro) : null),
    stats,
    researchPanel(data.auto_research, signal),
    h("section", { class: "panel" },
      h("div", { class: "panel-head" },
        h("div", null, h("h2", null, "Lab Overview"),
          h("p", { class: "muted" }, "One card per lab, grouped by the month it was created. Open a card to read that lab.")),
        h("a", { class: "more", href: "/labs" }, "All labs")),
      timeline(labs.labs || [], site.labRows, signal)),
    graphSection);

  api("wiki/graph", {}, { signal }).then((graph) => {
    graphHost.replaceChildren();
    if (!graph.nodes.length) {
      graphHost.append(empty("No compiled wiki pages yet"));
      return;
    }
    mountGraph(graphHost, graph);
  }).catch((error) => {
    if (error && error.name === "AbortError") return;
    graphHost.replaceChildren(empty("The knowledge graph could not be built"));
  });
  return page;
}
