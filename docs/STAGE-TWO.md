# Stage Two · iPhone product pass

The iPhone app opens with a clear path into the product. Choose **Explore sample jobs** to try it immediately, or **Connect to your Mac** to open your real workspace. The original [product audit](PRODUCT-AUDIT.md) and [job-board research](PERSONALIZED-JOB-BOARD.md) informed the design. The welcome screen offers an immediate way to try the app, with native navigation for moving between discovery and tracking. [Apple onboarding guidance](https://developer.apple.com/design/human-interface-guidelines/onboarding) · [Apple tab bar guidance](https://developer.apple.com/design/human-interface-guidelines/tab-bars)

## What changed

- **Welcome** introduces the app and provides a sample workspace even if a previously configured Mac is unreachable. Connection settings and retry remain available.
- **For You** puts role, employer, pay, location, match score and evidence in a consistent order. Top Matches and Needs Review keep listings with missing information visible. Save and Pass are separate from opening a card, and Undo restores the last action.
- **Browse** searches across roles, employers and locations in the retained list. Best Matches is available as a quick view. **My Jobs** keeps saved roles and application stages easy to reach.
- **Job Details** uses the same card hierarchy as the feed, expands on matched skills and employer evidence, and gives the employer link a prominent action when available.
- **Alerts** starts with the match inbox and saved searches, followed by employer search controls. Settings continues to hold the search profile, résumé import, employer boards and Mac connection.
- The iPhone home-screen name is **Jobs**. The interface uses an adaptive pine-and-mint palette, scalable serif headlines, native controls, and layouts that can stack when text needs more room.

## Sample and connected workspaces

The sample uses four fictional listings with example scores and no employer URLs. Save, Pass, Undo and application edits work in memory. Leaving the sample workspace or ending the app process resets the session. The sample performs no employer searches, AI calls, notifications or writes to the Mac. Connected mode continues to use the existing versioned tracking and review endpoints. The live search, résumé matching and alert workflows require the Mac connection described in the [iPhone guide](../ios/README.md).

## Verification

- Xcode built the iPhone simulator app and an unsigned device release.
- The iPhone 17 simulator on iOS 27.2 passed an isolated Xcode UI test covering first launch, Top Matches and Needs Review, Save and Pass with Undo, Browse navigation, My Jobs, marking a sample application Applied, and leaving the sample.
- All 37 Python regression tests passed using temporary data.
- The unsigned IPA requires signing before normal installation on a physical iPhone. Stage Two physical-device installation, connected-mode alerts, and large-text and dark-mode visual review are pending.
