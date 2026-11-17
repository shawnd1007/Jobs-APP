# Jobs roadmap

[The approved product vision](PRODUCT-VISION.md) sets the direction. [The Build 9 checklist](STAGE-TWO.md) and [verification record](VERIFICATION.md) show where the current prototype stands. Each item below needs its own acceptance evidence.

The matching follow-up adds [distinct duty evidence](COMPLETE-GUIDE.md#7-how-matching-and-verification-work) for ranking and adjacent-title discovery. The next follow-up adds employer-enabled Personio feeds and bounded search with progress and retry. Continue to validate relevance on larger labeled sets and measure discovery coverage and time to results.

## Make the local app dependable for daily use

| Order | Work | Evidence to collect |
| --- | --- | --- |
| 1 | Validate the end-to-end iPhone workflow with Shawn as the first daily tester. Cover the system Files picker, résumé corrections, direct employer links, tracking, follow-ups, offline recovery, and notification behavior on a signed phone. The inbox now shows when an earlier match is closed, needs a recheck, or no longer matches the saved search. | Record the device and build, reproduce any failure with fictional data, and confirm an application survives a search refresh and a reconnect. |
| 2 | Improve the credibility and breadth of discovery. Expand source coverage one employer family at a time, including Workday where practical. Recruitee adds a sixth supported family through its public XML feed. Direct posting checks now gate new alerts, and employer URLs with distinct requisition parameters keep separate records. Published work arrangements now distinguish remote, hybrid and on-site roles. Matching and approval use the same salary policy. Measure deferred checks and improve coverage of dynamic forms, remote residence restrictions and complex pay tiers. | Compare known requisitions against employer pages. Measure direct-link accuracy, stale and duplicate rates, and the relevance of the first ten results. Count only observed working sources. |
| 3 | Make profile, fit, and application preparation more useful. Application Prep now pairs employer duties with profile excerpts and saves a draft. Improve transferable-skill review and evaluate evidence quality across job families. | Test with fictional résumés and labeled postings from multiple occupations. Show the evidence behind a suggestion, gaps and unknowns, and keep any fit score separate from hiring probability. |
| 4 | Close tracking gaps. The browser and connected iPhone can now add an outside application. Validate historical imports and extend corrections for manually entered posting details. | Use fictional CSV exports with duplicate and ambiguous requisitions. The original personal tracker or another confirmed export is needed to import Shawn’s additional history. |

## Ideas from personal testing

- Show meaningful search progress, including the current stage and available counts, so people can tell the search is still working. Handle unknown totals and incomplete coverage honestly.
- Suggest and validate locations as people type, including city, state, and country, while preserving a way to correct the selection.
- Keep a copy of the uploaded résumé in the candidate profile, with clear access, replacement, and deletion controls.
- Under each job posting, offer AI-assisted résumé editing that creates a tailored version from the candidate's master résumé and the actual posting. Keep the original intact, never invent qualifications, and let the candidate review and edit the tailored version before use.
- Measure recruiter AI token usage and cost per search, including retries, to estimate the cost of weekly use and support subscription pricing decisions.
- Explore an optional bring-your-own-OpenAI-key plan with a lower app fee and customer-paid AI usage, potentially allowing searches and résumé edits beyond the included weekly allowance. Evaluate practical limits, key protection, cost transparency, provider rules, and support before promising unlimited use or a price.
- Design a weekly customer search allowance: let an accepted search finish its full intended process, then limit customers to one search per week; provide Shawn a separate allowance for ongoing testing. Keep review, applying and application tracking available throughout the week. Define recovery for failures without charging a user for another weekly search.

### Weekly-search model: questions to resolve

- Define what a complete search covers, including how many openings receive personalized comparison, how unfinished work is surfaced, and how to avoid silently deferring most results.
- Record input and output tokens, model, attempts, retries, and estimated provider cost for each search; separately account for hosting and any search-provider charges. Verify real costs before choosing a customer price or token allowance.
- Decide when the weekly allowance resets, how partial failures recover without consuming another search, and how the user can see the next available search. Keep saved opportunities, application tracking, notes, and follow-ups accessible between searches.
- Give Shawn a clearly separated testing allowance without weakening future customer limits. Validate the policy with real usage and costs before implementing or promising a subscription tier.

These are requested improvements, not claims about completed functionality.

## Validate the paid service before wider access

1. Add authenticated accounts, authorization on every workspace operation, user-controlled correction and deletion, and tested isolation across data, caches, backups, and background jobs.
2. Evaluate deployment, monitoring, consent, accessibility, recovery, and alert delivery for real users. Validate provider usage and cost with a separately authorized trial.
3. Measure time saved, relevance, correct employer links, repeat use, and willingness to pay. About $10/month is a pricing hypothesis. Fifty boards is an illustrative ambition. Use measured value, reliability, and costs to decide what to offer.

### Personal Azure setup in progress

- Azure App Service and a small PostgreSQL flexible server have been created for personal testing. The server has seven-day automatic backups; one initial backup was observed, but a restore has not been tested. Track costs and free-service usage separately from OpenAI usage.
- PostgreSQL support is under development. Isolated local PostgreSQL tests use fictional data and cover startup, settings persistence, job tracking, a mocked search, and AI token records. They do not prove the hosted service or signed phone works.
- Before relying on the hosted service, finish secure App Service database identity and restricted network access, deploy the reviewed backend, test a backup restore and authenticated phone connection, and carry the approved employer-board settings to the new workspace. Do not copy personal résumé or application data without a separate, deliberate migration.

## Prepare for the iPhone App Store

These are future release tasks, not completed features or an approval to publish.

- Enroll in the [Apple Developer Program](https://developer.apple.com/help/account/membership/program-enrollment/) and verify identity. Individual enrollment displays the person's legal name as seller; eligible organizations have additional verification requirements. The program fee is currently $99 per year in the US.
- Build and sign a distribution version in Xcode, create the app record in App Store Connect, and consider TestFlight for pre-release testing.
- Prepare the store listing, screenshots, support information, privacy policy, and accurate data-collection disclosures. Explain how résumés and other personal information are handled, including AI processing.
- Provide Apple with a working way to review the app, including a review account if needed, and submit the app for App Review. If accounts can be created, support account deletion in the app. See [Apple's review guidelines](https://developer.apple.com/app-store/review/guidelines/).
- Before wider release, implement and verify secure accounts, separation of users' information, durable storage, recovery, and a dependable hosted service. Review Apple's current in-app purchase and subscription rules, banking, tax, and fees before setting a paid offering.
