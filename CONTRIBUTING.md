# Working on the prototype

1. Run `python3 setup_project.py` once. It creates ignored local files and never overwrites existing ones.
2. Use a separate development database from your authoritative personal installation.
3. Make a small branch and a focused change. Preserve the separation of listings, human reviews, tracking and AI advice.
4. Run relevant Python checks and the isolated browser tests after UI changes. Browser suites share port 18084 and must run sequentially.
5. Inspect `git diff` and staged files before committing. Never stage local configuration, databases, keys, personal research or private migration archives.
6. Explain the problem, resulting behavior and verification in the commit or pull request.

Python 3.13 is the baseline. Node 22+ and the lockfile-pinned Playwright version are used only for browser checks. On Windows these tests currently launch Microsoft Edge; on other platforms they launch the installed Playwright Chromium.

The CI configuration targets Linux. A committed workflow is not a passing hosted CI run until GitHub Actions has actually executed it. Test macOS on the target machine before claiming support.
