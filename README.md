# shunya-site

The waitlist pages: `/` is Shunya Systems, `/tantr/` is tantr. Plain HTML, CSS and JS; no build
step, no third-party script (TANTR-6).

Pressing **Join** sends the signup down two roads at once, and it counts when either arrives.
One is tantr's own: a `collect.submission` envelope (formId `waitlist`, version 2) to
`https://tantr.app/v0/envelopes`, kept in the server's up journal (`GET /v0/admin/up`). The other is one event, `waitlist_joined`, to PostHog's capture endpoint with the
project's public client token: `distinct_id` is the address, properties are `email`, `site`
(`shunya` | `tantr`), `page`, `referrer` and any `utm_*`, and `$set.email` puts the address on the
person. In PostHog: Activity (events) filtered to `waitlist_joined`, or People.

`config.js` holds the token and is **not** in the repo. Write it before serving or deploying:

    powershell -File tools\write-config.ps1     # on the pc, from .secret\logger.env

Try it: `python -m http.server 8080` in this folder, open http://localhost:8080/ and /tantr/.

Deploy to a preview channel (not the live site): `firebase hosting:channel:deploy waitlist --expires 7d --project <project>`.
The live address is Vishal's decision.

With an ad blocker that stops PostHog the signup still arrives on tantr's road, but it is then
missing from PostHog; forwarding collect submissions from the server to the logger closes that.
