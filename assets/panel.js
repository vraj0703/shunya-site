// The right-hand panel: a field of dots breathing through slow noise, drawn on one canvas.
// Shunya (zero) draws its mark, two braces holding a zero, and the field opens inside the zero;
// tantr draws the field itself, warmer.
// No library. It pauses off-screen and when the tab is hidden, and holds one still frame for
// visitors who ask for reduced motion.
(function () {
  var canvas = document.querySelector('.panel canvas');
  if (!canvas) return;
  var ctx = canvas.getContext('2d', { alpha: false });
  var brand = document.documentElement.getAttribute('data-brand') || 'shunya';
  var rgb = brand === 'tantr' ? [255, 90, 54] : [217, 164, 65];
  var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var w = 0, h = 0, dpr = 1, step = 9, running = false, visible = true, t0 = performance.now();
  // The mark (see /logo/): the two braces in units of u = 10; the zero between them is an ellipse 42.36 by 68.54.
  var BRACES = 'M-5 -68.06 C-25 -70 -45 -66 -52.36 -42.36 C-57.17 -26.91 -52.36 -10 -68.54 0 C-52.36 10 -57.17 26.91 -52.36 42.36 C-45 66 -25 70 -5 68.06 C-26.31 63.96 -42.36 34.72 -42.36 0 C-42.36 -34.72 -26.31 -63.96 -5 -68.06 Z ' +
               'M5 -68.06 C25 -70 45 -66 52.36 -42.36 C57.17 -26.91 52.36 -10 68.54 0 C52.36 10 57.17 26.91 52.36 42.36 C45 66 25 70 5 68.06 C26.31 63.96 42.36 34.72 42.36 0 C42.36 -34.72 26.31 -63.96 5 -68.06 Z';
  var mark = null, ink = null, hole = null, cols = 0;

  // value noise: cheap, smooth, good enough for blobs
  function hash(x, y) { var n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return n - Math.floor(n); }
  function smooth(t) { return t * t * (3 - 2 * t); }
  function noise(x, y) {
    var xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
    var a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
    var u = smooth(xf), v = smooth(yf);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }
  function field(x, y, t) {
    return 0.62 * noise(x * 1.7 + t * 0.11, y * 1.7 - t * 0.07) + 0.38 * noise(x * 3.9 - t * 0.09, y * 3.9 + t * 0.13);
  }

  function resize() {
    var r = canvas.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = Math.max(1, Math.round(r.width * dpr)); h = Math.max(1, Math.round(r.height * dpr));
    canvas.width = w; canvas.height = h;
    step = Math.max(7, Math.round(Math.min(w, h) / 78));
    mask();
    if (!running) draw(performance.now());
  }

  // Per dot, once per size: how much of it lies on the braces (ink) and how far it is from the
  // zero's centre (hole: 0 at the centre, rising outward; the field stays quiet close around the mark). The dots do not move, so the
  // frame loop only reads these.
  function mask() {
    if (brand === 'tantr' || typeof Path2D === 'undefined') { ink = hole = null; return; }
    if (!mark) mark = new Path2D(BRACES);
    var s = Math.min(w, h) * 0.27 / 68.54, cx = w / 2, cy = h / 2, q = step * 0.28, rows = Math.ceil(h / step);
    cols = Math.ceil(w / step); ink = new Float32Array(cols * rows); hole = new Float32Array(cols * rows);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    for (var j = 0; j < rows; j++) for (var i = 0; i < cols; i++) {
      var x = (i + 0.5) * step, y = (j + 0.5) * step, n = 0;
      for (var a = 0; a < 5; a++) {
        var px = (x + (a === 1 ? -q : a === 2 ? q : 0) - cx) / s, py = (y + (a === 3 ? -q : a === 4 ? q : 0) - cy) / s;
        if (ctx.isPointInPath(mark, px, py)) n++;
      }
      var ex = (x - cx) / s / 42.36, ey = (y - cy) / s / 68.54, e = ex * ex + ey * ey;
      var gx = (x - cx) / s / 96, gy = (y - cy) / s / 96, g = gx * gx + gy * gy;   // a quiet ground around the mark
      ink[j * cols + i] = n / 5; hole[j * cols + i] = (e < 1 ? Math.pow(e, 1.5) : 1) * (g < 1 ? 0.1 + 0.9 * Math.pow(g, 3) : 1);
    }
  }

  function draw(now) {
    var t = (now - t0) / 1000;
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h);
    var scale = 1 / Math.min(w, h);
    for (var y = step / 2, j = 0; y < h; y += step, j++) {
      for (var x = step / 2, i = 0; x < w; x += step, i++) {
        var v = field(x * scale, y * scale, t);
        var k = Math.min(1, Math.max(0, (v - 0.47) * 6.5));
        if (ink) {
          // shunya: the field clears inside the zero and the braces themselves glow
          var m = j * cols + i;
          k = Math.max(k * hole[m] * 0.85, ink[m]);
        }
        if (k < 0.04) continue;
        var r = step * (0.12 + 0.36 * k);
        ctx.fillStyle = 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',' + (0.18 + 0.82 * k).toFixed(3) + ')';
        ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.fill();
      }
    }
  }

  function loop(now) {
    if (!running) return;
    draw(now);
    requestAnimationFrame(loop);
  }
  function sync() {
    var should = visible && !document.hidden && !still;
    if (should && !running) { running = true; requestAnimationFrame(loop); }
    else if (!should) { running = false; }
  }

  window.addEventListener('resize', resize, { passive: true });
  document.addEventListener('visibilitychange', sync);
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (e) { visible = e[0].isIntersecting; sync(); }).observe(canvas);
  }
  resize(); sync();
})();
