// Mutable Notes session shared by host and project modules (same object refs, no runtime bag).
export const session = {
  renderWorkspace: async () => {},
  syncDashboardVisibility: () => {},
  NotesBrowsing: {
    clean(_id, current) { return current; },
    checkpoint() {},
    currentLocation() { return { view: '', location: {} }; },
  },
};
