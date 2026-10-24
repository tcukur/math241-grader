"""Assignment packs: everything the instructor defines once per assignment.

A pack is a folder containing pack.json plus the assignment PDF, the
instructor guide (reference solution and rubric) and optional reference code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf


@dataclass
class RubricRow:
    id: str
    group: str
    label: str
    max: float
    description: str
    screening_focus: str


@dataclass
class IntegrityCategory:
    id: str
    label: str
    description: str
    points: float
    row_cap_pct: float | None
    half_row_cap_pct: float | None
    default_rows: list[str]
    student_text: str
    ta_check: str = ""


@dataclass
class Pack:
    folder: Path
    data: dict
    rubric: list[RubricRow] = field(default_factory=list)
    categories: list[IntegrityCategory] = field(default_factory=list)
    assignment_text: str = ""
    guide_text: str = ""
    reference_code: str = ""

    # convenience accessors -------------------------------------------------
    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def title(self) -> str:
        return self.data.get("title", self.id)

    @property
    def model(self) -> dict:
        return self.data.get("model", {})

    @property
    def report(self) -> dict:
        return self.data.get("report", {})

    @property
    def levels(self) -> list[int]:
        return self.data.get("levels", [100, 75, 50, 25, 0])

    @property
    def total_max(self) -> float:
        return sum(r.max for r in self.rubric)

    @property
    def integrity_cap(self) -> float:
        return float(self.data.get("integrity", {}).get("total_cap", 0))

    @property
    def exclusive_groups(self) -> list[list[str]]:
        return self.data.get("integrity", {}).get("exclusive_groups", [])

    def handout_points(self, row_id: str) -> float | None:
        """Original points of this item, when the instructor has changed them since. None otherwise."""
        v = (self.data.get("handout_points") or {}).get(row_id)
        r = self.row(row_id)
        return float(v) if v is not None and r is not None and float(v) != r.max else None

    def reweighted(self) -> list[tuple[str, float, float]]:
        """[(item, points in the handout, points now)] for items whose points were changed."""
        return [(r.label, self.handout_points(r.id), r.max) for r in self.rubric
                if self.handout_points(r.id) is not None]

    def row(self, row_id: str) -> RubricRow | None:
        return next((r for r in self.rubric if r.id == row_id), None)

    def category(self, cat_id: str) -> IntegrityCategory | None:
        return next((c for c in self.categories if c.id == cat_id), None)


def _pdf_text(path: Path) -> str:
    if not path.exists():
        return ""
    with pymupdf.open(path) as doc:
        parts = []
        for i, page in enumerate(doc, start=1):
            parts.append(f"[page {i}]\n" + page.get_text().replace("​", ""))
    return "\n".join(parts)


def load_pack(folder: str | Path) -> Pack:
    folder = Path(folder)
    manifest = folder / "pack.json"
    if not manifest.exists():
        raise FileNotFoundError(f"No pack.json found in {folder}")
    data = json.loads(manifest.read_text(encoding="utf-8"))

    pack = Pack(folder=folder, data=data)
    pack.rubric = [RubricRow(**r) for r in data["rubric"]]
    for c in data.get("integrity", {}).get("categories", []):
        pack.categories.append(IntegrityCategory(
            id=c["id"], label=c["label"], description=c.get("description", ""),
            points=float(c.get("points", 0)), row_cap_pct=c.get("row_cap_pct"),
            half_row_cap_pct=c.get("half_row_cap_pct"),
            default_rows=list(c.get("default_rows", [])),
            student_text=c.get("student_text", c["label"]), ta_check=c.get("ta_check", ""),
        ))

    files = data.get("files", {})
    if files.get("assignment"):
        pack.assignment_text = _pdf_text(folder / files["assignment"])
    if files.get("instructor_guide"):
        guide = folder / files["instructor_guide"]
        if guide.suffix.lower() == ".pdf":
            pack.guide_text = _pdf_text(guide)
        elif guide.exists():
            pack.guide_text = guide.read_text(encoding="utf-8", errors="replace")
    if files.get("reference_code"):
        ref = folder / files["reference_code"]
        if ref.exists():
            pack.reference_code = ref.read_text(encoding="utf-8", errors="replace")
    return pack
