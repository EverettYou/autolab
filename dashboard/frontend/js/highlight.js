// One highlighter for code files and fenced blocks. Highlight.js is loaded from
// frontend/vendor before the app module; pages stay usable as plain text if it is missing.

const LIMIT = 80000;
const ALIASES = { shell: "bash", cython: "python", cuda: "cpp", make: "makefile" };

export function highlightSource(text, language) {
  const hljs = window.hljs;
  if (!hljs || !language || language === "text" || !text || text.length > LIMIT) return null;
  let name = language;
  const mapped = ALIASES[name];
  if (mapped && !hljs.getLanguage(name)) name = mapped;
  if (!hljs.getLanguage(name)) return null;
  try {
    return hljs.highlight(text, { language: name, ignoreIllegals: true }).value;
  } catch {
    return null;
  }
}

export function highlightRoot(root) {
  const hljs = window.hljs;
  if (!hljs || !root || !root.querySelectorAll) return;
  for (const code of root.querySelectorAll("pre.code code")) {
    if (code.dataset.highlighted) continue;
    const text = code.textContent || "";
    if (!text || text.length > LIMIT) continue;
    let language = "";
    for (const name of code.classList) {
      if (name.startsWith("language-")) language = name.slice("language-".length);
    }
    const mapped = ALIASES[language];
    if (mapped && !hljs.getLanguage(language)) {
      code.classList.remove(`language-${language}`);
      code.classList.add(`language-${mapped}`);
      language = mapped;
    }
    if (language && !hljs.getLanguage(language)) continue;
    try {
      hljs.highlightElement(code);
    } catch {
      // Leave the block as plain text when a grammar rejects the source.
    }
  }
}
