// The local research queue and its lab reports.

import { api, post } from "../api.js";
import { renderInline, renderLabel, renderMarkdown } from "../markdown.js";
import { updateQuery } from "../nav.js";
import { ago, badge, card, empty, fmtDate, h, pageHeader, setTitle, warnings } from "../ui.js";
import { filterChips, frontmatter, matches, searchInput } from "./common.js";
import { usage, watchSystem } from "../system.js";

const enc = encodeURIComponent;

export async function render({ query, signal }) {
  const data = await api("auto-research", {}, { signal });
  setTitle("Auto Research");
  const header = pageHeader({
    kicker: "Task management",
    title: "Auto Research",
    subtitle: "Drag tasks to set priority. Open a task to read its lab report.",
  });
  if (!data.exists) return h("div", { class: "page" }, header, warnings(data.warnings), empty("No research queue"));
  const pending = data.pending_threads || [];
  const waiting = !pending.length ? h("span", { class: "muted" }, "nothing")
    : h("span", null, pending.map((item, i) => h("span", null,
        i ? ", " : null,
        item.exists
          ? h("a", { href: `/discussion/${enc(item.id)}` }, renderLabel(item.title || item.id))
          : h("span", { class: "missing" }, `${item.id} (missing threads/${item.id}.json)`))));
  const statusSlot = h("span", null, badge(data.status || "unknown"));
  const flagSlot = h("span", { class: "muted" }, data.flag_status && data.flag_status !== data.status
    ? `flag ${data.flag_status}` : "—");
  const liveSlot = h("span", { class: "muted small" },
    (data.liveness && data.liveness.detail) || "Local planning queue");
  const checkedSlot = h("span", { class: "muted" }, data.checked_at ? ago(data.checked_at) : "—");
  const state = card("Research state", factList([
    ["Status", statusSlot],
    ["Flag", flagSlot],
    ["Monitor", liveSlot],
    ["Checked", checkedSlot],
    ["Updated", data.updated ? `${fmtDate(data.updated)} (${ago(data.updated)})` : null],
    ["Deliverable", data.active_deliverable ? renderInline(data.active_deliverable, data.links) : h("span", { class: "muted" }, "none")],
    ["Waiting", waiting],
    ["Schema", data.schema ? h("code", null, data.schema) : null],
    ...data.extra,
  ]));
  function applyLoop(loop) {
    if (!loop) return;
    statusSlot.replaceChildren(badge(loop.status || "unknown"));
    flagSlot.textContent = loop.flag_status && loop.flag_status !== loop.status
      ? `flag ${loop.flag_status}` : "—";
    flagSlot.className = "muted";
    liveSlot.textContent = (loop.liveness && loop.liveness.detail) || "";
    checkedSlot.textContent = loop.checked_at ? ago(loop.checked_at) : "—";
  }

  const filters = { blocked: query.get("blocked") === "1", q: query.get("q") || "" };
  const body = h("tbody");
  const summary = h("p", { class: "muted small" });
  const orderError = h("p", { class: "loop-error", hidden: true });
  let dragging = "";
  let busy = false;

  function sortable() {
    return !filters.blocked && !filters.q.trim();
  }

  function clearDrop() {
    for (const row of body.querySelectorAll("tr")) row.classList.remove("drop-before", "drop-after", "is-dragging");
  }

  async function place(id, target, before) {
    if (!id || !target || id === target || busy) return;
    const ids = data.tasks.map((item) => item.id);
    const from = ids.indexOf(id);
    const to = ids.indexOf(target);
    if (from < 0 || to < 0) return;
    if (before && from + 1 === to) return;
    if (!before && from - 1 === to) return;
    busy = true;
    orderError.hidden = true;
    try {
      const payload = await post("auto-research/order", before ? { id, before: target } : { id, after: target });
      data.tasks = payload.tasks;
      data.counts = payload.counts;
      refresh();
    } catch (err) {
      orderError.hidden = false;
      orderError.textContent = err.message || "The tasks did not move.";
    } finally {
      busy = false;
    }
  }

  function refresh() {
    const shown = data.tasks.filter((item) => (!filters.blocked || item.blocked) && matches(filters.q, item.title, item.id, item.for, item.related_labs.join(" ")));
    const canSort = sortable();
    body.replaceChildren(...shown.map((item) => {
      const row = h("tr", { class: item.blocked ? "blocked" : null, dataset: { id: item.id } });
      const handle = h("span", {
        class: `grip${canSort ? "" : " is-locked"}`, draggable: canSort ? "true" : "false",
        role: "button", tabindex: canSort ? "0" : "-1",
        "aria-label": canSort ? `Drag to reorder ${item.title}` : "Clear the filter to reorder",
        title: canSort ? "Drag to change priority" : "Clear the filter to reorder",
      }, h("i"), h("i"), h("i"));
      handle.addEventListener("keydown", (event) => {
        if (!canSort || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
        event.preventDefault();
        const ids = data.tasks.map((entry) => entry.id);
        const index = ids.indexOf(item.id);
        if (event.key === "ArrowUp" && index > 0) place(item.id, ids[index - 1], true);
        if (event.key === "ArrowDown" && index >= 0 && index < ids.length - 1) place(item.id, ids[index + 1], false);
      });
      handle.addEventListener("dragstart", (event) => {
        if (!canSort) { event.preventDefault(); return; }
        dragging = item.id;
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", item.id);
        event.dataTransfer.setDragImage(row, 24, 16);
        row.classList.add("is-dragging");
      });
      handle.addEventListener("dragend", () => { dragging = ""; clearDrop(); });
      row.addEventListener("dragover", (event) => {
        if (!dragging || dragging === item.id) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        const before = event.clientY < row.getBoundingClientRect().top + row.getBoundingClientRect().height / 2;
        row.classList.toggle("drop-before", before);
        row.classList.toggle("drop-after", !before);
      });
      row.addEventListener("dragleave", (event) => {
        if (!row.contains(event.relatedTarget)) row.classList.remove("drop-before", "drop-after");
      });
      row.addEventListener("drop", (event) => {
        event.preventDefault();
        const before = row.classList.contains("drop-before");
        const id = dragging;
        clearDrop();
        dragging = "";
        place(id, item.id, before);
      });
      row.append(
        h("td", { class: "grip-cell" }, handle),
        h("td", null, item.detail ? h("a", { href: `/auto-research/${enc(item.detail)}` }, renderInline(item.title, data.links)) : renderInline(item.title, data.links),
          item.question && item.question !== item.blocked_on ? h("div", { class: "small" }, renderInline(item.question, data.links)) : null,
          item.next_step ? h("div", { class: "small muted" }, renderInline(item.next_step, data.links)) : null,
          item.blocked_on ? h("div", { class: "small" }, badge("blocked"), ` ${item.blocked_on}`) : null,
          item.related_labs.length ? h("div", { class: "chips" }, item.related_labs.map((lab) => h("a", { class: "chip chip-link", href: `/labs/${enc(lab)}` }, lab))) : null),
        h("td", { class: "fit" }, item.for), h("td", { class: "fit" }, item.gpu),
        h("td", { class: "fit" }, item.time), h("td", { class: "fit muted" }, fmtDate(item.added)));
      return row;
    }));
    summary.textContent = canSort ? `${shown.length} of ${data.tasks.length}` : `${shown.length} of ${data.tasks.length}. Clear the filter to reorder.`;
    updateQuery({ blocked: filters.blocked, q: filters.q });
  }
  const chips = filterChips([{ key: "all", label: "All", count: data.counts.tasks }, { key: "blocked", label: "Blocked", count: data.counts.blocked }],
    filters.blocked ? "blocked" : "all", (key) => { filters.blocked = key === "blocked"; refresh(); });
  const filter = searchInput(filters.q, "Filter tasks", (value) => { filters.q = value; refresh(); });
  refresh();
  const taskCard = card("Tasks", data.tasks.length ? h("div", null,
    h("div", { class: "toolbar" }, chips, h("div", { class: "toolbar-end" }, filter, summary)),
    orderError,
    h("div", { class: "table-wrap" }, h("table", { class: "data queue" },
      h("thead", null, h("tr", null, h("th", { class: "grip-cell", "aria-label": "Order" }), h("th", null, "Task"), h("th", { class: "fit" }, "For"), h("th", { class: "fit" }, "GPU"), h("th", { class: "fit" }, "Time"), h("th", { class: "fit" }, "Added"))),
      body))) : empty("No tasks yet."), { class: "span-3" });
  const systemBody = h("div", null, h("p", { class: "muted" }, "Reading the machine…"));
  const system = card("System status", systemBody);
  refreshSystem(systemBody, signal, applyLoop);
  const actions = card("Actions", h("div", null,
    data.next_action ? h("div", { class: "callout" }, h("div", { class: "callout-label" }, "Next action"), renderMarkdown(data.next_action, data.links, { anchors: false })) : h("p", { class: "muted" }, "No next action."),
    data.last_action ? h("div", { class: "field" }, h("div", { class: "field-label" }, `Last action${data.last_action.at ? ` · ${fmtDate(data.last_action.at)}` : ""}`),
      renderInline(data.last_action.summary, data.links)) : null), { class: "span-3" });
  return h("div", { class: "page" }, header, warnings(data.warnings), h("div", { class: "grid" }, h("div", { class: "status-pair" }, state, system), actions, taskCard));
}

function factList(pairs) {
  const rows = pairs.filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (!rows.length) return null;
  return h("dl", { class: "status-facts" }, rows.map(([key, value]) => [h("dt", null, key), h("dd", null, value)]));
}

function gib(mib) {
  const value = mib / 1024;
  if (!Number.isFinite(value)) return "—";
  return value >= 10 ? value.toFixed(1) : value.toFixed(2);
}

function systemView(status) {
  const agent = status.agent || {};
  const runtime = status.runtime || {};
  const gpus = status.gpus || [];
  const facts = factList([
    ["Agent", agent.name || "—"],
    ["Runtime", runtime.runtime || "—"],
    ["Machine", runtime.machine || "—"],
  ]);
  const boards = gpus.length ? h("div", { class: "gpu-scroll" }, h("table", { class: "gpu-table" },
    h("thead", null, h("tr", null, h("th", null, "GPU"), h("th", null, "Utilization"), h("th", null, "Memory"))),
    h("tbody", null, gpus.map((gpu) => {
      const util = gpu.util_pct == null ? "—" : `${gpu.util_pct}%`;
      const memPct = gpu.mem_total_mib ? (100 * gpu.mem_used_mib) / gpu.mem_total_mib : 0;
      const text = `${gib(gpu.mem_used_mib)} / ${gib(gpu.mem_total_mib)} GB`;
      return h("tr", null,
        h("th", null, `GPU ${gpu.index}`),
        h("td", null, usage(gpu.util_pct, util, `GPU ${gpu.index} utilization ${util}`, "util")),
        h("td", null, usage(memPct, text, `GPU ${gpu.index} memory ${text}`, "mem")));
    })))) : h("p", { class: "muted sys-none" }, "No GPU on this machine.");
  return h("div", null, facts, boards);
}

function refreshSystem(body, signal, onLoop) {
  watchSystem(signal, (status) => {
    body.replaceChildren(systemView(status));
    if (onLoop) onLoop(status && status.loop);
  }, (err) => {
    body.replaceChildren(h("p", { class: "muted" }, err.message || "The machine could not be read."));
  });
}

export async function item({ params, signal }) {
  const data = await api(`auto-research/${enc(params[0])}`, {}, { signal });
  setTitle(data.title, "Auto Research");
  const entry = data.item;
  // pageHeader owns the title; task notes start with the same # heading (sometimes stacked after renames).
  const rendered = renderMarkdown(data.doc.markdown, data.doc.links, { dropLeadingTitles: true });
  return h("div", { class: "page narrow" },
    pageHeader({ kicker: h("a", { href: "/auto-research" }, "Auto Research"), title: renderInline(data.title),
      meta: entry ? [entry.blocked ? badge("blocked") : null, entry.for ? h("span", { class: "meta" }, `for ${entry.for}`) : null,
        entry.gpu ? h("span", { class: "meta" }, `GPU ${entry.gpu}`) : null, entry.time ? h("span", { class: "meta" }, `time ${entry.time}`) : null,
        entry.added ? h("span", { class: "muted small" }, `added ${fmtDate(entry.added)}`) : null] : [badge("not a current task", "warn")] }),
    warnings(data.warnings),
    entry && entry.related_labs.length ? h("div", { class: "related" }, h("span", { class: "muted small" }, "Related labs"),
      h("div", { class: "chips" }, entry.related_labs.map((lab) => h("a", { class: "chip chip-link", href: `/labs/${enc(lab)}` }, lab)))) : null,
    card(null, h("div", null, frontmatter(data.doc.frontmatter, data.doc.links), rendered), { class: "doc-card" }));
}
