# Microsoft Clarity

Project: `zdbchcjjtg`, supplied by the site owner. The default is active after
deployment on anonymous public editorial pages. `CLARITY_PROJECT_ID` may override
the public project ID; set it to an empty value to disable the integration.

The local loader makes no Clarity request until a valid analytics choice is
stored in `cookie_consent_v3` (maximum age 180 days). It reads the cookie rather
than trusting event payloads. ConsentV2 passes `analytics_Storage: granted` and
`ad_Storage: denied`; advertising sharing stays disabled. Withdrawal signals
denial, clears `_clck`/`_clsk` cookies and uses the site's existing page reload to
stop the loaded scripts. Invalid or expired choices fail closed.

The server excludes query parameters, non-GET requests, authenticated sessions,
private routes and unpublished/missing article pages. Forms, public comments and
assistant content are explicitly masked, including dynamically inserted forms.
No custom account identifier is sent to Clarity. Review masking and retention
settings in the Clarity dashboard before relying on session recordings.

The CSP retains nonce/strict-dynamic script protection and permits Clarity
connections only on eligible pages (`https://*.clarity.ms`, `https://c.bing.com`).
The local cookie description and PT/EN privacy policy disclose session recordings.
Do not also install this project through GTM, which would create a second loader.

Validation: Node tests cover consent, expiry, deduplication and revocation;
Python tests cover page/CSP scope and disclosures; browser tests mock Clarity
and send no real analytics.

The browser CI job sets an empty project ID globally. The dedicated mocked test
mounts the real local loader only after its vendor route is mocked, so unrelated
browser regressions cannot send visits to the production Clarity project.

After deployment, accept analytics on an anonymous
public page and inspect a single `/tag/zdbchcjjtg?ref=bwt` request, then verify
collection and the actual recording/masking in the project dashboard. Rejecting
analytics must produce no Clarity requests.

Primary references consulted 2026-11-14:
- https://learn.microsoft.com/en-us/clarity/setup-and-installation/clarity-consent-api-v2
- https://learn.microsoft.com/en-us/clarity/setup-and-installation/clarity-csp
