// A small force layout of the compiled wiki. No external library: a few dozen iterations,
// then a canvas the reader can pan, zoom and click.

import { navigate } from "../nav.js";
import { h } from "../ui.js";

const MIN_SCALE = 0.4;
const MAX_SCALE = 3.5;
// One wheel event moves the scale by at most about 3%. A trackpad tick is smaller still.
const WHEEL_ZOOM_SENSITIVITY = 0.0008;
const MAX_WHEEL_DELTA = 40;
const BUTTON_ZOOM = 1.25;

// One hue family per folder, with lightness staggered so neighbors on the
// wheel do not read as the same blue or the same green.
const COLORS = {
  decoders: "#1d4ed8",
  concepts: "#c026d3",
  codes: "#15803d",
  methods: "#ca8a04",
  implementations: "#0891b2",
  techniques: "#ea580c",
  platform: "#65a30d",
  questions: "#7c3aed",
  comparisons: "#9a3412",
  "deadends": "#dc2626",
  papers: "#be185d",
  records: "#57534e",
  project: "#292524",
  overview: "#a8a29e",
};

function color(folder) {
  return COLORS[folder] || "#64748b";
}

function layout(nodes, edges) {
  const folders = [...new Set(nodes.map((node) => node.folder))].sort();
  const placed = nodes.map((node, index) => {
    const slot = Math.max(folders.indexOf(node.folder), 0);
    const angle = (slot / Math.max(folders.length, 1)) * Math.PI * 2;
    const ring = 160;
    const jitter = ((index * 17) % 40) - 20;
    return {
      ...node,
      x: Math.cos(angle) * ring + jitter,
      y: Math.sin(angle) * ring + ((index * 9) % 30) - 15,
      vx: 0, vy: 0,
    };
  });
  const byId = new Map(placed.map((node) => [node.id, node]));
  const pairs = edges.map((edge) => [byId.get(edge.source), byId.get(edge.target)]).filter((pair) => pair[0] && pair[1]);
  const repulsion = 900;
  for (let step = 0; step < 90; step += 1) {
    for (let i = 0; i < placed.length; i += 1) {
      for (let j = i + 1; j < placed.length; j += 1) {
        const a = placed[i];
        const b = placed[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        const dist = Math.hypot(dx, dy) || 0.1;
        const force = repulsion / (dist * dist);
        dx = (dx / dist) * force;
        dy = (dy / dist) * force;
        a.vx += dx;
        a.vy += dy;
        b.vx -= dx;
        b.vy -= dy;
      }
    }
    for (const [a, b] of pairs) {
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      a.vx += dx * 0.012;
      a.vy += dy * 0.012;
      b.vx -= dx * 0.012;
      b.vy -= dy * 0.012;
    }
    for (const node of placed) {
      node.vx *= 0.72;
      node.vy *= 0.72;
      node.x += Math.max(-12, Math.min(12, node.vx));
      node.y += Math.max(-12, Math.min(12, node.vy));
    }
  }
  return { placed, byId, pairs };
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

export function mountGraph(host, data) {
  const { placed, pairs } = layout(data.nodes, data.edges);
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const node of placed) {
    minX = Math.min(minX, node.x);
    minY = Math.min(minY, node.y);
    maxX = Math.max(maxX, node.x);
    maxY = Math.max(maxY, node.y);
  }
  const pad = 28;
  const worldW = Math.max(1, maxX - minX);
  const worldH = Math.max(1, maxY - minY);

  const canvas = h("canvas", { class: "graph-canvas", tabindex: "0",
    "aria-label": "Knowledge Graph. Drag to pan. Scroll to zoom." });
  const tip = h("div", { class: "graph-tip", hidden: true });
  const zoomOut = h("button", { type: "button", class: "graph-zoom", "aria-label": "Zoom out", title: "Zoom out" }, "−");
  const zoomIn = h("button", { type: "button", class: "graph-zoom", "aria-label": "Zoom in", title: "Zoom in" }, "+");
  const fitButton = h("button", { type: "button", class: "graph-zoom", "aria-label": "Fit", title: "Fit" }, "Fit");
  const toolbar = h("div", { class: "graph-toolbar", role: "group", "aria-label": "Graph controls" },
    zoomOut, zoomIn, fitButton);
  const folders = [...new Set(placed.map((node) => node.folder))].sort((a, b) => a.localeCompare(b));
  const legend = h("ul", { class: "graph-legend" }, folders.map((folder) => h("li", null,
    h("span", { class: "dot", style: `background:${color(folder)}` }), folder,
    h("strong", null, placed.filter((node) => node.folder === folder).length))));
  host.append(h("div", { class: "graph-wrap" }, toolbar, canvas, tip), legend);

  const state = { scale: 1, ox: 0, oy: 0 };
  let hover = null;

  function project(node) {
    return {
      x: state.ox + ((node.x - minX) / worldW) * (canvas.clientWidth - pad * 2) * state.scale + pad,
      y: state.oy + ((node.y - minY) / worldH) * (canvas.clientHeight - pad * 2) * state.scale + pad,
    };
  }

  function draw() {
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(80, 96, 120, 0.28)";
    ctx.beginPath();
    for (const [a, b] of pairs) {
      const pa = project(a);
      const pb = project(b);
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
    }
    ctx.stroke();
    for (const node of placed) {
      const point = project(node);
      const radius = node === hover ? 6.5 : 3.5 + Math.min(node.links, 12) * 0.35;
      ctx.beginPath();
      ctx.fillStyle = color(node.folder);
      ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
      ctx.stroke();
    }
  }

  function refreshControls() {
    zoomIn.disabled = state.scale >= MAX_SCALE - 1e-9;
    zoomOut.disabled = state.scale <= MIN_SCALE + 1e-9;
  }

  function zoomAt(factor, cx, cy) {
    const next = clamp(state.scale * factor, MIN_SCALE, MAX_SCALE);
    const applied = next / state.scale;
    state.ox = cx - (cx - state.ox) * applied;
    state.oy = cy - (cy - state.oy) * applied;
    state.scale = next;
    refreshControls();
    draw();
  }

  function zoomCenter(factor) {
    zoomAt(factor, canvas.clientWidth / 2, canvas.clientHeight / 2);
  }

  function fit() {
    state.scale = 1;
    state.ox = 0;
    state.oy = 0;
    refreshControls();
    draw();
  }

  function nodeAt(x, y) {
    let best = null;
    let bestDist = 14;
    for (const node of placed) {
      const point = project(node);
      const dist = Math.hypot(point.x - x, point.y - y);
      if (dist < bestDist) {
        best = node;
        bestDist = dist;
      }
    }
    return best;
  }

  canvas.addEventListener("mousemove", (event) => {
    const rect = canvas.getBoundingClientRect();
    const node = nodeAt(event.clientX - rect.left, event.clientY - rect.top);
    hover = node;
    canvas.style.cursor = node ? "pointer" : "grab";
    if (!node) {
      tip.hidden = true;
      draw();
      return;
    }
    tip.hidden = false;
    tip.textContent = `${node.title} · ${node.folder}`;
    tip.style.left = `${event.clientX - rect.left + 12}px`;
    tip.style.top = `${event.clientY - rect.top + 12}px`;
    draw();
  });
  canvas.addEventListener("mouseleave", () => {
    hover = null;
    tip.hidden = true;
    draw();
  });
  canvas.addEventListener("click", () => {
    if (hover) navigate(`/wiki/${hover.id.split("/").map(encodeURIComponent).join("/")}`);
  });

  let drag = null;
  canvas.addEventListener("pointerdown", (event) => {
    drag = { x: event.clientX, y: event.clientY, ox: state.ox, oy: state.oy };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drag) return;
    state.ox = drag.ox + (event.clientX - drag.x);
    state.oy = drag.oy + (event.clientY - drag.y);
    draw();
  });
  canvas.addEventListener("pointerup", () => { drag = null; });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const deltaScale = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? canvas.clientHeight : 1;
    const wheelDelta = clamp(event.deltaY * deltaScale, -MAX_WHEEL_DELTA, MAX_WHEEL_DELTA);
    const factor = Math.exp(-wheelDelta * WHEEL_ZOOM_SENSITIVITY);
    const rect = canvas.getBoundingClientRect();
    zoomAt(factor, event.clientX - rect.left, event.clientY - rect.top);
  }, { passive: false });
  zoomIn.addEventListener("click", () => zoomCenter(BUTTON_ZOOM));
  zoomOut.addEventListener("click", () => zoomCenter(1 / BUTTON_ZOOM));
  fitButton.addEventListener("click", () => fit());
  canvas.addEventListener("keydown", (event) => {
    if (event.key === "+" || event.key === "=") { event.preventDefault(); zoomCenter(BUTTON_ZOOM); }
    else if (event.key === "-" || event.key === "_") { event.preventDefault(); zoomCenter(1 / BUTTON_ZOOM); }
    else if (event.key === "0") { event.preventDefault(); fit(); }
  });

  const observer = new ResizeObserver(() => draw());
  observer.observe(canvas);
  fit();
  return () => observer.disconnect();
}
