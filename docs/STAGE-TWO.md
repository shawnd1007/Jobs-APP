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
