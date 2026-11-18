# Personal backend trial: reliability and recommendations

Based on `987bc3c5a737b4f676362f5ca62f0c5d2774d2fb` from `codex/v2-ai-recruiter`.

## Behavior

- Compare every retained opening instead of stopping after 12. Prioritize allowed work arrangements/locations, résumé-backed duties and target-title overlap before recency. This orders AI work; it is not an AI recommendation or an eligibility guarantee.
- Personal testing now bypasses the shared daily AI attempt ceiling by default. `JOBS_PERSONAL_UNLIMITED_AI=0` explicitly restores that daily ceiling. Existing attempt/token accounting, caches, four-worker concurrency, retrieval time limits and provider limits remain. This is a personal trial setting, not a customer billing policy.
- Recruiter web queries search across sites rather than restricting each role query to one ATS domain. Only supported employer feeds and posting pages become candidates. Live coverage and relevance still require observation.
- A failed refresh retains the previous shortlist alongside completed new comparisons. iPhone also displays retained results during discovery and after interruption, and offers a direct button to jobs needing confirmation when Recommended is empty. Unknown eligibility stays unconfirmed.
- Restarted searches replace stale progress with an interruption message. Stop status explicitly says in-flight requests are finishing. Employer network waits notice cancellation without waiting for the socket to finish; detached read-only fetches retain their bounded network slots until they exit. Already submitted AI calls finish and retain results; stop prevents subsequent batches and research calls. It does not cancel provider billing.
- Azure PostgreSQL connections use a five-second connection timeout, ten-second statement timeout and three-second lock timeout with verified TLS retained. Managed identity acquisition is separate and still needs live timing diagnosis.
- Automatic market pay research for promising matches remains enabled. Its failures are counted separately and displayed without discarding matches. Estimates never become employer-published pay.

## Verification and limits

Cloud Linux: Python 3.13, temporary databases and fictional résumés/jobs only. The backend suite covers contrasting careers, actual fixture feed parsing, recommendation ordering across more than 12 openings, no default daily AI ceiling, cached pay research/promotion/failure, interrupted/failed refresh recovery, cancellation, and redacted usage accounting. Browser suites run sequentially with system Chromium. Empty-workspace health, recruiter status and dashboard HTTP requests completed locally in under 0.02 seconds; this is not an Azure latency measurement.

No live database, paid provider request, Azure deployment, Mac or iPhone was used. SwiftUI changes require Xcode compilation and device/simulator observation. Local PostgreSQL integration tests remain skipped without their dedicated isolated server; Azure timeout options have mocked verification only. This change does not establish the root cause of the owner's live timeout or guarantee a nonempty live shortlist.

The usage endpoint reports token counts and estimated text cost for known rates; it is not a complete invoice. Web-search fees, unknown/failed request usage, calls outside the retained latest 1,000 and hosting charges are excluded. For a completed authorized live search, record the operation and compare the usage report with the provider's usage/billing data, including salary-research tool charges. No live cost was measured here.

## Next live checks

Use a separate authorized trial workspace with fictional candidate input and permitted public openings. Complete a search, inspect every recommendation group and source failures, confirm automatic salary research and usage totals, and stop during discovery/comparison/research. Observe request timings and service restart behavior on Azure. Read-only App Service logs and timing diagnostics are needed to diagnose live latency; provider usage/billing access is needed to establish actual cost. Never run automated fixtures against the owner's database. Deploying or merging into the deployment branch requires owner approval.
