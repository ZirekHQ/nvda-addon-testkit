"""Assemble a running NVDA from settings.

Two paths: the real one, which needs Windows, and the FakeNvda one, which is
how the kit's own tests and a Linux developer exercise everything above the
transport.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from .download import ensure_launcher
from .errors import UnsupportedPlatformError
from .portable import create_portable, extract_addon
from .process import NvdaProcess, new_token, nvda_argv
from .resolve import resolve_launcher
from .rpcclient import RpcClient
from .settings import TestkitSettings
from .spybundle import require_spy_bundle

SPY_ADDON_DIRNAME = "nvda-testkit-spy"


class Provisioned:
    """A running NVDA plus everything needed to tear it down."""

    def __init__(self, process: NvdaProcess, rpc: RpcClient, workdir: Path, keep: bool) -> None:
        self.process = process
        self.rpc = rpc
        self.workdir = workdir
        self.keep = keep
        self.current_rpc: Callable[[], RpcClient] = lambda: self.rpc

    def teardown(self) -> None:
        try:
            self.current_rpc().close()
        finally:
            try:
                self.process.quit(timeout=30)
            finally:
                if not self.keep:
                    shutil.rmtree(self.workdir, ignore_errors=True)


def _start(process: NvdaProcess, settings: TestkitSettings, timeout: float) -> RpcClient:
    handshake = process.start(timeout=timeout)
    return RpcClient.from_handshake(
        handshake, token=process.token, timeout_scale=settings.timeout_scale
    )


def provision_fake(settings: TestkitSettings, fake_script: Path) -> Provisioned:
    workdir = Path(tempfile.mkdtemp(prefix="nvda-testkit-fake-"))
    succeeded = False
    try:
        out_dir = workdir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        process = NvdaProcess(
            [sys.executable, str(fake_script)],
            out_dir,
            token=new_token(),
            quit_via="rpc",
            timeout_scale=settings.timeout_scale,
        )
        try:
            rpc = _start(process, settings, timeout=60)
        except BaseException:
            process.kill()
            raise
        succeeded = True
        return Provisioned(process, rpc, workdir, keep=settings.keep_portable)
    finally:
        if not succeeded:
            shutil.rmtree(workdir, ignore_errors=True)


def provision(settings: TestkitSettings) -> Provisioned:
    if sys.platform != "win32":
        raise UnsupportedPlatformError(
            "Driving a real NVDA needs Windows. On Linux, point the plugin at the "
            "FakeNvda double with --nvda-fake to exercise everything above the transport."
        )
    info = resolve_launcher(settings.channel)
    launcher = ensure_launcher(info, settings.cache_dir)

    workdir = Path(tempfile.mkdtemp(prefix="nvda-testkit-"))
    succeeded = False
    try:
        out_dir = settings.out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        portable = create_portable(launcher, workdir / "nvda")
        extract_addon(require_spy_bundle(), portable.addons_dir / SPY_ADDON_DIRNAME)

        log_file = out_dir / "nvda.log"
        process = NvdaProcess(
            nvda_argv(portable, log_file),
            out_dir,
            token=new_token(),
            log_file=log_file,
            quit_via="exe",
            timeout_scale=settings.timeout_scale,
        )
        try:
            rpc = _start(process, settings, timeout=120)
        except BaseException:
            process.kill()
            raise
        succeeded = True
        return Provisioned(process, rpc, workdir, keep=settings.keep_portable)
    finally:
        if not succeeded:
            shutil.rmtree(workdir, ignore_errors=True)
