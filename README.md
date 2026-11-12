# Jobs App

Jobs is being built as a paid, secure, ad-free personal AI recruiter. It should understand a job seeker's experience and goals, find current openings on employer sites, explain the fit, help prepare a truthful application, and replace the application spreadsheet. Shawn is the first daily tester. Other job seekers are the intended customers. [Approved product vision](docs/PRODUCT-VISION.md)

Build 9 is a local-first, single-workspace prototype with a browser dashboard and a native iPhone app. The Python service owns the shared SQLite database and runs discovery. The iPhone connects to that service and can reopen its last synced copy offline. Run the service on a trusted network because the prototype has no sign-in.

## What works in Build 9

- **Find roles.** Pull openings from Greenhouse, Lever, Ashby, SmartRecruiters, and employer-enabled Personio boards. Searches show progress and keep results from sources that respond. Browse the full collection or open **For You** to see ranked recommendations.
- **Personalize matching.** Import a résumé on iPhone, select supported skills and experience, and set role, location and pay preferences. Job details explain the score and identify details to verify.
- **Save searches.** Keep separate sets of criteria and review new matches in the alert inbox. Jobs checks the exact employer posting before it alerts. Local iPhone notification delivery still needs a signed-device check.
- **Manage applications.** Save or pass on roles, apply on the employer’s site, and use **My Jobs** to track stages, notes, and follow-ups. Add applications you found elsewhere, even if the posting link is gone.
- **Read offline.** Open the last synced workspace on iPhone to review real listings and application history when the Mac is unavailable.
- **Request AI advice.** The optional OpenAI integration compares your profile with a posting. Build 9 checks use mocked providers. Paid execution and costs need separate validation.

## Try it

On iPhone, choose **Explore sample jobs** to try recommendations and application tracking offline with fictional listings. Connect to the Jobs server for live listings and searches. [iPhone setup guide](ios/README.md)

## Run locally

Use Python 3.13 and Docker Compose from a [clean checkout](docs/GITHUB-SETUP.md).

```sh
python3 setup_project.py
docker compose up -d
```

On Windows use `python` if that is your installed command. Open http://localhost:8084. The clean Compose file binds to loopback by default. A second service already using port 8084 must be stopped before using that port here.

This source copy starts with an empty workspace. Scheduled search, public web discovery and AI are initially off. Add an employer board in Preferences and request a search.

For a native Python backend, run `JOBS_BIND_HOST=127.0.0.1 python3 app.py` after setup. On Windows PowerShell, set `$env:JOBS_BIND_HOST = '127.0.0.1'` before running `python app.py`. Stop the other backend first if port 8084 is already in use.

## Checks

Use a separate source checkout with an empty local setup and fictional fixtures. Run the two browser checks sequentially through the package script.

```sh
python3 setup_project.py
python3 -m unittest -v test_app.py test_prototype.py
npm ci
npx playwright install chromium
PYTHON=python3 npm run test:browser
```

Node is only a development/test dependency. The runtime backend uses the Python standard library. On Windows set `$env:PYTHON='python'` before the npm browser command.

## Project docs

| Where to start | What it covers |
| --- | --- |
| [Product vision](docs/PRODUCT-VISION.md) | The approved product and business goals |
| [Project guide](docs/COMPLETE-GUIDE.md) | Current architecture, data ownership, setup, API, and recovery |
| [iPhone guide](ios/README.md) | Xcode setup, offline reading, résumé import, and alerts |
| [Build checklist](docs/STAGE-TWO.md) and [verification](docs/VERIFICATION.md) | What shipped in Build 9 and what was tested |
| [Roadmap](docs/NEXT-STEPS.md) | The next work toward a dependable local app and a secure service |
| [Contributing](CONTRIBUTING.md) and [GitHub workflow](docs/GITHUB-SETUP.md) | Safe tests, branch conventions, and publication |
