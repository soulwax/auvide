# PyPI Trusted Publishing

`.github/workflows/publish-pypi.yml` is manual-only until the release workflow
owns publication. It builds and checks distributions before a separate,
protected publishing job exchanges its GitHub Actions OIDC identity for a
short-lived index token. No PyPI API token or repository secret is used.

## One-Time Configuration

Create the following protected GitHub environments before the first run:

- `testpypi` for package rehearsal. Configure required reviewers as desired.
- `pypi` for production publication. Require maintainer approval.

For each matching index project, add a GitHub Actions trusted publisher with:

```text
Owner: soulwax
Repository: auvide
Workflow filename: publish-pypi.yml
Environment: testpypi or pypi
```

Use TestPyPI first. The package name must be available on the selected index,
or the initial trusted-publisher configuration must be created as a pending
publisher through that index's UI.

## Publishing A Version

1. Update `VERSION`, use `scripts/sync_version.py --set X.Y.Z`, and add the
   release notes to `CHANGELOG.md`.
2. Run `python scripts/sync_version.py --check` and the engine validation
   suite locally.
3. Create and push the signed release commit and its `vX.Y.Z` tag.
4. From GitHub Actions, run **Publish PyPI Package** on that tag or its release
   commit. Select `testpypi` for rehearsal, then `pypi` after verification.
5. Confirm the environment approval identifies the intended commit and that
   the published version matches `VERSION`.

The workflow requests `id-token: write` only in the publishing job. Keep the
workflow filename and environment names stable after registering trusted
publishers; changing either requires updating the index configuration.
