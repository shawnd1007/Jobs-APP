# Version 2: AI recruiter development

## Separation and scope

Local branch: `codex/v2-ai-recruiter`, based on published commit `26ffccf7b7422eb48150286cb818d82ebd441c1c`. Draft PR #2 is unchanged. No push, new PR, merge, deployment or release was performed. The local checkout is `version-next` inside the Jobs App workspace; the original source and the earlier temporary checkout remain untouched.

The iPhone target is **Jobs Next**, version 2.0, build 1, bundle `com.shawndelegal.jobsapp.next`. It installs alongside Jobs with separate device storage. Do not connect this development build to the owner's live database for testing. The existing service remains authoritative for that live database.

This is the first functional V2 development checkpoint, not a finished paid product. The [customer workflow](CUSTOMER-WORKFLOW.md) remains the target; incomplete requirements below are explicit.

## Implemented vertical journey

- For You starts with Upload résumé on an empty connected workspace. PDF/text import supplies the full readable text to automatic AI analysis, instead of requiring selected catalog skills and copied experience.
- The backend produces a career summary, evidence-backed skills, primary roles, adjacent roles and cautionary roles. Every supporting quote must occur in the résumé. Cautions do not silently become exclusions.
- The user enters pay, currency/period and flexibility, selects work arrangements, and supplies separate remote-work and office locations. Find my matches stays visible above the tab bar.
- One request orchestrates public discovery, employer-feed parsing, duplicate handling, exact-posting verification, AI comparison and a grouped shortlist. Role searches derive from the generated strategy. The customer does not choose feed identifiers.
- Recruiter discovery allows candidates through to AI evaluation without the legacy manual keyword gate. Retrieval retains the existing bounded source and candidate limits; the AI stage currently analyzes up to 12 retained openings per run and discloses deferred candidates.
- Confirmed constraints can demote AI recommendations. Unknown eligibility or incomparable pay is review, not verified fit. Explicit remote-region exclusions override a broad remote-country label. Hybrid attendance and hiring eligibility remain conservative review questions.
- Recommendations explain experience, duties, gaps and emphasis. Job details opened from the shortlist use recruiter explanations instead of the old profile's score. Existing employer handoff and tracking remain accessible.
- Recruiter state, raw résumé text and match cache have separate SQLite tables. Existing owner preferences are not overwritten. Listing facts, user decisions and application history keep their existing ownership.
- Version checks and an active-operation lock prevent duplicate taps and stale submissions. State survives app relaunch. Service restart marks unfinished work interrupted; retry can reuse the saved résumé. Valid AI comparisons are cached; current constraints and changed posting facts are checked again when reading results.
- OpenAI requests use structured output with application-side validation, backend-only credentials, `store: false`, a reserved daily attempt budget, and redacted failure messages. No provider call is silently retried. The implementation follows the [official structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

## Observed verification — November 12, 2026, Eastern

| Target | Result |
| --- | --- |
| Python | 90 tests passed: the original 79 plus 11 recruiter checks. All use temporary databases and fictional data. |
| Recruiter retrieval | Empty database → mocked public search response → actual Lever feed parser → exact-posting checks → simulated AI matching. Six unfiltered fictional openings; no preinserted shortlist. |
| Contrasting careers | Mara's billing résumé selects a revenue-cycle role; Jules's manufacturing résumé selects CNC work from the same feed. |
| Constraints and recovery | Covered remote exclusion, uncertain region, hybrid, pay below/crossing target, currency mismatch, closed/unverified posting, changed posting facts, bad AI evidence, provider failure, budget reservation, disabled AI, duplicate requests, stale versions, cached analysis and interrupted-work recovery. |
| Existing browser | Both suites passed sequentially on port 18084 using the installed Brave browser through Playwright. No browser page errors. Bundled headless Chromium was unavailable; no claim of a Chromium-specific run. |
| iPhone build | Xcode 27.2 simulator build succeeded for iPhone 17, iOS 27.2. |
| Device Hub | Started with an empty fictional workspace. Selected Mara's PDF in system Files. Automatic career summary/role appeared. Entered $70,000 annual USD, Oregon/United States for remote work and Portland/Oregon for hybrid commute. Find my matches produced the shortlist. |
| Detail and tracking | Opened the recommended role, observed separate checked posting/form evidence and Not Applied tracking. Saved a fictional note and reopened it successfully. No employer submission occurred. |
| Relaunch and appearance | Shortlist survived reinstall/relaunch of the separate app. Dark appearance and accessibility-extra-large text exposed cramped header/filter layout; changed to wrapping header, a large-text menu, and collapsed strategy above results. Rebuilt and visually rechecked. Restored light/default large text. |

The simulator service is `ios/Tests/serve_recruiter_fixture.py`, loopback port 18087, with a temporary database. It patches network and AI responses; production settings cannot select this mock provider. The fixture proves orchestration, source parsing and UI behavior, **not live AI quality, live discovery coverage, or real employer availability**.

Run backend checks with:

```sh
python3 -m unittest -v test_app.py test_prototype.py test_recruiter.py
```

For the disposable simulator backend:

```sh
python3 ios/Tests/serve_recruiter_fixture.py
```

Connect Jobs Next to `http://127.0.0.1:18087` in the simulator. Stopping the fixture discards its fictional workspace. Paid API calls stay off during automated verification.

## Remaining work against the workflow

1. Validate live AI profile quality, matching accuracy, latency and cost in a separately authorized trial. Automated tests deliberately use controlled AI outputs. Paid execution is unverified.
2. Broaden and measure permitted source discovery. Public RSS discovery and existing feed integrations are bounded, best-effort coverage. Validate query breadth, no-results recovery and source outages with live public data. Deferred analysis needs fair continuation rather than repeatedly favoring the first bounded set.
3. Add structured work history, richer optional corrections and explicitly retained user overrides. The current strategy is editable by replacing the résumé, not field-level evidence correction. Finish DOCX and scanned-PDF/OCR import; current UI honestly supports readable PDF/text only.
4. Replace free-text locations with disambiguated places and real commute-distance support. Region aliases and complex employer restrictions require broader evaluation. Hybrid eligibility currently stays in review, even for a nearby office.
5. Complete automated scheduled recruiter refresh and alert policy. The new flow currently runs from Find my matches or Refresh matches; the legacy scheduler is not a complete V2 recruiter schedule.
6. Extend V2 to the browser, Browse, Settings, saved-search criteria and application preparation consistently. The browser remains the legacy workspace, covered by regression checks. Keep legacy controls clearly separate from customer onboarding.
7. Complete offline recruiter caching, durable preference drafts, graceful provider-limit continuation, service-restart recovery of incomplete searches, and full VoiceOver interaction tests. Visual large-text checks are not a VoiceOver audit. No physical-device behavior was verified.
8. Add authenticated customer accounts, isolation, data export/deletion and retention policy, operational security, billing and service-limit disclosure before public access. The local single-workspace prototype still has no customer sign-in. Raw résumé data stays in its private database; do not expose this service publicly.

The build establishes a real executable start-to-shortlist path. These remaining items must be completed and observed before calling the full workflow or paid service ready.
