# Package verification — November 10, 2026

These observations apply to the prepared source snapshot, not to a published GitHub release.

| Check | Observed outcome |
| --- | --- |
| Clean setup | Created ignored local configuration and an empty startup seed |
| Empty startup | Zero personal jobs; daily schedule and AI disabled |
| Windows unit suite | 34 tests passed using fictional fixtures and temporary databases |
| Linux unit suite | Same 34 tests passed in Python 3.13 Alpine Docker, network disabled and source mounted read-only |
| Approval browser suite | Passed checklist validation, reload persistence, applied/interview transitions, hold/dismiss, geographic guards and mobile overflow checks |
| Workspace browser suite | Passed preference persistence, source pause/resume, compact review panels and all four mobile screens |
| Browser errors | None observed in those suites |
| Dependency install | Lockfile generation and `npm ci` succeeded using declared Playwright 1.62.1 |
| Privacy exclusions | Local profile/config, original personal seed, data, keys, dependency folders and temporary screenshots are ignored |

The committed screenshot uses fictional QA data. There are no real job leads or application records in the source snapshot. API responses are mocked for AI tests; no paid AI call was made. Browser checks ran on Windows using Edge. Actual macOS execution, Xcode compilation and hosted GitHub Actions have not been observed.

The workflow is prepared for Linux unit and browser checks after publication. No remote repository was created and no push was performed as part of package preparation. The local repository is initialized and staged for review; the initial commit remains for the owner to make with their chosen author identity.
