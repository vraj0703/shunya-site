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

Deploy to a preview channel (not a live site), once, from this folder on the pc:

    powershell -File tools\write-config.ps1
    firebase hosting:sites:create shunya-waitlist --project tantr-app     # first time only
    firebase hosting:channel:deploy waitlist --expires 7d --project tantr-app

`firebase.json` names the site `shunya-waitlist`, so nothing here can land on the portfolio's
site. The live address (a domain, the live channel) is Vishal's decision.

With an ad blocker that stops PostHog the signup still arrives on tantr's road, but it is then
missing from PostHog; forwarding collect submissions from the server to the logger closes that.

## Pipeline

`.github/workflows/deploy.yml`, the portfolio's shape: every pull request runs the end-to-end test
and gets a preview URL (commented on the PR); a push to `main` deploys the live channel of the
hosting site `shunya-waitlist` in project `tantr-app`. One-time setup, Vishal's hand, on the pc:

    firebase hosting:sites:create shunya-waitlist --project tantr-app
    firebase init hosting:github          # choose this repo; it creates the service account and
                                          # stores it as a secret; rename it to FIREBASE_SERVICE_ACCOUNT
    gh secret set POSTHOG_TOKEN -R vraj0703/shunya-site     # paste the phc_ project token
    gh variable set POSTHOG_HOST -R vraj0703/shunya-site -b https://us.i.posthog.com

Until the two secrets exist the test runs and the preview and deploy jobs skip themselves.
The domain: Firebase console > Hosting > shunya-waitlist > Add custom domain > shunya.systems,
then the DNS records it shows, at the registrar.
