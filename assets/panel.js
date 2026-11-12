// The right-hand panel: a field of dots breathing through slow noise, drawn on one canvas.
// Shunya (zero) draws a ring that the field opens around; tantr draws the field itself, warmer.
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
    if (!running) draw(performance.now());
  }

  function draw(now) {
    var t = (now - t0) / 1000;
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h);
    var cx = w / 2, cy = h / 2, R = Math.min(w, h) * 0.2, scale = 1 / Math.min(w, h);
    for (var y = step / 2; y < h; y += step) {
      for (var x = step / 2; x < w; x += step) {
        var v = field(x * scale, y * scale, t);
        var k = Math.min(1, Math.max(0, (v - 0.47) * 6.5));
        if (brand !== 'tantr') {
          // shunya: the field clears inside the ring and the ring itself glows
          var d = Math.hypot(x - cx, y - cy);
          var ring = Math.exp(-Math.pow((d - R) / (step * 1.6), 2));
          var hole = d < R ? Math.pow(d / R, 3) : 1;
          k = Math.max(k * hole * 0.85, ring);
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
