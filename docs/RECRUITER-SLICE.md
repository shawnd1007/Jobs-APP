# Recruiter evidence slice — November 12, 2026

## Base and scope

Branch `codex/trustworthy-recruiter` starts at `faa54f2`, the latest head of open PR #2 (`codex/stage-two-iphone-polish`), rather than older main. The approved product vision is copied unchanged from PR #3 (`55bf56d`). Neither PR was merged and neither existing branch was rewritten.

This extends the working single-workspace flow. It is not an account-based commercial service and does not add billing, deployment, application submission, push delivery, or authentication. Use only a trusted private workspace. All clients connected to a server can access its profile, excerpts, and application history. Profile isolation tests prove advice does not leak between supplied profile inputs; they do **not** prove multi-user authorization.

## What to try on a Mac

```sh
git fetch origin
git switch --track origin/codex/trustworthy-recruiter
python3 setup_project.py
JOBS_BIND_HOST=127.0.0.1 python3 app.py
```

Setup preserves existing config, data and seed files. Back up a live workspace before updating it. For simulator testing open `ios/Shawn's iPhone Job App.xcodeproj`, select JobsApp and an iPhone simulator, then connect to `http://localhost:8084`. See ios/README.md for physical-device private-network setup. No Xcode build has been performed for this branch in Cloud.

1. Use **Connect to your Mac**, not the fictional sample workspace.
2. Settings → Edit Search Profile: import a synthetic PDF/text résumé that mentions SQL, review the literal mentions and approve the ones that reflect real experience. Inspect, edit or remove the excerpt in Reviewed Résumé Evidence before saving. Set role phrases, skills, locations, work setting and pay. Empty location preferences retain legacy geography rules; configure them explicitly for a different user.
3. Add an employer board slug, for example Greenhouse `figma` or Ashby `linear`. These are discovery sources, not recommendations for your profile. Configure role phrases appropriate to the board; an empty shortlist can be correct. Existing pipeline caps and filters still apply.
4. Alerts → Run Employer Search. Inspect failures and source health. Browse → All Listings shows retained roles. Job details now distinguish hard salary/location checks from role/skill preferences, unknown information, selected skills lacking résumé excerpts, and preparation suggestions quoting only approved evidence.
5. Inspect link status. `verified` means a recent same-requisition URL, exact title and application-form check, with the employer board relationship checked against the live feed. It is not a guarantee of employer identity or ongoing availability. Location is taken from the employer feed, not independently reverified on the form. `unverified`, `stale`, and `unavailable` require attention. Old verification timestamps without scoped provenance remain unverified. Inaccessible/dynamic forms do not pass merely because a feed returned a URL.
6. Save to My Jobs, open the posting, apply yourself, then update Application Tracking, dates and notes. Existing concurrency checks and history preservation remain in place.
7. Change or remove an excerpt and save the profile. Preparation updates on refresh, without persisting candidate-specific suggestions into shared employer facts. Removing the local résumé also clears the editor's excerpt draft; save to remove server excerpts. Existing backups may retain prior preferences and need separate private retention management.

## Sources actually checked

Live checks on November 12 from this environment used the existing public adapters, with no paid calls:

| Source | Observed result | Limitation |
| --- | --- | --- |
| Greenhouse / figma | 142 live jobs; first job's direct application passed stricter verification | One checked page, not all 142 applications; salary may be absent |
| Ashby / linear | 33 live jobs; first application remained unverified | Accessible content did not satisfy the stricter checks |
| Lever / netflix | HTTP failure | This slug was unavailable; adapter fixtures do not establish live availability |

No LinkedIn, Indeed or Monster integration is claimed. Existing public search can discover supported employer-board URLs; the pipeline retrieves the actual board and requisition rather than inventing an application URL. This slice does not implement general cross-domain intermediary-to-employer resolution. Unsupported/aggregator URLs remain rejected or unresolved, not verified. Source outages preserve existing application records; complete successful feeds can identify closed listings. No security restrictions or authentication were bypassed.

## AI and privacy

The new preparation is deterministic excerpt overlap, explicitly labeled as rules. There are no new AI inferences or fabricated AI responses. Existing optional per-job AI review is disabled without both server configuration and user enablement. To enable later, provision `OPENAI_API_KEY` on the backend or an ignored `secrets/openai.key`, choose an available model and daily attempt cap in Settings, then explicitly request a job review. Provider calls can cost money; none were made or verified during this task. Existing provider advice uses the candidate profile text and job facts, not this new evidence preparation engine.

Full résumé preview stays on the device. Approved excerpts are sent to the server when saved; the editor discloses this. Excerpts persist in ignored preferences, not Git or listing rows. Avoid real résumés in screenshots, logs and test fixtures. No personal résumé, credentials or application database was used in testing.

## Data compatibility and validation

This is an additive preferences key (`resume_evidence`) and optional API fields. No SQLite schema change, deletion, or destructive migration is introduced. Older clients ignore extra response fields. Rolling code back leaves the ignored preferences key on disk; remove that key from a private copy of preferences if an older editor rejects it. Existing database backups and tracking tables are preserved. New native fields are optional so legacy/sample JSON remains decodable.

Commands:

```sh
python3 -m unittest -v test_app.py test_prototype.py test_recruiter.py
npm ci
npx playwright install chromium
npm run test:browser
```

Cloud verification: 48 Python tests passed; both Playwright browser suites passed at a 390×844 viewport, including review, save, applied/interview stages, persisted notes, preferences, source controls, no mobile overflow and no JS errors. New tests cover missing facts, evidence removal, profile-dependent preparation, stale/unverified links, mismatched employer boards/requisitions/titles, scoped successful verification and redirects. Existing tests cover failures, duplicates and preserved tracking. CI now includes the new suite. CI execution on GitHub is not claimed.

Neither `xcodebuild` nor `swift` is installed here. No native compile, simulator test, device test or signing was performed. The browser checks validate the existing web workflow, not the new SwiftUI controls. First next step is an Xcode build and a synthetic résumé → live search → saved → applied device walkthrough.

Next priorities: authenticated per-user storage and authorization tests; general employer-resolution evidence with company/location/requisition comparisons; user-correctable inference workflow with a real provider and cost controls; replace legacy geography defaults and test a broader variety of profiles. This slice does not satisfy the entire commercial product vision.
