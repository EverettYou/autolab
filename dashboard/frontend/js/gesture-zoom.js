// Pinch-to-zoom for the PDF and image readers.
// A trackpad pinch arrives as a wheel event with ctrlKey. A touch pinch is two fingers.
// A plain wheel still scrolls.

const WHEEL_ZOOM_SENSITIVITY = 0.0016;
const MAX_WHEEL_DELTA = 48;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function wheelFactor(event, element) {
  const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? element.clientHeight : 1;
  const delta = clamp(event.deltaY * unit, -MAX_WHEEL_DELTA, MAX_WHEEL_DELTA);
  return Math.exp(-delta * WHEEL_ZOOM_SENSITIVITY);
}

function span(touches) {
  return Math.hypot(touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY);
}

function midpoint(touches) {
  return {
    x: (touches[0].clientX + touches[1].clientX) / 2,
    y: (touches[0].clientY + touches[1].clientY) / 2,
  };
}

// `onZoom(factor, clientX, clientY)` scales around that point. Factor is the
// multiplier for this event, greater than 1 when the gesture opens.
export function bindGestureZoom(element, onZoom) {
  let pinch = null;
  let lastKind = "";
  let lastAt = 0;

  function accept(kind) {
    const now = performance.now();
    if (lastKind && lastKind !== kind && now - lastAt < 50) return false;
    lastKind = kind;
    lastAt = now;
    return true;
  }

  element.addEventListener("wheel", (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    if (!accept("wheel")) return;
    const factor = wheelFactor(event, element);
    if (factor !== 1) onZoom(factor, event.clientX, event.clientY);
  }, { passive: false });

  element.addEventListener("touchstart", (event) => {
    if (event.touches.length !== 2) return;
    pinch = { distance: span(event.touches) };
  }, { passive: true });

  element.addEventListener("touchmove", (event) => {
    if (!pinch || event.touches.length !== 2) return;
    event.preventDefault();
    const distance = span(event.touches);
    if (distance < 1 || pinch.distance < 1) return;
    const factor = clamp(distance / pinch.distance, 0.5, 2);
    pinch.distance = distance;
    if (!accept("touch") || factor === 1) return;
    const point = midpoint(event.touches);
    onZoom(factor, point.x, point.y);
  }, { passive: false });

  element.addEventListener("touchend", (event) => {
    if (event.touches.length < 2) pinch = null;
  });
  element.addEventListener("touchcancel", () => { pinch = null; });

  // Safari reports a trackpad pinch as gesture events. Chromium uses the wheel
  // path above; a recent event from either source suppresses the other.
  element.addEventListener("gesturestart", (event) => {
    event.preventDefault();
    pinch = { distance: event.scale || 1 };
  });
  element.addEventListener("gesturechange", (event) => {
    event.preventDefault();
    const scale = event.scale || 1;
    const base = pinch && pinch.distance ? pinch.distance : 1;
    const factor = clamp(scale / base, 0.5, 2);
    pinch = { distance: scale };
    if (!accept("gesture") || factor === 1) return;
    onZoom(factor, event.clientX, event.clientY);
  });
  element.addEventListener("gestureend", () => { pinch = null; });
}

// Keep the document point under the pointer in place after `resize` changes `element`'s box.
export function zoomAround(stage, element, clientX, clientY, resize) {
  const before = element.getBoundingClientRect();
  const originX = clientX - before.left;
  const originY = clientY - before.top;
  resize();
  const after = element.getBoundingClientRect();
  const ratioX = before.width ? after.width / before.width : 1;
  const ratioY = before.height ? after.height / before.height : 1;
  stage.scrollLeft += after.left - (clientX - originX * ratioX);
  stage.scrollTop += after.top - (clientY - originY * ratioY);
}
