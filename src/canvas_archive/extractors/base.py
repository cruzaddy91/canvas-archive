from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ExtractResult:
    assignments_written: int = 0
    assignments_enriched: int = 0
    starters_copied: int = 0
    handouts_html: int = 0
    handouts_pdf: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        bits = [f"assignments={self.assignments_written}"]
        if self.assignments_enriched:
            bits.append(f"enriched={self.assignments_enriched}")
        if self.starters_copied:
            bits.append(f"starters={self.starters_copied}")
        if self.handouts_html or self.handouts_pdf:
            bits.append(f"handouts={self.handouts_html}md/{self.handouts_pdf}pdf")
        return ", ".join(bits)


class ExtractStrategy(Protocol):
    def extract(self, course, profile: dict[str, Any], out_dir: Path) -> ExtractResult: ...


def reset_dir(path: Path) -> None:
    import shutil
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
