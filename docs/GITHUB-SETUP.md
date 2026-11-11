# Your first GitHub setup

Use this clean source folder, not the personal migration archive. Start with a private repository while reviewing the project.

The prepared local folder may already contain a Git repository and staged files. Run `git status` first. ZIP source exports exclude `.git`; initialize an extracted archive with `git init -b main`.

```sh
git status
git add .
git diff --cached --stat
git diff --cached
git commit -m "Prepare personal Jobs prototype"
```

If Git needs an author identity, configure your chosen name and email/no-reply address locally. No identity is invented by the packaging script.

Create an empty repository in your GitHub account. Leave its README/license/ignore initialization unchecked because this folder already has starting files. Substitute your own remote URL:

```sh
git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-REPOSITORY.git
git remote -v
git push -u origin main
```

These steps follow [GitHub's official local-repository instructions](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github). Authenticate using your chosen GitHub tool. GitHub Desktop is an alternative if you prefer reviewing changes visually.

Nothing has been pushed by preparing this package. No real API key, application database, personal experience profile or original job directory belongs in this repository. `.gitignore` protects future additions; it does not remove a file already committed.

No open-source license has been selected. Decide that separately before advertising an open-source release. GitHub stores source history; keep private database backups separately.
