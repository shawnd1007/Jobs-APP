# Jobs roadmap

[The approved product vision](PRODUCT-VISION.md) sets the direction. [The Build 9 checklist](STAGE-TWO.md) and [verification record](VERIFICATION.md) show where the current prototype stands. Each item below needs its own acceptance evidence.

The matching follow-up adds [distinct duty evidence](COMPLETE-GUIDE.md#7-how-matching-and-verification-work) for ranking and adjacent-title discovery. The next follow-up adds employer-enabled Personio feeds and bounded search with progress and retry. Continue to validate relevance on larger labeled sets and measure discovery coverage and time to results.

## Make the local app dependable for daily use

| Order | Work | Evidence to collect |
| --- | --- | --- |
| 1 | Validate the end-to-end iPhone workflow with Shawn as the first daily tester. Cover the system Files picker, résumé corrections, direct employer links, tracking, follow-ups, offline recovery, and notification behavior on a signed phone. | Record the device and build, reproduce any failure with fictional data, and confirm an application survives a search refresh and a reconnect. |
| 2 | Improve the credibility and breadth of discovery. Expand source coverage one employer family at a time, including Workday where practical. Direct posting checks now gate new alerts, and employer URLs with distinct requisition parameters keep separate records. Published work arrangements now distinguish remote, hybrid and on-site roles. Measure deferred checks and improve coverage of dynamic forms, remote residence restrictions and pay. | Compare known requisitions against employer pages. Measure direct-link accuracy, stale and duplicate rates, and the relevance of the first ten results. Count only observed working sources. |
| 3 | Make profile, fit, and application preparation more useful. Application Prep now pairs employer duties with profile excerpts and saves a draft. Improve transferable-skill review and evaluate evidence quality across job families. | Test with fictional résumés and labeled postings from multiple occupations. Show the evidence behind a suggestion, gaps and unknowns, and keep any fit score separate from hiring probability. |
| 4 | Close tracking gaps. The browser and connected iPhone can now add an outside application. Validate historical imports and extend corrections for manually entered posting details. | Use fictional CSV exports with duplicate and ambiguous requisitions. The original personal tracker or another confirmed export is needed to import Shawn’s additional history. |

## Validate the paid service before wider access

1. Add authenticated accounts, authorization on every workspace operation, user-controlled correction and deletion, and tested isolation across data, caches, backups, and background jobs.
2. Evaluate deployment, monitoring, consent, accessibility, recovery, and alert delivery for real users. Validate provider usage and cost with a separately authorized trial.
3. Measure time saved, relevance, correct employer links, repeat use, and willingness to pay. About $10/month is a pricing hypothesis. Fifty boards is an illustrative ambition. Use measured value, reliability, and costs to decide what to offer.
