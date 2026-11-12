# Stage Two · Build 9 checklist

The [approved product vision](PRODUCT-VISION.md) describes the product we are building. This checklist records Build 9 of the private, local-first app. See the [verification record](VERIFICATION.md) for observed checks and the [roadmap](NEXT-STEPS.md) for prioritized work.

The iPhone app opens with a clear path into the product. Choose **Explore sample jobs** to try it immediately, or **Connect to your Mac** to open your real workspace. The original [product audit](PRODUCT-AUDIT.md) and [job-board research](PERSONALIZED-JOB-BOARD.md) informed the design. The welcome screen offers an immediate way to try the app, with native navigation for moving between discovery and tracking. [Apple onboarding guidance](https://developer.apple.com/design/human-interface-guidelines/onboarding) · [Apple tab bar guidance](https://developer.apple.com/design/human-interface-guidelines/tab-bars)

## What changed

- **Welcome** introduces the app and provides a sample workspace even if a previously configured Mac is unreachable. Connection settings and retry remain available.
- **For You** puts role, employer, pay, location, match score and evidence in a consistent order. Top Matches and Needs Review keep listings with missing information visible. Save and Pass are separate from opening a card, and Undo restores the last action.
- **Browse** searches across roles, employers and locations in the retained list. The Sort menu includes Best Match and shows match scores in that view. **My Jobs** shows counts by application stage and puts due and overdue follow-ups at the top of the screen. Each tracked role belongs to one stage at a time.
- **Job Details** uses the same card hierarchy as the feed, expands on matched skills and employer evidence, and gives the employer link a prominent action when available.
- **Alerts** starts with the match inbox and saved searches, followed by employer search controls. Settings continues to hold the search profile, résumé import, employer boards and Mac connection.
- The iPhone home-screen name is **Jobs**. The interface uses an adaptive pine-and-mint palette, scalable serif headlines, native controls, and layouts that can stack when text needs more room.

## Sample and connected workspaces

The sample uses 16 fictional listings across several industries, with example applications in Applied and Interviews. A searchable skill catalog is available in the sample profile, connected profile, and saved searches. Sample skills and a pay preset update For You locally. Save, Pass, Undo and application edits work offline. Sample changes persist locally between launches. A confirmed reset in sample Settings clears them. The sample performs no employer searches, AI calls, notifications or writes to the Mac. Connected mode continues to use the existing versioned tracking and review endpoints. The live search, résumé matching and alert workflows require the Mac connection described in the [iPhone guide](../ios/README.md).

## Earlier Stage Two checks

- Xcode built the iPhone simulator app and an unsigned device release.
- The iPhone 17 simulator on iOS 27.2 passed an isolated Xcode UI test covering first launch, Top Matches and Needs Review, Save and Pass with Undo, Browse navigation, My Jobs, marking a sample application Applied, and leaving the sample.
- A second simulator test set a follow-up, moved a role to Applied, relaunched the app, checked that the role was out of Saved and still due, then confirmed that reset cleared the follow-up.
- All 37 Python regression tests passed using temporary data.
- The unsigned IPA requires signing before normal installation on a physical iPhone. Stage Two physical-device installation, connected-mode alerts, and large-text and dark-mode visual review are pending.

## Build 9 and the original brief

| Brief sections | State |
| --- | --- |
| 1, 5, 11 and 14 · Existing dashboard, tracking and reliability | The iPhone can reopen the last synced workspace without the Mac. An interrupted save keeps the open form and reconnects before a retry. An invalid server address leaves the existing connection intact. |
| 2 and 7 · Profile and fit | The résumé preview stays on the iPhone. Selected skills and explicitly added experience can be saved to the search profile. The matching engine can use that experience to identify relevant duties. |
| 3, 4, 6, 8, 9, 10 and 15 · Discovery, evidence and reports | The Mac runs the daily pipeline. Build 8 verified coverage across 29 employer boards, exact-requisition tracking and daily reports. Broader Workday board coverage and more dynamic application-form checks remain open. |
| 12 and 13 · Historical data | Existing application tracking is preserved. The CSV importer is ready to preview confirmed history. Importing additional historical records needs the original tracker or another export. |

The connected workspace remains a private-network product. Public deployment needs sign-in and workspace isolation. The physical iPhone alert path still needs a signed-device test.

Build 9 passed 49 backend tests, both sequential browser checks, and an Xcode device build. On the iPhone simulator, an unreachable replacement address preserved the original connection. A dropped connection preserved a follow-up draft, a retry saved it, and a cold offline launch reopened the application with its existing status and notes. A separate simulator test supplied a fictional PDF to the import handler, selected Excel, saved the experience, verified the posting duty evidence, and confirmed that repeating the passage did not duplicate it. The Files picker opened during testing. Document selection through the system picker remains unverified for build 9.

## Matching follow-up

Employer descriptions retain their headings and bullets. The app ranks and displays distinct duties that mention selected profile skills. This helps surface adjacent titles for review and keeps qualifications and repeated keyword mentions from inflating duty evidence. A fictional end-to-end search test verifies that an adjacent role with two distinct duties outranks a title-only match and that a weak individual employer posting stays out of discovery. A bounded request to the public Lever API verified labeled section handling on one posting. [How matching works](COMPLETE-GUIDE.md#7-how-matching-and-verification-work) · [Lever Posting API](https://github.com/lever/postings-api)

Browse now separates **Filter listings** from **Find New Jobs**. The first narrows the current list. The second leads to the Mac employer search, and the sample offers connection settings instead. Both workflows passed on an iPhone 18 Pro simulator with fictional records. The checkpoint also passed 53 backend tests, both browser checks, and an Xcode release build. [Simulator test setup](../ios/README.md#test-filtering-and-discovery-on-a-simulator)

## Search progress and Personio

Find New Jobs now shows its stage, source and progress. Source checks have deadlines; a partial run keeps the results it could verify and lets the user retry. The Personio adapter checks the public XML feed and the exact requisition page independently. A bounded public check verified an exact AND-E posting page and correctly flagged a separate feed result whose direct page returned 404. Neither check established an accessible application form. No employer boards were added to the owner’s preferences during these checks.


## Track an application found elsewhere

The connected iPhone app and browser can add an application with a title, employer and status. A link, location, notes and dates are optional. The record uses the existing stages and follow-up views. Duplicate checks protect existing records. Jobs preserves owner-entered provenance until it finds and saves the exact employer posting. An exact match keeps the application history on the same record.


## Direct posting checks for alerts

Jobs checks the requisition and page title before sending a saved-search alert. A timeout or mismatch leaves the listing in review. A later successful check uses the current search criteria, preserves the same tracking record and sends each matching alert once. The browser and iPhone distinguish checked and unverified posting links. Application form evidence stays separate.


## Application Prep

The web and connected iPhone job details include a worksheet that pairs employer duties with examples from the saved Search Profile. Users can add their own excerpts to a draft, edit them and save it per job. Skills without a usable work example appear with questions to check. Draft writes use a version so retries and edits on two devices preserve the owner’s text. The worksheet works without a paid AI provider.


## Keep distinct employer openings separate

Jobs retains requisition parameters in employer page URLs and no longer merges openings by employer, title and location. Search deduplicates tracking links to the same posting. Older keys upgrade in place when the retained URL is consistent. Ambiguous records stay in review with their original tracking and preparation drafts.


## Apply work arrangement preferences to employer evidence

Jobs carries employer-published remote, hybrid and on-site values through search, saved alerts and listing details. A missing or conflicting value stays in review when a work arrangement is required. On refresh, a removed employer value does not leave an obsolete label. Existing application notes and alert history stay with the job.


## Apply the same salary policy in matching and approval

The selected salary policy now governs discovery, Top Matches and manual approval. A published lower bound below the target blocks approval when the entire range must meet it. If the selected policy needs a bound the employer has not published, pay stays in review. A single published annual USD amount can match a saved search. Preference changes preserve existing approvals, notes and drafts.

The salary checkpoint passed 75 Python tests and both sequential browser suites on macOS. The iPhone client passed four UI tests on a separate iPhone 18 Pro simulator with fictional data, and Xcode built an unsigned device release. Hosted checks are tracked on draft PR #2. A signed physical-device test and provider execution remain open.
