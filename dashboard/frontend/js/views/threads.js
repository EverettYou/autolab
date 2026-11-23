// Threads: the research threads store. The page records the researcher's words (author=user).

import { api, post } from "../api.js";
import { plainText, renderLabel, renderMarkdown } from "../markdown.js";
import { navigate, updateQuery } from "../nav.js";
import { ago, badge, copyButton, debounce, empty, fmtDate, h, pageHeader, plural, setTitle, warnings } from "../ui.js";
import { siteSettings } from "../site-config.js";
import { catalogPage, listPages, runSearch, searchInput, searchNote } from "./common.js";

const enc = encodeURIComponent;
const CATEGORIES = ["direction", "decision", "scope", "checkpoint"];
const PRIORITIES = ["high", "normal", "low"];
const USER_TYPES = [["reply", "Reply"], ["decision", "Decision"], ["instruction", "Instruction"]];

function select(name, options, selected) {
  return h("select", { class: "select", name }, options.map(([value, label]) =>
    h("option", { value, selected: value === selected || null }, label)));
}

function labeled(text, control) {
  return h("label", { class: "composer-field" }, h("span", { class: "field-label" }, text), control);
}

function composer({ heading, hint, controls, submitLabel, onSubmit, onCancel, actions }) {
  const error = h("p", { class: "form-error", hidden: true });
  const button = h("button", { class: "btn btn-primary", type: "button" }, submitLabel);
  button.addEventListener("click", async () => {
    error.hidden = true;
    const siblings = [...(button.parentElement?.querySelectorAll("button") || [])];
    for (const control of siblings) control.disabled = true;
    const original = button.textContent;
    button.textContent = "Saving…";
    try {
      await onSubmit();
    } catch (err) {
      error.hidden = false;
      error.textContent = (err && err.message) || "Could not record that.";
      for (const control of siblings) control.disabled = false;
      button.textContent = original;
    }
  });
  return h("section", { class: "composer" },
    h("div", { class: "composer-head" },
      h("h2", null, heading),
      onCancel ? h("button", { class: "btn btn-small", type: "button", onclick: onCancel }, "Cancel") : null),
    hint ? h("p", { class: "muted small" }, hint) : null,
    ...controls,
    h("div", { class: "form-actions" }, button, ...(actions || [])),
    error);
}

export async function list({ query, signal }) {
  const [data, settings] = await Promise.all([api("threads", {}, { signal }), siteSettings()]);
  setTitle("Threads");
  const state = { q: query.get("q") || query.get("status") || "" };
  const body = h("div", { class: "cards-list" });
  const summary = h("p", { class: "muted small" });
  const note = h("p", { class: "muted small search-mode" });
  let controller = null;
  let paintedQuery = null;
  const trigger = h("button", {
    class: "btn btn-new-thread", type: "button", "aria-expanded": "false", "aria-controls": "new-thread",
  }, "New thread");
  const panel = newThreadPanel(() => setOpen(false));
  panel.hidden = true;

  function setOpen(open) {
    panel.hidden = !open;
    trigger.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) panel.querySelector("input")?.focus();
    else trigger.focus();
  }
  trigger.addEventListener("click", () => setOpen(panel.hidden));

  function row(thread) {
    return h("article", { class: `item${thread.status === "open" ? " item-open" : ""}` },
      h("div", { class: "item-head" },
        h("a", { class: "item-title", href: `/threads/${enc(thread.id)}` }, renderLabel(thread.title)),
        h("div", { class: "item-badges" }, thread.awaiting_human ? badge("awaiting reply", "warn") : null, badge(thread.status),
          thread.priority && thread.priority !== "normal" ? badge(thread.priority) : null)),
      h("div", { class: "item-sub" }, h("span", { class: "mono" }, thread.id),
        thread.category ? h("span", null, thread.category) : null,
        h("span", null, plural(thread.messages, "message")),
        thread.last ? h("span", null, `last from ${thread.last.author} ${ago(thread.last.created)}`) : null,
        thread.related_labs.length ? h("span", null, plural(thread.related_labs.length, "lab")) : null));
  }

  const pages = listPages(body, summary, {
    pageSize: settings.pages.discussion,
    total: data.threads.length,
    emptyText: "No threads match this search.",
    row,
  });

  function paint(shown) {
    const q = state.q.trim();
    const reset = q !== paintedQuery;
    paintedQuery = q;
    pages.paint(shown, reset);
  }

  async function refresh() {
    const q = state.q.trim();
    updateQuery({ status: "", q });
    if (controller) controller.abort();
    if (!q) {
      note.textContent = "";
      paint(data.threads);
      return;
    }
    controller = new AbortController();
    if (signal) signal.addEventListener("abort", () => controller.abort(), { once: true });
    note.textContent = "Searching…";
    try {
      const byId = new Map(data.threads.map((thread) => [thread.id, thread]));
      await runSearch(q, { scope: "threads", limit: 500, signal: controller.signal, onUpdate(result) {
        const group = (result.groups || []).find((item) => item.key === "threads");
        paint((group ? group.items : []).map((item) => byId.get(item.id)).filter(Boolean));
        note.textContent = searchNote(result);
      } });
    } catch (error) {
      if (error && error.name === "AbortError") return;
      note.textContent = "Search is unavailable.";
    }
  }

  const schedule = debounce(() => { refresh(); }, 180);
  const filter = searchInput(state.q, "Search a thread, or type labels such as open decision", (value) => { state.q = value; schedule(); });
  refresh();
  return catalogPage({
    title: "Threads",
    subtitle: "Questions, decisions and instructions between the research agent and the human. Open threads come first. A new thread here is recorded as your instruction.",
    alerts: warnings(data.warnings),
    missing: !data.exists && !data.threads.length ? empty("No Threads store", ".auto-research/state.json does not exist yet.") : null,
    filter, summary, extra: trigger, note, lead: panel, list: h("div", null, body, pages.nav),
  });
}

function newThreadPanel(onCancel) {
  const title = h("input", { class: "filter-input wide", name: "title", maxlength: "200", placeholder: "Short line naming the instruction" });
  const content = h("textarea", { name: "content", rows: "6", placeholder: "The instruction, in your words." });
  const lab = h("input", { class: "filter-input", name: "lab", placeholder: "2026-09-25-g3-bb144-circuit" });
  const category = select("category", CATEGORIES.map((item) => [item, item]), "direction");
  const priority = select("priority", PRIORITIES.map((item) => [item, item]), "normal");
  const box = composer({
    heading: "New thread",
    hint: "This opens a thread as you. The research loop treats an open instruction as its first input. You can close it later from the thread page.",
    controls: [
      labeled("Title", title),
      h("div", { class: "composer-row" }, labeled("Category", category), labeled("Priority", priority), labeled("Related lab (optional)", lab)),
      labeled("Instruction", content),
    ],
    submitLabel: "Open thread",
    onCancel,
    onSubmit: async () => {
      const created = await post("threads", {
        title: title.value.trim(),
        content: content.value.trim(),
        category: category.value,
        priority: priority.value,
        labs: lab.value.trim() ? [lab.value.trim()] : [],
      });
      navigate(`/threads/${enc(created.id)}`);
    },
  });
  box.classList.add("composer-lead");
  box.id = "new-thread";
  box.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    onCancel();
  });
  return box;
}

// Collapse only when the thread is long in *screenfuls*, not by a fixed message count.
// Under ~5 viewports: leave fully expanded. Over that: keep about ~2 viewports of the latest
// messages and offer to show the rest.
const COLLAPSE_AFTER_VIEWPORTS = 5;
const KEEP_VIEWPORTS = 2;
const MESSAGE_GAP_PX = 12;

function message(item, links) {
  return h("article", { class: `message message-${item.author === "user" ? "user" : "agent"}`, id: item.id },
    h("header", { class: "message-head" },
      h("span", { class: "author" }, item.author === "user" ? "Human" : item.author === "agent" ? "Agent" : item.author),
      badge(item.type, item.type === "question" ? "info" : item.type === "decision" || item.type === "instruction" ? "good" : "neutral"),
      h("a", { class: "muted small time", href: `#${item.id}`, title: fmtDate(item.created) }, fmtDate(item.created))),
    item.content ? renderMarkdown(item.content, links, { anchors: false }) : h("p", { class: "muted" }, "(empty message)"));
}

function hashMessageId() {
  const raw = (typeof location !== "undefined" && location.hash) || "";
  return raw.replace(/^#/, "");
}

function viewportHeight() {
  return window.innerHeight || document.documentElement.clientHeight || 800;
}

function scrollToLatestOrHash(root) {
  const id = hashMessageId();
  const target = (id && root.querySelector(`#${CSS.escape(id)}`))
    || root.querySelector(".message:last-of-type");
  if (!target) return;
  requestAnimationFrame(() => {
    target.scrollIntoView({ block: "end", behavior: "auto" });
  });
}

function countFittingFromEnd(nodes, maxHeight, gap = MESSAGE_GAP_PX) {
  let used = 0;
  let count = 0;
  for (let i = nodes.length - 1; i >= 0; i -= 1) {
    const height = nodes[i].offsetHeight;
    const next = count === 0 ? height : used + gap + height;
    if (count > 0 && next > maxHeight) break;
    used = next;
    count += 1;
  }
  return Math.max(count, 1);
}

function messagesView(items, links) {
  if (!items.length) return empty("No messages.");
  const wrap = h("div", { class: "messages" });
  const anchor = hashMessageId();
  const anchorIndex = anchor ? items.findIndex((item) => item.id === anchor) : -1;
  let keepCount = items.length;
  let canCollapse = false;

  function paint(showAll) {
    wrap.replaceChildren();
    const hidden = showAll || !canCollapse ? 0 : Math.max(0, items.length - keepCount);
    if (canCollapse) {
      if (hidden) {
        const button = h("button", {
          class: "btn messages-earlier", type: "button", "aria-expanded": "false",
        }, `Show earlier messages (${hidden})`);
        button.addEventListener("click", () => paint(true));
        wrap.append(h("div", { class: "messages-earlier-wrap" }, button,
          h("p", { class: "muted small" },
            `Showing about two screens of the latest messages (${keepCount} of ${items.length}).`)));
      } else {
        const button = h("button", {
          class: "btn messages-earlier", type: "button", "aria-expanded": "true",
        }, "Collapse earlier messages");
        button.addEventListener("click", () => paint(false));
        wrap.append(h("div", { class: "messages-earlier-wrap" }, button));
      }
    }
    const slice = hidden ? items.slice(-keepCount) : items;
    for (const item of slice) wrap.append(message(item, links));
    scrollToLatestOrHash(wrap);
  }

  // Measure real heights first (message count is a bad proxy: 11 short posts ≠ a long thread).
  for (const item of items) wrap.append(message(item, links));
  requestAnimationFrame(() => {
    const vh = viewportHeight();
    const nodes = [...wrap.querySelectorAll(".message")];
    const totalHeight = wrap.scrollHeight;
    if (totalHeight <= COLLAPSE_AFTER_VIEWPORTS * vh || nodes.length <= 1) {
      scrollToLatestOrHash(wrap);
      return;
    }
    keepCount = countFittingFromEnd(nodes, KEEP_VIEWPORTS * vh);
    if (keepCount >= items.length) {
      scrollToLatestOrHash(wrap);
      return;
    }
    canCollapse = true;
    const expandForHash = anchorIndex >= 0 && anchorIndex < items.length - keepCount;
    paint(expandForHash);
  });
  return wrap;
}

function closeControl(data, content) {
  const note = h("p", { class: "form-error close-note", hidden: true });
  const button = h("button", { class: "btn btn-danger", type: "button" }, "Close thread");
  button.addEventListener("click", async () => {
    const text = content.value.trim();
    if (!text) {
      note.hidden = false;
      note.textContent = "Write a closing note in the message box first.";
      content.focus();
      return;
    }
    note.hidden = true;
    const siblings = [...(button.parentElement?.querySelectorAll("button") || [])];
    for (const control of siblings) control.disabled = true;
    const original = button.textContent;
    button.textContent = "Closing…";
    try {
      await post(`threads/${enc(data.id)}/close`, { content: text });
      navigate(`/threads/${enc(data.id)}`, { replace: true });
    } catch (err) {
      note.hidden = false;
      note.textContent = (err && err.message) || "Could not close that thread.";
      for (const control of siblings) control.disabled = false;
      button.textContent = original;
    }
  });
  return [button, note];
}

function replyPanel(data) {
  const open = data.status === "open";
  const content = h("textarea", { name: "content", rows: "6", placeholder: open ? "Reply, decide, add an instruction, or say why this closes." : "Why this should be open again." });
  const type = select("type", USER_TYPES, open && data.awaiting_human ? "decision" : "instruction");
  return composer({
    heading: open ? "Reply" : "Reopen",
    hint: open
      ? "Posted as you. Use Decision to answer a question, Instruction for a new directive, Reply for anything else. Close thread records this message as your resolution and marks the thread closed."
      : "Posted as you. A closed thread stays closed until someone reopens it with a reason.",
    controls: [h("div", { class: "composer-row" }, labeled("Kind", type)), labeled(open ? "Message" : "Reason", content)],
    submitLabel: open ? "Post reply" : "Reopen thread",
    actions: open ? closeControl(data, content) : null,
    onSubmit: async () => {
      const path = open ? `discussion/${enc(data.id)}/messages` : `discussion/${enc(data.id)}/reopen`;
      await post(path, { content: content.value.trim(), type: type.value });
      navigate(`/threads/${enc(data.id)}`, { replace: true });
    },
  });
}

function terminalHint(data) {
  const reply = data.reply;
  if (!reply || !reply.command) return null;
  const lines = [reply.command, reply.close_command].filter(Boolean);
  return h("details", { class: "reply-note" },
    h("summary", null, "Or from a terminal"),
    h("div", { class: "command" }, h("pre", { class: "code" }, h("code", null, lines.join("\n"))), copyButton(lines.join("\n"))),
    reply.skill ? h("p", { class: "small muted" }, "The full protocol is in ", h("a", { href: `/files/${reply.skill}` }, reply.skill), ".") : null);
}

export async function thread({ params, signal }) {
  const data = await api(`threads/${enc(params[0])}`, {}, { signal });
  setTitle(plainText(data.title), "Threads");
  return h("div", { class: "page narrow" },
    pageHeader({ kicker: h("a", { href: "/threads" }, "Threads"), title: renderLabel(data.title),
      meta: [badge(data.status), data.awaiting_human ? badge("awaiting reply", "warn") : null, data.category ? badge(data.category, "type") : null,
        data.priority && data.priority !== "normal" ? badge(data.priority) : null, h("span", { class: "mono muted" }, data.id),
        h("span", { class: "muted small" }, `opened ${fmtDate(data.created)}${data.updated && data.updated !== data.created ? `, updated ${fmtDate(data.updated)}` : ""}`)] }),
    warnings(data.warnings),
    data.labs.length ? h("div", { class: "related" }, h("span", { class: "muted small" }, "Related labs"),
      h("div", { class: "chips" }, data.labs.map((lab) => lab.exists ? h("a", { class: "chip chip-link", href: `/labs/${enc(lab.id)}`, title: lab.id }, lab.title)
        : h("span", { class: "chip missing", title: "Not a lab in this repository" }, lab.id)))) : null,
    messagesView(data.messages, data.links),
    replyPanel(data),
    terminalHint(data),
    h("nav", { class: "pager" },
      data.previous ? h("a", { href: `/threads/${enc(data.previous)}` }, `Previous: ${data.previous}`) : h("span"),
      data.next ? h("a", { href: `/threads/${enc(data.next)}` }, `Next: ${data.next}`) : h("span")));
}
