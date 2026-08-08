import pytest

from nvda_testkit.namespaces.addons import AddonInfo, AddonsNamespace, AddonState
from nvda_testkit.process import NvdaProcess
from nvda_testkit.rpcclient import RpcClient


@pytest.fixture
def addons(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv, fake_nvda.out_dir, token=fake_nvda.token, env=fake_nvda.env, quit_via="rpc"
    )
    handshake = proc.start(timeout=20)
    rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token)
    yield AddonsNamespace(rpc), rpc
    rpc.close()
    proc.kill()


def test_an_unknown_addon_is_not_installed(addons):
    namespace, _ = addons
    assert namespace.state("nothing-here") is AddonState.NOT_INSTALLED


def test_install_returns_a_pending_addon_info(addons):
    namespace, _ = addons
    info = namespace.install("/tmp/demo.nvda-addon")
    assert isinstance(info, AddonInfo)
    assert info.name == "demo-addon"
    assert info.state is AddonState.PENDING_INSTALL


def test_install_does_not_secretly_restart(addons):
    namespace, _ = addons
    namespace.install("/tmp/demo.nvda-addon")
    assert namespace.state("demo-addon") is AddonState.PENDING_INSTALL, (
        "install() must leave the add-on pending; completing it is the caller's restart"
    )


def test_list_parses_into_addon_infos(addons):
    namespace, _ = addons
    namespace.install("/tmp/demo.nvda-addon")
    (info,) = namespace.list()
    assert info.name == "demo-addon"
    assert info.version == "1.0.0"


def test_states_compare_as_strings_too(addons):
    namespace, _ = addons
    namespace.install("/tmp/demo.nvda-addon")
    assert namespace.state("demo-addon") == "PENDING_INSTALL"
