# Contributing to nvda-addon-testkit

Contributions are welcome — bug reports, feature suggestions, and PRs alike.

## Reporting a bug

Use the **Bug report** template at <https://github.com/ZirekHQ/nvda-addon-testkit/issues/new/choose>. It asks for the testkit version, NVDA channel, OS, and enough of a repro to run — fill in what you can, especially a minimal failing test or command.

## Suggesting a feature

Use the **Feature request** template. Describe the *problem* you're hitting, not just the API you imagine — that often surfaces a simpler fixture or a better name than the first idea.

## Development setup

```bash
pip install -e ".[dev]"
python tools/build_spy.py
```

`build_spy.py` packages `spy/` (the scriptable NVDA double) into the `.nvda-addon` the host-side tests install. Rerun it whenever you change anything under `spy/`.

## Running tests

```bash
pytest                       # host and spy unit tests -- any platform
pytest tests_e2e/ -v         # real NVDA -- Windows only
nvda-testkit doctor          # check this machine
```

| Tree | Exercises | Runs on |
| --- | --- | --- |
| `tests/` | the host-side library, against `tests/fake_nvda.py` | Linux + Windows |
| `tests_spy/` | `spy/`, the in-NVDA agent, against stubbed NVDA modules (`tests_spy/nvda_stubs.py`) | Linux + Windows |
| `tests_e2e/` | both halves together, against a real provisioned NVDA | Windows only |

`tests_e2e/` tests run serially — only one NVDA can own a desktop session, so `pytest-xdist` with more than one worker refuses to start rather than silently corrupting results.

## Linting

```bash
ruff check .
ruff format --check .
```

## Submitting a PR

Use the pull request template. Link the issue with `Closes #N` in the PR body where one exists.

- **Commit messages**: short imperative subject, optionally prefixed `fix:` / `feat:` / `ci:` / `chore:` / `docs:` when it clarifies the kind of change. Don't append the `(#NNNNN)` PR-number suffix — GitHub's squash-merge adds it automatically.
- **Branch naming**: `<type>/<slug>`, e.g. `fix/rpc-race`, `feature/braille-namespace`.
- **No `Co-Authored-By` trailers.**

## Cutting a release

Releases are tag-driven, not version-bumped by hand — `pyproject.toml` has no `version` field. The `hatch-vcs` build hook derives the package version from the git tag at build time.

1. Run `prepare-release.yml` (Actions tab → **Prepare release** → Run workflow). Leave `new_tag` blank to let it compute the next version from Conventional Commit subjects since the last tag (`scripts/next-version.sh`); pass a `vX.Y.Z` value there instead to override it. Check `dry_run` to only see the computed version without tagging or publishing anything.
2. The `release` environment gate requires a maintainer approval before anything happens — that's the human checkpoint, not the version computation.
3. Once approved, `release.yml` tags `main` at the resolved commit, force-moves the `v<major>` tag consumers pin (README and GitHub Marketplace listings use `@v1`), and publishes the GitHub Release with auto-generated notes.
4. That tag feeds `publish-python.yml`, which builds the sdist/wheel and uploads to PyPI via Trusted Publishing — no token to rotate.

### Why not fully automate this (conventional commits + semantic-release)?

The version bump itself *is* automated — computed from commit prefixes since the last tag. What's deliberately kept manual is the human approval gate before anything tags or publishes: pre-1.0 semver bumps (does this `feat:` deserve a minor, or does it actually break the fixture API?) are judgment calls worth a maintainer's eyes before they go to PyPI and the Marketplace. Worth revisiting if release volume ever makes that approval step the actual bottleneck.
