// Display numbers from /static/site.json. Missing or unusable values stay at the
// defaults in site.defaults.json. The API key is blank in that response.

const DEFAULTS = {
  pages: { references: 20, labs: 20, discussion: 20 },
  home: {
    wiki_folders: 6,
    lab_rows: 4,
    lab_title_lines: 2,
    graph_height: "460px",
    queue_height: "204px",
  },
  search_hits: { navbar: 5, page: 50 },
  wiki_folder_page: 40,
  json_table_height: "304px",
};

const LENGTH = /^(\d+(?:\.\d+)?)(px|rem|em|vh)$/;

function cssLength(value, fallback, minPx, maxPx) {
  if (typeof value !== "string") return fallback;
  const match = LENGTH.exec(value.trim());
  if (!match) return fallback;
  const amount = Number(match[1]);
  const unit = match[2];
  if (unit === "vh") {
    if (amount < 8 || amount > 100) return fallback;
    return `${amount}vh`;
  }
  const px = unit === "px" ? amount : amount * 16;
  if (px < minPx || px > maxPx) return fallback;
  return `${amount}${unit}`;
}

function clampInt(value, fallback, min, max) {
  const number = Number(value);
  if (!Number.isInteger(number)) return fallback;
  return Math.min(max, Math.max(min, number));
}

export function normalizeSite(document) {
  const source = document && typeof document === "object" ? document : {};
  const pages = source.pages && typeof source.pages === "object" ? source.pages : {};
  const home = source.home && typeof source.home === "object" ? source.home : {};
  const hits = source.search_hits && typeof source.search_hits === "object" ? source.search_hits : {};
  return {
    title: typeof source.title === "string" ? source.title : "Lab",
    intro: typeof source.intro === "string" ? source.intro : "",
    pages: {
      references: clampInt(pages.references, DEFAULTS.pages.references, 1, 200),
      labs: clampInt(pages.labs, DEFAULTS.pages.labs, 1, 200),
      discussion: clampInt(pages.discussion, DEFAULTS.pages.discussion, 1, 200),
    },
    home: {
      wiki_folders: clampInt(home.wiki_folders, DEFAULTS.home.wiki_folders, 1, 40),
      lab_rows: clampInt(home.lab_rows, DEFAULTS.home.lab_rows, 1, 20),
      lab_title_lines: clampInt(home.lab_title_lines, DEFAULTS.home.lab_title_lines, 1, 8),
      graph_height: cssLength(home.graph_height, DEFAULTS.home.graph_height, 160, 2000),
      queue_height: cssLength(home.queue_height, DEFAULTS.home.queue_height, 80, 2000),
    },
    search_hits: {
      navbar: clampInt(hits.navbar, DEFAULTS.search_hits.navbar, 1, 50),
      page: clampInt(hits.page, DEFAULTS.search_hits.page, 1, 200),
    },
    wiki_folder_page: clampInt(source.wiki_folder_page, DEFAULTS.wiki_folder_page, 1, 500),
    json_table_height: cssLength(source.json_table_height, DEFAULTS.json_table_height, 80, 2000),
  };
}

export function applySiteChrome(settings) {
  const root = document.documentElement;
  const home = settings.home;
  root.style.setProperty("--lab-rows", String(home.lab_rows));
  root.style.setProperty("--lab-title-lines", String(home.lab_title_lines));
  root.style.setProperty("--graph-height", home.graph_height);
  root.style.setProperty("--queue-height", home.queue_height);
  root.style.setProperty("--json-table-height", settings.json_table_height);
}

let pending = null;

export function siteSettings() {
  if (!pending) {
    pending = fetch("/static/site.json", { headers: { Accept: "application/json" } })
      .then((response) => (response.ok ? response.json() : {}))
      .then((document) => normalizeSite(document))
      .catch(() => normalizeSite({}));
  }
  return pending;
}

export function rememberSite(document) {
  const settings = normalizeSite(document);
  pending = Promise.resolve(settings);
  applySiteChrome(settings);
  return settings;
}
