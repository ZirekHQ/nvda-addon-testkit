"""nvda-testkit command line: provision and doctor."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import __version__
from .download import default_cache_dir, ensure_launcher
from .errors import TestkitError
from .portable import create_portable
from .resolve import CHANNELS, resolve_launcher
from .spybundle import spy_bundle_path


def _provision(args) -> int:
    info = resolve_launcher(args.channel)
    print(f"channel:     {info.channel}")
    print(f"version:     {info.version}")
    print(f"url:         {info.url}")
    print(f"sha1:        {info.sha1 or '(none published)'}")
    launcher = ensure_launcher(info)
    print(f"launcher:    {launcher}")
    if args.portable_path:
        portable = create_portable(launcher, Path(args.portable_path))
        print(f"portable:    {portable.root}")
    return 0


def _doctor(args) -> int:
    failures = 0
    print(f"nvda-addon-testkit {__version__}")
    print(f"platform:      {sys.platform}")
    if sys.platform != "win32":
        print("  ! Driving a real NVDA needs Windows. Use --nvda-fake for host-side work.")

    bundle = spy_bundle_path()
    if bundle.is_file():
        print(f"spy bundle:    {bundle} ({bundle.stat().st_size} bytes)")
    else:
        print(f"spy bundle:    MISSING at {bundle} -- run: python tools/build_spy.py")
        failures += 1

    cache = default_cache_dir()
    cached = sorted(cache.glob("*.exe")) if cache.is_dir() else []
    print(f"launcher cache: {cache} ({len(cached)} cached)")

    for channel in CHANNELS:
        try:
            info = resolve_launcher(channel)
            print(f"  {channel:<7} -> {info.version}")
        except TestkitError as error:
            print(f"  {channel:<7} -> FAILED: {error}")
            failures += 1

    if args.full and sys.platform == "win32":
        info = resolve_launcher("stable")
        launcher = ensure_launcher(info)
        with tempfile.TemporaryDirectory(prefix="nvda-testkit-doctor-") as workdir:
            portable = create_portable(launcher, Path(workdir) / "nvda")
            print(f"portable copy: created at {portable.root}")

    print("OK" if not failures else f"{failures} problem(s) found")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nvda-testkit")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    provision = subparsers.add_parser("provision", help="resolve and download an NVDA launcher")
    provision.add_argument("--channel", default="stable")
    provision.add_argument("--portable-path", default=None, help="also create a portable copy here")
    provision.set_defaults(handler=_provision)

    doctor = subparsers.add_parser("doctor", help="check this machine can run the kit")
    doctor.add_argument("--full", action="store_true", help="also create a real portable copy")
    doctor.set_defaults(handler=_doctor)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except TestkitError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
