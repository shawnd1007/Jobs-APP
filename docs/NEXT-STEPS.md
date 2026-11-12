# Jobs roadmap

[The approved product vision](PRODUCT-VISION.md) sets the direction. [The Build 9 checklist](STAGE-TWO.md) and [verification record](VERIFICATION.md) show where the current prototype stands. Each item below needs its own acceptance evidence.

## Make the local app dependable for daily use

| Order | Work | Evidence to collect |
| --- | --- | --- |
| 1 | Validate the end-to-end iPhone workflow with Shawn as the first daily tester. Cover the system Files picker, résumé corrections, direct employer links, tracking, follow-ups, offline recovery, and notification behavior on a signed phone. | Record the device and build, reproduce any failure with fictional data, and confirm an application survives a search refresh and a reconnect. |
| 2 | Improve the credibility and breadth of discovery. Expand source coverage one employer family at a time, including Workday where practical. Improve dynamic form verification and explain ambiguous remote eligibility and pay. | Compare known requisitions against employer pages. Measure direct-link accuracy, stale and duplicate rates, and the relevance of the first ten results. Count only observed working sources. |
| 3 | Make profile, fit, and application preparation more useful. Let people review inferred and transferable skills, correct the evidence, and prepare truthful materials they can approve. | Test with fictional résumés and labeled postings from multiple occupations. Show the evidence behind a suggestion, gaps and unknowns, and keep any fit score separate from hiring probability. |
| 4 | Close tracking gaps. Support applications found outside the app and validate confirmed history imports. | Use fictional CSV exports with duplicate and ambiguous requisitions. The original personal tracker or another confirmed export is needed to import Shawn’s additional history. |

## Validate the paid service before wider access

1. Add authenticated accounts, authorization on every workspace operation, user-controlled correction and deletion, and tested isolation across data, caches, backups, and background jobs.
2. Evaluate deployment, monitoring, consent, accessibility, recovery, and alert delivery for real users. Validate provider usage and cost with a separately authorized trial.
3. Measure time saved, relevance, correct employer links, repeat use, and willingness to pay. About $10/month is a pricing hypothesis. Fifty boards is an illustrative ambition. Use measured value, reliability, and costs to decide what to offer.
