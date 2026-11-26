# Contributing to Jobs

Start with the [approved product vision](docs/PRODUCT-VISION.md), then check the [roadmap](docs/NEXT-STEPS.md) and [current verification](docs/VERIFICATION.md). A feature should strengthen the flow from understanding the person through finding, verifying, applying to, and tracking a real opportunity.

- Use a separate development checkout and database. Run `python3 setup_project.py` once to create ignored local configuration and an empty seed. Use the [README](README.md) to run the backend and the [iPhone guide](ios/README.md) to run Xcode.
- Preserve the boundaries in the [architecture guide](docs/COMPLETE-GUIDE.md#3-the-architecture-in-plain-english). Source refresh owns employer facts. The user owns review decisions, tracking and profile choices. AI advice stays separate.
- Use fictional fixtures and temporary databases for tests. Provider requests are mocked in AI tests. The two browser checks share port 18084 and run sequentially through `npm run test:browser`. Python 3.13 is the baseline, and Node 22 or newer is used for browser tests. Windows uses Edge. macOS and Linux use Playwright Chromium.
- Follow the [feature-branch and draft PR workflow](docs/GITHUB-SETUP.md). Review the exact staged diff before publishing. Include the problem, resulting behavior, observed checks, and remaining limits in the PR.
