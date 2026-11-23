// Thin call-time bag for host ↔ projects cycles that ESM import order cannot break yet:
// projects needs renderWorkspace / NotesBrowsing / syncDashboardVisibility from host;
// host needs renderProjectWorkspace / ProjectUI from projects.
export const runtime = {};
