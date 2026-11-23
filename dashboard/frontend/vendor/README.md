# Frontend vendor libraries

Third-party libraries for the dashboard. **Nothing is loaded from a CDN at runtime** after
install; the browser only sees files under this folder.

## What is in Git vs downloaded

| In Git (project-owned) | Downloaded on first `./run.sh` |
| --- | --- |
| `code-editor.js`, `code-editor/` | `mermaid/` |
| `fontawesome/` (+ `sync.py`) | `katex/` |
| `manifest.json`, `install_vendor.py` | `pdfjs/` |
| this README, `CODEMIRROR_NOTICES.txt` | `marked/`, `dompurify/`, `highlight/` |

Pins and sha256 digests live in `manifest.json`. Installer:

```bash
python3 dashboard/frontend/vendor/install_vendor.py          # missing packages only
python3 dashboard/frontend/vendor/install_vendor.py --force  # re-download all
python3 dashboard/frontend/vendor/install_vendor.py --check  # markers present?
```

`./run.sh` calls the same installer when markers are missing (same idea as creating `.venv`).
After a successful install you can work offline; the first bring-up needs network.

## Versions (see manifest for URLs/hashes)

| Library | Version | License |
| --- | --- | --- |
| [marked](https://github.com/markedjs/marked) | 15.0.7 | MIT |
| [DOMPurify](https://github.com/cure53/DOMPurify) | 3.2.3 | Apache-2.0 or MPL-2.0 |
| [KaTeX](https://github.com/KaTeX/KaTeX) | 0.16.11 | MIT |
| [Mermaid](https://github.com/mermaid-js/mermaid) | 11.4.1 | MIT |
| [PDF.js](https://github.com/mozilla/pdf.js) (`pdfjs-dist`) | 6.4.299 | Apache-2.0 |
| [Highlight.js](https://github.com/highlightjs/highlight.js) | 11.11.1 | BSD-3-Clause |

One PDF.js tree and one KaTeX tree serve the whole dashboard (wiki, references, Notes).
The shared reader is `js/pdf-browser.js` (`mountPDF`); markdown math goes through
`js/markdown.js` + global KaTeX from `index.html`.

## Upgrade a package

1. Edit `manifest.json` (version, URL, sha256 — compute hash from the downloaded bytes).
2. Run `python3 dashboard/frontend/vendor/install_vendor.py --force`.
3. Check wiki Mermaid, references/Notes PDF, and math still render.

## Font Awesome subset

Refresh after changing the icon list:

```bash
python3 dashboard/frontend/vendor/fontawesome/sync.py
```

## MIT License (marked, KaTeX)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
