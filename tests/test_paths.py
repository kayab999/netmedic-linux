from pathlib import Path

from netmedic.paths import resolve_app_icon_path, resolve_manual_path


def test_resolve_app_icon_path_finds_repo_asset():
    path = resolve_app_icon_path()
    assert path is not None
    assert path.name == "netmedic.png"
    assert path.is_file()


def test_resolve_app_icon_path_repo_layout(tmp_path, monkeypatch):
    repo_root = tmp_path / "netmedic_linux"
    repo_icon = repo_root / "assets" / "netmedic.png"
    repo_icon.parent.mkdir(parents=True)
    repo_icon.write_bytes(b"png")

    fake_module = repo_root / "netmedic" / "netmedic" / "paths.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.touch()

    monkeypatch.setattr("netmedic.paths.__file__", str(fake_module))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "empty-home"))
    assert resolve_app_icon_path() == repo_icon


def test_resolve_manual_path_from_repo_layout():
    path = resolve_manual_path()
    assert path is not None
    assert path.name == "MANUAL.md"
    assert path.is_file()