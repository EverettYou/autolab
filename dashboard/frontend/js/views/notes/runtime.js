// Shared Notes runtime bag for ESM migration step 1.
// host.js fills helpers; projects.js fills workspace renderers; both read across the bag
// at call time so import order stays host → projects without rewriting call sites yet.
export const runtime = {};
