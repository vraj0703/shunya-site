// The waitlist form. One event, `waitlist_joined`, goes straight to PostHog's capture endpoint
// with the project's public client token from config.js (written at deploy time, never in the
// repo). The address is the person's distinct id and is set on the person, so it shows up in
// PostHog under People and under the event. Nothing else is collected and no script is loaded.
(function () {
  var form = document.querySelector('form.join');
  if (!form) return;
  var input = form.querySelector('input[type=email]');
  var trap = form.querySelector('input[name=company]');
  var button = form.querySelector('button');
  var note = document.querySelector('.note');
  var site = document.documentElement.getAttribute('data-brand') || 'shunya';
  var cfg = window.WAITLIST_CONFIG || {};
  var KEY = 'waitlist:' + site;

  function say(text, kind) { note.textContent = text; note.setAttribute('data-kind', kind || ''); }
  function valid(v) { return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v) && v.length <= 254; }
  function utm() {
    var out = {}, q = new URLSearchParams(location.search);
    ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'ref'].forEach(function (k) {
      if (q.get(k)) out[k] = q.get(k).slice(0, 120);
    });
    return out;
  }
  function remembered() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function remember(v) { try { localStorage.setItem(KEY, v); } catch (e) {} }

  function send(email) {
    if (!cfg.token) return Promise.reject(new Error('no token'));
    var props = Object.assign({
      email: email, site: site, page: location.pathname, referrer: document.referrer || '',
      $current_url: location.href, $set: { email: email }, $set_once: { first_waitlist: site }
    }, utm());
    return fetch((cfg.host || 'https://us.i.posthog.com').replace(/\/$/, '') + '/capture/', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true,
      body: JSON.stringify({ api_key: cfg.token, event: 'waitlist_joined', distinct_id: email,
        properties: props, timestamp: new Date().toISOString() })
    }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var email = (input.value || '').trim().toLowerCase();
    if (trap && trap.value) { say("You're on the list. We'll write when it opens.", 'ok'); return; } // a bot
    if (!valid(email)) { say('That does not look like an email address.', 'err'); input.focus(); return; }
    if (remembered() === email) { say("You're already on the list with this address.", 'ok'); return; }
    button.disabled = true; say('Adding you…');
    send(email).then(function () {
      remember(email); form.reset();
      say("You're on the list. We'll write when it opens.", 'ok');
    }).catch(function () {
      say('That did not go through. Check your connection or an ad blocker, then try again.', 'err');
    }).then(function () { button.disabled = false; });
  });
})();
