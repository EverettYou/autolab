// The agent skill catalog. Each skill is skills/<id>/SKILL.md inside this repository.
// Labels stay on the cards. The search box filters by them, the same way labs and references do.

import { api } from "../api.js";
import { renderInline, renderMarkdown } from "../markdown.js";
import { updateQuery } from "../nav.js";
import { badge, debounce, empty, filesRoute, h, pageHeader, setTitle } from "../ui.js";
import { frontmatter, searchInput } from "./common.js";

const BUNDLES = [
  ["scripts", "script", "scripts"],
  ["references", "reference", "references"],
  ["templates", "template", "templates"],
  ["assets", "asset", "assets"],
  ["tests", "test", "tests"],
  ["machines", "machine", "machines"],
  ["probes", "probe", "probes"],
];

const STAGES = [
  { id: "loop", ids: ["auto-research", "research-threads", "git-workflow", "guards", "runtime-env"] },
  { id: "sources", ids: ["discover-references", "fetch-reference", "reproduce-reference"] },
  { id: "labs", ids: ["create-lab", "research-workflow", "organize-lab"] },
  { id: "lib", ids: ["promote-to-lib", "audit"] },
  { id: "wiki", ids: ["wiki-ingest", "wiki-lint", "wiki-query"] },
];

const OTHER = { id: "other", ids: [] };

function stageFor(id) {
  return STAGES.find((stage) => stage.ids.includes(id)) || OTHER;
}

function inBundle(file, dir) {
  return file === dir || file.startsWith(`${dir}/`);
}

function bundleCounts(files) {
  const known = new Set(BUNDLES.map(([dir]) => dir));
  const counts = BUNDLES.map(([dir, one, many]) => {
    const n = (files || []).filter((file) => inBundle(file, dir)).length;
    return n ? `${n} ${n === 1 ? one : many}` : "";
  }).filter(Boolean);
  const other = (files || []).filter((file) => file !== "SKILL.md" && !known.has(file.split("/")[0])).length;
  if (other) counts.push(`${other} more`);
  return counts;
}

function skillField(label, text, links) {
  if (!text) return null;
  return h("div", { class: "skill-field" },
    h("div", { class: "field-label" }, label),
    h("p", null, renderInline(text, links)));
}

function skillCard(skill) {
  const stage = stageFor(skill.id);
  const facts = bundleCounts(skill.files);
  return h("article", { class: "item" },
    h("div", { class: "item-head" },
      h("a", { class: "item-title", href: skill.route }, skill.name),
      h("span", { class: "item-badges" },
        skill.issues && skill.issues.length ? badge("check", "warn") : null,
        badge(stage.id, "neutral"))),
    skill.description
      ? h("p", { class: "item-text" }, renderInline(skill.description, skill.links))
      : h("p", { class: "item-text" }, "No description yet."),
    skill.usage ? h("p", { class: "skill-when" }, renderInline(skill.usage, skill.links)) : null,
    h("div", { class: "item-facts" }, facts.length ? facts.join(" · ") : "Instructions only"));
}

function wordsOf(query) {
  return String(query || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
}

function textMatch(skill, words) {
  const haystack = [skill.name, skill.id, stageFor(skill.id).id, skill.description, skill.usage, ...(skill.files || [])]
    .join("\n").toLowerCase();
  return words.every((word) => haystack.includes(word));
}

// A query whose every word is a label keeps skills that carry all of those labels.
// Anything else has to occur in the name, the description, or a file in the folder.
function selectSkills(skills, query) {
  const words = wordsOf(query);
  if (!words.length) return { shown: skills, note: "" };
  const known = new Set(skills.map((skill) => stageFor(skill.id).id));
  if (words.every((word) => known.has(word))) {
    const shown = skills.filter((skill) => words.every((word) => stageFor(skill.id).id === word));
    const note = words.length > 1 ? "Filtered to items with all of these labels." : "Filtered to this label.";
    return { shown, note };
  }
  return { shown: skills.filter((skill) => textMatch(skill, words)), note: "" };
}

export async function list({ query, signal }) {
  const data = await api("skills", {}, { signal });
  setTitle("Skills");
  const skills = data.skills || [];
  const state = { q: query.get("q") || query.get("stage") || "" };
  const listHost = h("div");
  const summary = h("span", { class: "muted small" });
  const note = h("p", { class: "muted small search-mode" });

  function paint(text) {
    const q = String(text || "").trim();
    updateQuery({ stage: "", q });
    const { shown, note: mode } = selectSkills(skills, q);
    note.hidden = !mode;
    note.textContent = mode;
    summary.textContent = `${shown.length} of ${skills.length}`;
    if (!skills.length) {
      listHost.replaceChildren(empty("No skills yet.", "skills/ has no SKILL.md files."));
      return;
    }
    listHost.replaceChildren(shown.length
      ? h("div", { class: "cards-list" }, shown.map(skillCard))
      : empty("No skill matches this search."));
  }

  const schedule = debounce((value) => paint(value), 180);
  paint(state.q);
  return h("div", { class: "page" },
    pageHeader({
      kicker: "Agent workflows",
      title: "Skills",
      subtitle: "Procedures an agent follows. This page lists the folders so you can read and edit them. It does not run them.",
    }),
    h("div", { class: "toolbar" },
      h("div", { class: "toolbar-search" }, searchInput(state.q, "Search a skill, or type a label such as loop", (value) => {
        state.q = value;
        schedule(value);
      })),
      h("div", { class: "toolbar-end" }, summary)),
    note,
    listHost);
}

function fileGroups(files) {
  const known = new Set(BUNDLES.map(([dir]) => dir));
  const groups = BUNDLES.map(([dir, , many]) => ({
    title: many,
    files: (files || []).filter((file) => inBundle(file, dir)),
  })).filter((group) => group.files.length);
  const rest = (files || []).filter((file) => file !== "SKILL.md" && !known.has(file.split("/")[0]));
  if (rest.length) groups.push({ title: "other", files: rest });
  return groups;
}

function fileList(skill, files, title) {
  if (!files.length) return null;
  return h("section", { class: "side-section" },
    h("h3", null, title, h("span", { class: "count" }, String(files.length))),
    h("ul", { class: "side-list skill-files" }, files.map((file) => h("li", null,
      h("a", { class: "mono", href: filesRoute(`skills/${skill.id}/${file}`) }, file)))));
}

export async function detail({ params, signal }) {
  const data = await api(`skills/${encodeURIComponent(params[0])}`, {}, { signal });
  setTitle(data.name, "Skills");
  const doc = data.doc || {};
  // pageHeader owns the skill name; SKILL.md starts with the same # heading.
  const rendered = renderMarkdown(doc.markdown || "", doc.links, { dropLeadingTitles: true });
  const stage = stageFor(data.id);
  const groups = fileGroups(data.files);
  const aside = h("aside", { class: "side" },
    h("section", { class: "side-section" },
      h("h3", null, "Folder"),
      h("ul", { class: "side-list" },
        h("li", null, h("a", { href: filesRoute(`skills/${data.id}`) }, "Read the skill folder")),
        h("li", null, h("a", { class: "mono", href: filesRoute(`skills/${data.id}/SKILL.md`) }, "SKILL.md")))),
    ...groups.map((group) => fileList(data, group.files, group.title)),
    data.related && data.related.length ? h("section", { class: "side-section" },
      h("h3", null, "Used with"),
      h("ul", { class: "side-list" }, data.related.map((item) => h("li", null,
        h("a", { href: item.route }, item.name))))) : null);
  const lead = h("div", { class: "skill-abstract" },
    skillField("Description", data.description, data.links),
    skillField("Usage", data.usage, data.links));
  return h("div", { class: "page" },
    pageHeader({
      kicker: h("a", { href: "/skills" }, "Skills"),
      kickerEnd: data.id,
      title: data.name,
      meta: [badge(stage.id, "neutral")],
      note: data.description || data.usage ? lead : null,
    }),
    data.issues && data.issues.length ? h("div", { class: "notice notice-warn", role: "status" },
      h("strong", null, "Worth fixing"),
      h("ul", null, data.issues.map((issue) => h("li", null, issue)))) : null,
    h("div", { class: "grid grid-detail" },
      h("article", { class: "card doc-card wiki-article" },
        frontmatter(doc.frontmatter, doc.links),
        doc.truncated ? h("div", { class: "notice" }, "Only the first 2 MB of this page are shown.") : null,
        rendered),
      aside));
}
