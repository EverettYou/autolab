# Local Font Awesome Icons

Solid subset used by the EM Boundary dashboard and Notes UI. Served from this
folder — no Font Awesome kit CDN at runtime.

- `svgs/solid/*.svg` — source glyphs (Font Awesome Free 6.7.2)
- `icons.json` — path/viewBox registry
- `icons.mjs` / `icons.js` — loaders for the module app and Notes iframe

Refresh after changing the icon list in `sync.py`:

```bash
python3 dashboard/frontend/vendor/fontawesome/sync.py
```
