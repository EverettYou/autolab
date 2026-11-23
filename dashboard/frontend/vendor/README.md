# Vendored Frontend Libraries

The dashboard works offline, so its third-party libraries are checked in here, unmodified.
Nothing else is loaded from the network.

| Library | Version | Files | License |
| --- | --- | --- | --- |
| [marked](https://github.com/markedjs/marked) | 15.0.7 | `marked/marked.umd.js` | MIT, Copyright (c) 2011-2025 Christopher Jeffrey (header of the file) |
| [DOMPurify](https://github.com/cure53/DOMPurify) | 3.2.3 | `dompurify/purify.min.js` | Apache-2.0 or MPL-2.0, (c) Cure53 and other contributors (header of the file) |
| [KaTeX](https://github.com/KaTeX/KaTeX) | 0.16.11 | `katex/katex.min.js`, `katex/katex.min.css`, `katex/fonts/` | MIT, Copyright (c) 2013-2020 Khan Academy and other contributors (see `katex/README.md`) |
| [Mermaid](https://github.com/mermaid-js/mermaid) | 11.4.1 | `mermaid/mermaid.min.js` | MIT, Copyright (c) Mermaid contributors |
| [PDF.js](https://github.com/mozilla/pdf.js) | (Mozilla viewer build) | `pdfjs/build/`, `pdfjs/web/`, `pdfjs/cmaps/`, `pdfjs/standard_fonts/`, `pdfjs/wasm/` | Apache-2.0, Copyright Mozilla Foundation |

One PDF.js tree and one KaTeX tree serve the whole dashboard (wiki, references, Notes).
The shared reader is `js/pdf-browser.js` (`mountPDF`); markdown math goes through
`js/markdown.js` + global KaTeX from `index.html`.

To upgrade one, replace its files with the release build of the new version, keep the license
header or file, update this table, and check wiki, references PDF, and Notes still render.

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
