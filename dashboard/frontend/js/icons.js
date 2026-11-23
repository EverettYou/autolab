// Dashboard icons from the local Font Awesome solid subset under vendor/fontawesome/.

import { faSvg } from "../vendor/fontawesome/icons.mjs";

/** Semantic names used by the dashboard → local FA glyph ids. */
const ICONS = {
  search: "magnifying-glass",
  menu: "bars",
  close: "xmark",
  sun: "sun",
  moon: "moon",
  system: "circle-half-stroke",
  gear: "gear",
};

export function icon(name, className) {
  const glyph = ICONS[name] || "circle";
  return faSvg(glyph, className) || faSvg("circle", className);
}
