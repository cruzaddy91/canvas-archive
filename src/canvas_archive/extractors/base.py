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
    canvas_files_downloaded: int = 0
    canvas_file_bytes_total: int = 0
    canvas_file_errors: int = 0
    external_starters_downloaded: int = 0
    external_spec_follow_downloaded: int = 0
    extract_duration_ms: int = 0
    notes: list[str] = field(default_factory=list)
    # canvas_only stage counters (JSON logs / dashboards; default 0 for other strategies)
    stage_home_table_canvas_assignments: int = 0
    stage_home_table_external_assignments: int = 0
    stage_assignments_with_canvas_downloads: int = 0
    stage_assignments_with_external_downloads: int = 0

    def summary(self) -> str:
        bits = [f"assignments={self.assignments_written}"]
        if self.assignments_enriched:
            bits.append(f"enriched={self.assignments_enriched}")
        if self.canvas_files_downloaded:
            bits.append(f"canvas_files={self.canvas_files_downloaded}")
        if self.external_starters_downloaded:
            bits.append(f"external_starters={self.external_starters_downloaded}")
        if self.external_spec_follow_downloaded:
            bits.append(f"external_spec_follow={self.external_spec_follow_downloaded}")
        if self.canvas_file_bytes_total:
            bits.append(f"canvas_file_bytes={self.canvas_file_bytes_total}")
        if self.canvas_file_errors:
            bits.append(f"canvas_file_errors={self.canvas_file_errors}")
        if self.extract_duration_ms:
            bits.append(f"extract_ms={self.extract_duration_ms}")
        if self.starters_copied:
            bits.append(f"starters={self.starters_copied}")
        if self.handouts_html or self.handouts_pdf:
            bits.append(f"handouts={self.handouts_html}md/{self.handouts_pdf}pdf")
        if self.stage_home_table_canvas_assignments or self.stage_home_table_external_assignments:
            bits.append(
                f"home_table_assignments={self.stage_home_table_canvas_assignments}c/"
                f"{self.stage_home_table_external_assignments}e"
            )
        if self.stage_assignments_with_canvas_downloads or self.stage_assignments_with_external_downloads:
            bits.append(
                f"dl_assignments={self.stage_assignments_with_canvas_downloads}c/"
                f"{self.stage_assignments_with_external_downloads}e"
            )
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
