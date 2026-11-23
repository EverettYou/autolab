// Lightweight action menu for the notes file tree.

let menu = null;
let owner = null;

function close() {
  if (!menu) return;
  owner?.setAttribute('aria-expanded', 'false');
  menu.remove();
  menu = null;
  owner = null;
  document.removeEventListener('pointerdown', onPointer, true);
  document.removeEventListener('keydown', onKey, true);
}

function onPointer(event) {
  if (!menu || menu.contains(event.target) || event.target === owner) return;
  close();
}

function onKey(event) {
  if (event.key === 'Escape') close();
}

function actions(anchor, { items = [] } = {}) {
  close();
  owner = anchor;
  menu = document.createElement('ul');
  menu.className = 'action-menu';
  menu.setAttribute('role', 'menu');
  for (const item of items) {
    if (item.separator) {
      menu.append(document.createElement('hr'));
      continue;
    }
    const li = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('role', 'menuitem');
    if (item.danger) button.classList.add('is-danger');
    button.textContent = item.label;
    button.onclick = () => {
      const run = item.run;
      close();
      run?.();
    };
    li.append(button);
    menu.append(li);
  }
  document.body.append(menu);
  const rect = anchor.getBoundingClientRect();
  const width = menu.offsetWidth;
  const height = menu.offsetHeight;
  const left = Math.min(window.innerWidth - width - 8, Math.max(8, rect.right - width));
  const top = Math.min(window.innerHeight - height - 8, rect.bottom + 4);
  Object.assign(menu.style, { left: `${left}px`, top: `${top}px` });
  anchor.setAttribute('aria-expanded', 'true');
  document.addEventListener('pointerdown', onPointer, true);
  document.addEventListener('keydown', onKey, true);
}

export const ActionMenu = { actions, close };
window.ActionMenu = ActionMenu;
