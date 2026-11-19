# Changelog

## November 19, 2026

This entry covers the changes since the [November 18 verification record](docs/VERIFICATION.md), including the recruiter reliability review and its follow-up releases.

### Recruiter search and recommendations

- Rank fresh openings before applying the comparison limit, including openings that have not been saved. Give comparably strong role families, employers, and eligible work arrangements room in the results.
- Keep discovered jobs in searchable **Pulled Openings** for browsing and individual comparison. Separate saved jobs from pulled openings and comparison results.
- Screen out definite work-location, work-arrangement, position-level, and published-pay mismatches before using AI. Keep uncertain facts eligible for review. Add position-level preferences, a maximum base-pay setting, and an option to consider jobs below the minimum pay target.
- Compare up to 100 eligible openings in personal mode. Standard mode has a ceiling of 24 and respects the configured daily AI allowance. Reuse cached comparisons and keep the previous shortlist available if the allowance is exhausted.
- Ground career suggestions in numbered résumé passages and verify each cited comparison quote against its own source. Require evidence from the posting before a required qualification can hold a recommendation. A preferred qualification alone does not block a match.
- Credit documented Excel and Google Sheets work for shared spreadsheet duties and honor explicit alternatives in the posting. Preserve separate checks for product-specific duties and credentials.
- Automatically research market pay for promising matches with a verified employer posting and eligible location when comparable employer pay is unavailable. Cache equivalent research and display cited estimates separately from published base pay.
- Rotate public discovery across target roles and locations, recheck promising employer postings, and retain coverage when a source fails or times out.
- Separate local commute eligibility from remote hiring restrictions. Check the posting for state limits and screen out international openings from U.S. searches.

### iPhone and workspace

- Group For You results into close matches, related roles, needs confirmation, and screened-out openings.
- Show the specific reason and next action at the top of review cards and opening details. Show new matches as comparisons, posting checks, and salary research progress.
- Refresh only changed workspace records and use a compact request for recruiter progress. Distinguish a delayed refresh from a lost connection.
- Stop a search while an employer request is waiting. Prevent new AI calls from starting, preserve completed comparisons and the previous shortlist, and report an accepted stop after a restart.
- Scope on-demand job advice to the opening requested. Separate employer facts, recruiter advice, and the user's saved jobs and application tracking.
- Give the sources screen clearer employer information and explain when an existing workspace has no original master résumé file saved.

### Hosting and database

- Run the live backend on Azure App Service B2 and use Azure PostgreSQL. Pool connections, bound database waits, and return a temporary-unavailable response when the database is unavailable.
- Reuse unchanged listing assessments, reduce PostgreSQL work for recruiter progress and dashboard reads, and release connections while waiting for employer sites. Measure server-side request and database stages.
- Restore the live employer-feed catalogue independently from first-use workspace data after the reset removed the original list.
- Support Azure deployment through Resource Manager with a short-lived build artifact URL and restricted management ingress.

### Verification

- Passed 194 Python tests with fictional data and disposable SQLite and PostgreSQL databases.
- Passed the iPhone simulator tests for search progress, early match visibility, review reasons, and automatic and manual salary research with a fictional provider.
- Live salary research has run. The latest observed run produced no accepted cited estimate. Live relevance, elapsed time, and salary coverage for the wider comparison are still to be measured.
