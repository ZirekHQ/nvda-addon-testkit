# nvda-addon-testkit

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
      - uses: zirekhq/nvda-addon-testkit/setup@v1
        with:
          nvda-channel: stable
      - run: pytest tests_e2e/ -v
```

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
