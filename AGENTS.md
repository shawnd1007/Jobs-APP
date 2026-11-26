# Project instructions

Read [the approved product vision](docs/PRODUCT-VISION.md) before planning changes. Jobs is intended to be a paid, secure, ad-free personal AI recruiter for job seekers. Shawn is the first daily tester. [The complete guide](docs/COMPLETE-GUIDE.md) describes the current single-workspace browser and iPhone prototype. Use the [roadmap](docs/NEXT-STEPS.md) and [verification record](docs/VERIFICATION.md) to distinguish goals, implementation, and observed results.

Keep employer listing facts, owner review decisions, application tracking, and AI advice separately owned. Preserve existing records, notes, settings, and Git history. Use one authoritative backend per live database.

Use fictional jobs and résumés in tests. Never operate on the owner's application database during automated tests. Keep configuration profiles, databases, credentials, screenshots, and migration archives out of Git. Do not enable paid provider calls merely to run tests. Run browser tests sequentially because they share QA port 18084. Treat macOS, hosted CI, physical devices, and paid provider execution as unverified until observed on those targets.

Follow the [existing GitHub workflow](docs/GITHUB-SETUP.md) when publishing. Continue the relevant feature branch and draft PR when one exists. Review the exact staged changes for private data and unrelated work. Verify the pushed SHA and its checks.
