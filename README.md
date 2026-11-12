# shunya-site

The waitlist pages: `/` is Shunya Systems, `/tantr/` is tantr. Plain HTML, CSS and JS; no build
step, no third-party script (TANTR-6).

Pressing **Join** posts one event, `waitlist_joined`, to PostHog's capture endpoint with the
project's public client token: `distinct_id` is the address, properties are `email`, `site`
(`shunya` | `tantr`), `page`, `referrer` and any `utm_*`, and `$set.email` puts the address on the
person. In PostHog: Activity (events) filtered to `waitlist_joined`, or People.

`config.js` holds the token and is **not** in the repo. Write it before serving or deploying:

    powershell -File tools\write-config.ps1     # on the pc, from .secret\logger.env

Try it: `python -m http.server 8080` in this folder, open http://localhost:8080/ and /tantr/.

Deploy to a preview channel (not the live site): `firebase hosting:channel:deploy waitlist --expires 7d --project <project>`.
The live address is Vishal's decision.

Known limit: an ad blocker that blocks PostHog drops the signup, and the form says so. The fix
is a first-party endpoint, a later slice.
