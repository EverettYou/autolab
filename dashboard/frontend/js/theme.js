// Light, dark, or the operating system. The choice is stored on this browser.
// theme-boot.js applies it before the first paint. The navbar icon cycles the three choices.

import { h } from "./ui.js";
import { icon } from "./icons.js";

const KEY = "lab-theme";

export const THEMES = [
  { id: "system", label: "System", icon: "system" },
  { id: "light", label: "Light", icon: "sun" },
  { id: "dark", label: "Dark", icon: "moon" },
];

export function themeChoice() {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    /* storage may be unavailable */
  }
  return "system";
}

export function resolvedTheme(choice = themeChoice()) {
  if (choice === "dark" || choice === "light") return choice;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(choice = themeChoice(), { notify = false } = {}) {
  const resolved = resolvedTheme(choice);
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.dataset.themeChoice = choice;
  root.style.colorScheme = resolved;
  if (notify) window.dispatchEvent(new CustomEvent("lab-theme", { detail: { choice, resolved } }));
  return { choice, resolved };
}

export function setTheme(choice) {
  try { localStorage.setItem(KEY, choice); } catch { /* keep the choice for this view */ }
  return applyTheme(choice, { notify: true });
}

export function watchSystemTheme() {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", () => {
    if (themeChoice() === "system") applyTheme("system", { notify: true });
  });
}

export function mountTheme(root) {
  if (!root) return;
  const button = h("button", { type: "button", class: "theme-button" });
  root.append(button);

  const paint = () => {
    const choice = themeChoice();
    const index = Math.max(0, THEMES.findIndex((item) => item.id === choice));
    const theme = THEMES[index];
    const next = THEMES[(index + 1) % THEMES.length];
    button.replaceChildren(icon(theme.icon));
    const label = `${theme.label}. Click for ${next.label}.`;
    button.setAttribute("aria-label", label);
    button.title = label;
  };

  button.addEventListener("click", () => {
    const index = Math.max(0, THEMES.findIndex((item) => item.id === themeChoice()));
    setTheme(THEMES[(index + 1) % THEMES.length].id);
    paint();
  });
  window.addEventListener("lab-theme", paint);
  paint();
}
