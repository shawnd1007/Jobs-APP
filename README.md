# Jobs App

Jobs is a personal job-search workspace. It brings employer listings, a reusable search profile, and application tracking together in a browser and an iPhone app so you can find a role, see why it fits, and keep track of what to do next.

## What Jobs does

- **Find roles.** Pull openings from employer boards such as Greenhouse, Lever, and Ashby. Browse the full collection or open **For You** to see ranked recommendations.
- **Personalize matching.** Import a résumé on iPhone, choose the roles and skills you want to match, and set location and pay preferences. Job details explain the score and identify details to verify.
- **Save searches.** Keep separate sets of criteria and review new matches in the alert inbox. The iPhone can notify you when it connects and finds unread matches.
- **Manage applications.** Save or pass on roles, apply on the employer’s site, and use **My Jobs** to track stages, notes, and follow-ups.
- **Request AI advice.** With OpenAI configured on the server, compare your profile with an individual posting to see relevant experience, gaps, and questions to verify.

## Try it

On iPhone, choose **Explore sample jobs** to try recommendations and application tracking offline with fictional listings. Connect to the Jobs server for live listings and searches. [iPhone setup guide](ios/README.md)

## Run locally

Install Python 3.13 and Docker Desktop, then run:

```sh
python3 setup_project.py
docker compose up -d
```

On Windows use `python` if that is your installed command. Open http://localhost:8084. The clean Compose file binds to loopback by default. A second service already using port 8084 must be stopped before using that port here.

This source copy starts empty: no personal profile, real jobs, application history or API key is bundled. Scheduled search, public web discovery and AI are initially off. Add an actual Greenhouse/Ashby/Lever employer board in Preferences and request a search. 

## Checks

```sh
python3 -m unittest -v test_app.py test_prototype.py
npm ci
npx playwright install chromium
PYTHON=python3 npm run test:browser
```

Node is only a development/test dependency. The runtime backend uses the Python standard library. On Windows set `$env:PYTHON='python'` before the npm browser command.

## Project scope

Jobs is a private-network prototype for one workspace. The Python server uses SQLite and serves the browser dashboard and iPhone app. Keep it on a trusted network because the API currently has no sign-in.

Read the [project guide](docs/COMPLETE-GUIDE.md) for architecture and workflows, the [development guide](CONTRIBUTING.md) for contributing, and the [verification notes](docs/VERIFICATION.md) for test coverage and platform limits.
