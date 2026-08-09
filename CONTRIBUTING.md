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

1. Publish a GitHub Release from `main` with a `vX.Y.Z` tag (semver; pre-1.0 minor bumps may break the fixture API).
2. `.github/workflows/publish.yml` picks up the `release: published` event, builds the sdist/wheel, and uploads to PyPI via Trusted Publishing — no token to rotate.

No separate changelog file to update — Release Drafter maintains a draft release from merged PR titles/labels as you go; open the draft, set the tag, and publish it to trigger the step above.

### Why not fully automate this (conventional commits + semantic-release)?

Considered and deliberately skipped. PRs are squash-merged, so main's history is already one commit per PR — parsing commit prefixes to categorize a release would just be a stricter, easier-to-typo restatement of what PR labels already give Release Drafter for free. More importantly, auto-bumping the version and auto-publishing on merge removes the last human checkpoint before something goes to PyPI, and pre-1.0 semver bumps (does this `feat:` deserve a minor, or does it actually break the fixture API?) are judgment calls a bot applies too mechanically at this stage. Worth revisiting if release volume ever makes the manual tag-and-publish step the actual bottleneck.
