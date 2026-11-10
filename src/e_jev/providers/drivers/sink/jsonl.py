"""providers/drivers/sink/jsonl: answered decisions as JSONL — the corpus the distillation loop trains fast heads from.

One line per answered question: state, question, the raw scores, the backend that produced them. Append-only,
unbuffered: a crash loses nothing already written. This is the teacher's syllabus (the reading route's distribution),
so the same state can carry the slow path's exact probabilities while the fast paths serve the live traffic."""

import time
from collections.abc import Sequence
from io import FileIO
from pathlib import Path
from typing import ClassVar, Self

import msgspec

from e_jev.infra.errors import DriverError
from e_jev.infra.logger import logger
from e_jev.models.systemone import Question
from e_jev.ports.provider import Isolation, Locality, Opened, ProviderSpec, Workload


##### TYPES #####
class JsonlSinkDriver:
    __slots__ = ("_file", "_path")

    spec: ClassVar[ProviderSpec] = ProviderSpec("jsonl", Locality.FILESYSTEM, Workload.IO_BOUND, Isolation.LOOP)
    file = Opened[FileIO](DriverError)

    def __init__(self, *, path: Path) -> None:
        self._path = path
        self._file: FileIO | None = None

    async def __aenter__(self) -> Self:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = FileIO(self._path, "ab")
        logger.info("decision log open", path=str(self._path))
        return self

    async def __aexit__(self, *exc: object) -> None:
        match self._file:
            case None:
                return
            case file:
                file.close()
                self._file = None

    async def health(self) -> bool:
        _ = self.file
        return True

    def record(self, state: str, question: Question, scores: Sequence[float], backend: str) -> None:
        line = {"ts": time.time(), "backend": backend, "state": state, "question": question, "scores": list(scores)}
        self.file.write(msgspec.json.encode(line) + b"\n")
