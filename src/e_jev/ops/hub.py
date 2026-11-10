"""ops/hub: model weights from the Hugging Face Hub — one pinned snapshot per spec, verified, idempotent.

`huggingface_hub.snapshot_download` does the transfer (hf_xet's Rust chunk store when the repo is on Xet, plain HTTP
otherwise; `HF_HUB_DISABLE_XET=1` forces the latter): resumable, parallel, and a no-op for files already in place.
A pull pins a revision — a tag or a commit, never a moving branch — and, when the repo ships a `SHA256SUMS`, every
file it lists is hashed against it before the snapshot is trusted. The transfer and the hashing block, so both run
in a thread."""

import asyncio
import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from huggingface_hub import snapshot_download

from e_jev.infra.errors import OpsError
from e_jev.infra.logger import logger

SUMS: Final[str] = "SHA256SUMS"


##### TYPES #####
class HubError(OpsError):
    """A snapshot that could not be fetched, or whose files do not match the sums the repo ships."""


##### OPS #####
def hub_digest(path: Path) -> str:
    """The sha256 of one file, streamed: a 9 GB shard is never held whole."""
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def hub_verify(folder: Path) -> int:
    """Every file `SHA256SUMS` lists, hashed and compared; the count checked — 0 when the repo ships no sums."""
    sums = folder / SUMS
    match sums.is_file():
        case False:
            return 0
        case True:
            listed = [line.split(maxsplit=1) for line in sums.read_text().splitlines() if line.strip()]
            wrong = [name.lstrip("*") for digest, name in listed if hub_digest(folder / name.lstrip("*")) != digest]
            match wrong:
                case []:
                    return len(listed)
                case files:
                    msg = f"{folder}: sha256 mismatch for {files}"
                    raise HubError(msg)


def hub_fetch(repo: str, revision: str, folder: Path, *, include: Sequence[str] = (), exclude: Sequence[str] = ()) -> Path:
    """The snapshot of `repo@revision` in `folder` — every file, or those `include` names minus those `exclude` names —
    fetched or completed in place, then verified. Blocking: see `hub_pull`."""
    try:
        snapshot_download(
            repo, revision=revision, local_dir=folder, allow_patterns=list(include) or None, ignore_patterns=list(exclude) or None
        )
    except (OSError, ValueError) as error:
        msg = f"{repo}@{revision}: {error}"
        raise HubError(msg) from error
    checked = hub_verify(folder)
    logger.info("hub snapshot ready", repo=repo, revision=revision, folder=str(folder), verified=checked)
    return folder


async def hub_pull(repo: str, revision: str, folder: Path, *, include: Sequence[str] = (), exclude: Sequence[str] = ()) -> Path:
    """`hub_fetch` off the event loop: the transfer and the hashing are blocking I/O."""
    logger.info("hub pull", repo=repo, revision=revision, folder=str(folder))
    return await asyncio.to_thread(hub_fetch, repo, revision, folder, include=include, exclude=exclude)
