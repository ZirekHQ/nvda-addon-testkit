# nvda-addon-testkit

[Project board](https://github.com/orgs/ZirekHQ/projects/1) — live roadmap and status for this repo's issues.

End-to-end testing for NVDA add-ons, against a real NVDA, in CI.

Your add-on's logic can be unit-tested with stubs. What cannot be stubbed is
whether it installs, registers, and behaves inside NVDA itself. This kit
provisions a disposable portable NVDA, installs your add-on into it, and lets
pytest drive it.

```python
def test_my_addon_announces_itself(nvda, addon_under_test):
    before = nvda.speech.index()
    nvda.keys.press("NVDA+shift+m")
    assert "my add-on is ready" in nvda.speech.wait_for("ready", timeout=10, since=before).text
    nvda.log.assert_no_errors()
```

The same test reads as plain steps with the (experimental) DSL:

```python
def test_my_addon_announces_itself(nvda, addon_under_test):
    nvda.press("NVDA+shift+m")
    nvda.should_hear("my add-on is ready")
    nvda.should_have_no_errors()
```

## Install

```bash
pip install nvda-addon-testkit
```

## Configure

```toml
[tool.nvda-testkit]
addon-bundle = "dist/my-addon-*.nvda-addon"
nvda-channel = "stable"
```

## Run in GitHub Actions

```yaml
jobs:
  e2e:
    runs-on: windows-2025
    steps:
      - uses: actions/checkout@v5
      - uses: zirekhq/nvda-addon-testkit@v1
        with:
          nvda-channel: stable
      - run: pytest tests_e2e/ -v
```

The action is OS-agnostic — pick whichever Windows runner matches what
your users run. This repository's e2e test suite runs on both `windows-2025`
and `windows-2022` (the latter for Windows 10 22H2, including builds
still on Extended Security Updates).

## What you get

| Fixture | What it gives you |
|---|---|
| `nvda` | a connected client, reset between tests |
| `addon_bundle` | the path to your built `.nvda-addon` |
| `addon_under_test` | that bundle, installed and enabled, NVDA restarted |

| Namespace | Use it for |
|---|---|
| `nvda.speech` | what NVDA asked to say, and waiting for it |
| `nvda.braille` | the raw text sent to the braille display |
| `nvda.keys` | sending gestures through NVDA's own input pipeline |
| `nvda.config` | reading and writing NVDA's configuration |
| `nvda.log` | structured log records, and `assert_no_errors()` |
| `nvda.addons` | two-phase install, remove, and state |

`nvda.eval()` runs a single expression inside NVDA; `nvda.exec()` runs a
full multi-statement scenario and returns whatever it binds to
`__result__`. Both need `--nvda-allow-eval`. A bad scenario raises
`ScenarioSyntaxError`, so catching bare `except Exception: pass` around
either call still swallows it — catch the types you expect instead.

`nvda.restart_harness()` kills and relaunches the NVDA process — use it to
finish a two-phase add-on install or reset to a clean process. It does not
exercise NVDA's own restart logic. For that, use `nvda.restart_nvda()`,
which triggers NVDA's real `core.restart()` and waits for the replacement
process — needs `--nvda-allow-eval`, since it is built on `nvda.eval()`.

A real `wx.Dialog.ShowModal()` never returns control to any of the above —
NVDA's main-thread queue doesn't drain while one is up. Open it with
`nvda.exec_nowait()` instead of `exec()` (queues the scenario without
waiting for it to finish), then close it with `nvda.simulate_modal(gesture,
timeout=10.0)`, which sends real injected keyboard input once our process
takes the foreground.

## Requirements

Windows to run the tests. NVDA is downloaded automatically — you do not need
one installed, and nothing touches an NVDA you already have.

Tests run serially: only one NVDA can own a desktop session, so pytest-xdist
with more than one worker is refused rather than silently producing nonsense.

## Developing the kit itself

The host side is fully testable on Linux against a scriptable double:

```bash
pip install -e ".[dev]"
python tools/build_spy.py
pytest                       # host and spy unit tests, any platform
pytest tests_e2e/ -v         # real NVDA, Windows only
nvda-testkit doctor          # check this machine
```

## Licence

GPL-2.0-or-later.

---

## 💝 Support This Project

If this repository saves you time and effort, please consider supporting it!

- ⭐ [Star on GitHub](https://github.com/ZirekHQ/nvda-addon-testkit)
- 🐦 [Share on Twitter](https://twitter.com/intent/tweet?text=nvda-addon-testkit%20-%20real%20end-to-end%20testing%20for%20NVDA%20add-ons&url=https%3A%2F%2Fgithub.com%2FZirekHQ%2Fnvda-addon-testkit)
- 💖 [Support on Open Collective](https://opencollective.com/zirek)
