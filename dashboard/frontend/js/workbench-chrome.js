// Shared Notes/workbench toast + modal chrome (workspace toast/dialog ids).
import { escape as esc } from './content-core.js';

export { esc };

let toastTimer;

export function toast(message, { outputId = 'workspace-toast' } = {}) {
  const output = document.getElementById(outputId);
  if (!output) return;
  output.textContent = message;
  output.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { output.hidden = true; }, 4500);
}

export function modal(title, body, actions, submit, { dialogId = 'workspace-modal' } = {}) {
  const dialog = document.getElementById(dialogId);
  if (!dialog) return;
  dialog.innerHTML = '<form><h2>' + esc(title) + '</h2>' + body +
    '<footer><button type="button" class="text-button" data-cancel>Cancel</button>' + actions + '</footer><p role="alert"></p></form>';
  dialog.querySelector('[data-cancel]').onclick = () => dialog.close();
  dialog.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    try { await submit(new FormData(event.target)); }
    catch (error) { dialog.querySelector('[role=alert]').textContent = error.message; }
  };
  dialog.showModal();
}
