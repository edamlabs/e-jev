"""ops/hub: a pinned snapshot, fetched in place and verified against the sums its repo ships."""

import hashlib
from pathlib import Path

import pytest

from e_jev.ops import hub
from e_jev.ops.hub import HubError, hub_pull, hub_verify


def _sums(folder: Path, files: dict[str, bytes], *, corrupt: str = "") -> None:
    lines = [f"{hashlib.sha256(body).hexdigest() if name != corrupt else '0' * 64}  {name}" for name, body in files.items()]
    for name, body in files.items():
        (folder / name).write_bytes(body)
    (folder / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def test_verify_without_sums(tmp_path: Path) -> None:
    assert hub_verify(tmp_path) == 0


def test_verify_counts_every_listed_file(tmp_path: Path) -> None:
    _sums(tmp_path, {"a.bin": b"a", "b.bin": b"b"})
    assert hub_verify(tmp_path) == 2


def test_verify_names_the_mismatch(tmp_path: Path) -> None:
    _sums(tmp_path, {"a.bin": b"a", "b.bin": b"b"}, corrupt="b.bin")
    with pytest.raises(HubError, match=r"\['b.bin'\]"):
        hub_verify(tmp_path)


async def test_pull_passes_the_pin_and_patterns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: dict[str, object] = {}

    def fake(repo: str, **kwargs: object) -> str:
        asked.update(repo=repo, **kwargs)
        _sums(tmp_path, {"w.gguf": b"w"})
        return str(tmp_path)

    monkeypatch.setattr(hub, "snapshot_download", fake)
    assert await hub_pull("org/model", "v1", tmp_path, include=("*.gguf",), exclude=("assets/*",)) == tmp_path
    assert asked == {
        "repo": "org/model",
        "revision": "v1",
        "local_dir": tmp_path,
        "allow_patterns": ["*.gguf"],
        "ignore_patterns": ["assets/*"],
    }


async def test_pull_translates_transfer_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(repo: str, **_: object) -> str:
        message = "no space left"
        raise OSError(message)

    monkeypatch.setattr(hub, "snapshot_download", broken)
    with pytest.raises(HubError, match="org/model@v1: no space left"):
        await hub_pull("org/model", "v1", tmp_path)
