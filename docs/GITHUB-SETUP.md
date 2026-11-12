# Work on Jobs across machines

The private source repository is [shawnd1007/Jobs-APP](https://github.com/shawnd1007/Jobs-APP). The [approved product vision](PRODUCT-VISION.md) is the starting point for new work. The [README](../README.md) has the run and test commands.

## Get the right source

Authenticate with GitHub, then clone into a new directory for development.

```sh
git clone https://github.com/shawnd1007/Jobs-APP.git
cd Jobs-APP
git status --short --branch
git remote -v
git fetch origin
```

For existing work, check the draft PR's head and base. Follow the existing feature branch. For example, Build 9 is on `codex/stage-two-iphone-polish` in [draft PR #2](https://github.com/shawnd1007/Jobs-APP/pull/2). To work on it from a new clone, run `git switch --track origin/codex/stage-two-iphone-polish`. If the branch already exists locally, use `git switch codex/stage-two-iphone-polish` and inspect the differences before pulling.

For an independent change, start from the agreed base. The repository uses `main` for integration and `codex/<topic>` feature branches for app work. Use a draft pull request into `main` for review. For source from a ZIP or a live folder without history, keep that folder and copy only the reviewed source changes into a clone with the correct branch history.

## Publish a reviewed change

1. Inspect the branch, working tree, and remote. Keep unrelated changes in place or use a separate checkout.
2. Stage only the intended source, tests, and documentation. Inspect `git diff --cached --stat`, `git diff --cached`, and `git diff --cached --check`.
3. Run the relevant checks with fictional data. Commit with a clear explanation of the change and verification.
4. Push the feature branch with `git push -u origin HEAD`. Open or update the draft PR. Confirm the remote SHA and check GitHub Actions for that SHA. Merge only when explicitly requested.

Keep local configuration, résumé and application data, secrets, screenshots, build outputs, and migration archives in the private workspace. Use a separate private backup for the database. GitHub author identity can use your GitHub no-reply address. Keep credentials out of commit metadata and source.
