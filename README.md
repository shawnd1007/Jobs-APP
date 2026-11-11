# Jobs workspace

A personal job-discovery, review and application-tracking prototype built with Python, SQLite and browser JavaScript. Employer facts, human decisions and optional AI advice are stored separately.

## Start here

Read the [complete plain-English guide](docs/COMPLETE-GUIDE.md), [GitHub setup](docs/GITHUB-SETUP.md), and [development instructions](CONTRIBUTING.md).

## Try the iPhone app

Open the Xcode project in `ios/`, run the JobsApp scheme, and choose **Explore sample jobs** to try the feed and tracking without a server. See the [iPhone guide](ios/README.md) and [Stage Two notes](docs/STAGE-TWO.md).

## Run locally

Install Python 3.13 and Docker Desktop, then run:

```sh
python3 setup_project.py
docker compose up -d
```

On Windows use `python` if that is your installed command. Open http://localhost:8084. The clean Compose file binds to loopback by default. A second service already using port 8084 must be stopped before using that port here.

This source copy starts empty: no personal profile, real jobs, application history or API key is bundled. Scheduled search, public web discovery and AI are initially off. Add an actual Greenhouse/Ashby/Lever employer board in Preferences and request a search. The fictional fixtures exist only for tests.

## What it implements

- Direct employer feed adapters and bounded best-effort discovery.
- Explicit location/pay checks, configurable title/skill rules and explanations.
- iPhone For You recommendations with match scores, Browse across retained listings, and My Jobs for application tracking.
- Résumé import with on-device preview, editable skills, and saved searches with a match inbox. iPhone alerts appear when the app connects and sees unread matches.
- Human review buckets, application notes/dates and conflict detection.
- Employer health and pause/resume controls.
- Requested, cached OpenAI career advice with daily attempt limits; disabled by default.
- Backups, search reports, isolated unit/browser checks and a versioned dashboard API.

Firecrawl is not required. Dynamic employer pages may still need manual review. No applications are submitted automatically.

## Checks

```sh
python3 -m unittest -v test_app.py test_prototype.py
npm ci
npx playwright install chromium
PYTHON=python3 npm run test:browser
```

Node is only a development/test dependency. The runtime backend uses the Python standard library. On Windows set `$env:PYTHON='python'` before the npm browser command.

## Scope

This is a private-network, single-workspace prototype. The API has no user authentication; do not expose it publicly. Some geography logic remains specific to Florida/Georgia and the original local-office rules. AI provider responses are mocked in tests; account-specific paid execution remains to be validated. The standard Docker setup on macOS remains unverified. The [native iPhone workspace](ios/README.md) connects to this backend for searches, review, tracking, employer boards, preferences and optional AI advice. The iPhone guide includes a Mac-only Python startup command and private-network setup.

Developed with AI assistance. See [portfolio notes](docs/PORTFOLIO.md) for what can be demonstrated and what remains future work. No open-source license has been selected for this preparation copy.

See [verification notes](docs/VERIFICATION.md) for observed checks and remaining platform limits.
