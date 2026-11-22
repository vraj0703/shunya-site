// The request-access form (SHUNY-13). A request travels two roads: tantr's own (a
// collect.submission envelope to the tantr server, the whole request) and one event,
// `access_requested`, straight to PostHog's capture endpoint with the project's public client
// token from config.js (written at deploy time, never in the repo). The event carries the address
// (the person's distinct id, set on the person as the waitlist did) and only whether a name and a
// reason were given, not what they say. Nothing else is collected and no script is loaded.
(function () {
  // The form lives in one dialog per page, opened by the first page's button and the one at the
  // end of every article.
  var dialog = document.querySelector('dialog.request');
  Array.prototype.forEach.call(document.querySelectorAll('[data-open-request]'), function (b) {
    b.addEventListener('click', function () {
      if (!dialog) return;
      if (dialog.showModal) dialog.showModal(); else dialog.setAttribute('open', '');
      var first = dialog.querySelector('input[type=email]');
      if (first) first.focus();
    });
  });
  var form = document.querySelector('form.join');
  if (!form) return;
  var input = form.querySelector('input[type=email]');
  var nameInput = form.querySelector('input[name=name]');
  var reasonInput = form.querySelector('input[name=reason]');
  var trap = form.querySelector('input[name=company]');
  var button = form.querySelector('button');
  var note = document.querySelector('.note');
  var site = document.documentElement.getAttribute('data-brand') || 'shunya';
  var cfg = window.WAITLIST_CONFIG || {};
  var KEY = 'access:' + site;
  var startedAt = new Date().toISOString();
  var THANKS = 'Thank you. I read every request myself and will write back.';

  function say(text, kind) { note.textContent = text; note.setAttribute('data-kind', kind || ''); }
  function valid(v) { return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v) && v.length <= 254; }
  function line(el, max) { return el ? (el.value || '').replace(/\s+/g, ' ').trim().slice(0, max) : ''; }
  function utm() {
    var out = {}, q = new URLSearchParams(location.search);
    ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'ref'].forEach(function (k) {
      if (q.get(k)) out[k] = q.get(k).slice(0, 120);
    });
    return out;
  }
  function remembered() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function remember(v) { try { localStorage.setItem(KEY, v); } catch (e) {} }

  // PostHog's road: one event. The name and the reason stay off it; it says only whether they
  // were given.
  function send(req) {
    if (!cfg.token) return Promise.reject(new Error('no token'));
    var props = Object.assign({
      email: req.email, site: site, has_name: !!req.name, has_reason: !!req.reason,
      page: location.pathname, referrer: document.referrer || '',
      $current_url: location.href, $set: { email: req.email }, $set_once: { first_access_request: site }
    }, utm());
    return fetch((cfg.host || 'https://us.i.posthog.com').replace(/\/$/, '') + '/capture/', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true,
      body: JSON.stringify({ api_key: cfg.token, event: 'access_requested', distinct_id: req.email,
        properties: props, timestamp: new Date().toISOString() })
    }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); });
  }

  // tantr's own road: the whole request as a collect.submission envelope to the tantr server
  // (formId access_request, version 1; the schema takes any form and any answers). First-party,
  // so it still arrives when an ad blocker stops the PostHog call. No key: the server's /v0 is
  // open.
  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16);
    });
  }
  function sendTantr(req, startedAt) {
    var server = cfg.tantr === undefined ? 'https://tantr.app' : cfg.tantr;
    if (!server) return Promise.reject(new Error('no server'));
    var now = new Date().toISOString();
    var answers = { email: req.email, site: site };
    if (req.name) answers.name = req.name;
    if (req.reason) answers.reason = req.reason;
    return fetch(server.replace(/\/$/, '') + '/v0/envelopes', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true,
      body: JSON.stringify([{ id: uuid(), type: 'collect.submission', version: '0.1', ts: now, direction: 'up',
        delivery: { guarantee: 'at_least_once' }, meta: { origin: 'app' },
        payload: { formId: 'access_request', formVersion: 1, answers: answers,
          startedAt: startedAt, completedAt: now } }])
    }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); });
  }
  // Both roads at once; the request counts when either one arrives.
  function sendBoth(req, startedAt) {
    var roads = [send(req), sendTantr(req, startedAt)].map(function (p) {
      return p.then(function () { return true; }, function () { return false; });
    });
    return Promise.all(roads).then(function (ok) { if (!ok[0] && !ok[1]) throw new Error('both failed'); });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var req = {
      email: (input.value || '').trim().toLowerCase(),
      name: line(nameInput, 80),
      reason: line(reasonInput, 200)
    };
    if (trap && trap.value) { say(THANKS, 'ok'); return; } // a bot
    if (!valid(req.email)) { say('That does not look like an email address.', 'err'); input.focus(); return; }
    if (remembered() === req.email) { say('You have already asked with this address. I will write back.', 'ok'); return; }
    button.disabled = true; say('Sending your request…');
    sendBoth(req, startedAt).then(function () {
      remember(req.email); form.reset();
      say(THANKS, 'ok');
    }).catch(function () {
      say('That did not go through. Check your connection or an ad blocker, then try again.', 'err');
    }).then(function () { button.disabled = false; });
  });
})();
