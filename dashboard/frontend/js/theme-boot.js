// Apply the saved theme before the stylesheet paints. This file is a classic script, not a module,
// because the page policy does not allow inline scripts.
(function () {
  var stored = "system";
  try { stored = localStorage.getItem("lab-theme") || "system"; } catch (e) {}
  if (stored !== "light" && stored !== "dark") stored = "system";
  var dark = stored === "dark" || (stored === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  var root = document.documentElement;
  root.dataset.theme = dark ? "dark" : "light";
  root.dataset.themeChoice = stored;
  root.style.colorScheme = dark ? "dark" : "light";
})();
