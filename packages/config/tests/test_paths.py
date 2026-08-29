"""Path resolution — a wrong repo root silently relocates the kill switch."""

from tsys.config import REPO_ROOT, settings


def test_repo_root_is_the_repository_not_the_packages_dir():
    assert REPO_ROOT.name != "packages"
    assert (REPO_ROOT / "packages").is_dir()
    assert (REPO_ROOT / "pyproject.toml").exists()


def test_data_dir_sits_at_the_repo_root():
    assert settings.base.data_dir.parent == REPO_ROOT


def test_kill_switch_is_not_nested_under_packages():
    """This regressed once: the switch resolved to packages/data/KILL, so the
    dashboard and the executor were checking two different files."""
    assert settings.risk.kill_switch_file == REPO_ROOT / "data" / "KILL"


def test_tv_cli_path_points_at_a_real_file():
    assert settings.tradingview.cli_path.exists(), settings.tradingview.cli_path
