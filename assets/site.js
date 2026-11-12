// The waitlist form. A signup travels two roads: tantr's own (a collect.submission envelope to the
// tantr server) and one event, `waitlist_joined`, straight to PostHog's capture endpoint
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
  var startedAt = new Date().toISOString();

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

  // tantr's own road: the same signup as a collect.submission envelope to the tantr server, the
  // contract the tantr site's waitlist form speaks (formId waitlist, version 2). First-party, so
  // it still arrives when an ad blocker stops the PostHog call. No key: the server's /v0 is open.
  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16);
    });
  }
  function sendTantr(email, startedAt) {
    var server = cfg.tantr === undefined ? 'https://tantr.app' : cfg.tantr;
    if (!server) return Promise.reject(new Error('no server'));
    var now = new Date().toISOString();
    return fetch(server.replace(/\/$/, '') + '/v0/envelopes', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true,
      body: JSON.stringify([{ id: uuid(), type: 'collect.submission', version: '0.1', ts: now, direction: 'up',
        delivery: { guarantee: 'at_least_once' }, meta: { origin: 'app' },
        payload: { formId: 'waitlist', formVersion: 2, answers: { email: email, idea: 'waitlist page: ' + site },
          startedAt: startedAt, completedAt: now } }])
    }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); });
  }
  // Both roads at once; the signup counts when either one arrives.
  function sendBoth(email, startedAt) {
    var roads = [send(email), sendTantr(email, startedAt)].map(function (p) {
      return p.then(function () { return true; }, function () { return false; });
    });
    return Promise.all(roads).then(function (ok) { if (!ok[0] && !ok[1]) throw new Error('both failed'); });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var email = (input.value || '').trim().toLowerCase();
    if (trap && trap.value) { say("You're on the list. We'll write when it opens.", 'ok'); return; } // a bot
    if (!valid(email)) { say('That does not look like an email address.', 'err'); input.focus(); return; }
    if (remembered() === email) { say("You're already on the list with this address.", 'ok'); return; }
    button.disabled = true; say('Adding you…');
    sendBoth(email, startedAt).then(function () {
      remember(email); form.reset();
      say("You're on the list. We'll write when it opens.", 'ok');
    }).catch(function () {
      say('That did not go through. Check your connection or an ad blocker, then try again.', 'err');
    }).then(function () { button.disabled = false; });
  });
})();
