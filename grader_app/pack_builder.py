"""Create an assignment pack from documents: assignment PDF, instructor guide (reference
solution and rubric) and optional reference code. The AI can draft the rubric rows from the
guide; a person checks and edits them before the pack is saved."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .pack import _pdf_text

DEFAULT_RULES = [
    "Do not deduct twice for the same error if later work follows consistently from it.",
    "AI use is required. Do not deduct because the writing or code looks AI-generated. Do not use AI-detector scores.",
    "Missing verification loses credit in the verification row even if the final answer is correct.",
    "If work only seems unverified but there is no concrete inconsistency, grade only what is demonstrated.",
    "Results or checks that are not produced by the submitted code, outputs or AI record count as not demonstrated, "
    "and are also an integrity finding.",
    "Correct alternative proofs, code, and checks receive full credit. The instructor guide is a reference, not an "
    "exact-match key.",
]

DRAFT_SYSTEM = """You help an instructor set up an AI-assisted grading tool for a university mathematics assignment.
From the assignment handout and the instructor's guide, extract the grading rubric exactly as the instructor wrote it.
Rules:
- Use the rubric rows, groups and maximum points from the guide. Do not invent rows or change points. If the guide has no
  explicit rubric, propose rows that follow the handout's required sections and say so in "notes".
- For each row write "screening_focus": two or three sentences telling a pre-screening assistant what to check in a
  student's submission for this row. Describe what a correct and complete answer must establish. Do not describe the
  guide's specific solution as the expected answer, because many correct solutions exist.
- "accepted_alternatives": short examples of other valid approaches a student might take (different proof mechanisms,
  formulations, code designs, checks). These are examples, not a complete list.
- "required_headings": section headings the handout requires, each with the label of the rubric row it belongs to.
- "page_limit": the main report page limit from the handout, or 0 if none.
Return only the JSON."""


def draft_schema() -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["title", "rubric", "grading_rules", "accepted_alternatives", "required_headings",
                     "page_limit", "notes"],
        "properties": {
            "title": {"type": "string"},
            "rubric": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["group", "label", "max", "description", "screening_focus"],
                "properties": {"group": {"type": "string"}, "label": {"type": "string"},
                               "max": {"type": "number"}, "description": {"type": "string"},
                               "screening_focus": {"type": "string"}}}},
            "grading_rules": {"type": "array", "items": {"type": "string"}},
            "accepted_alternatives": {"type": "array", "items": {"type": "string"}},
            "required_headings": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["text", "row_label"],
                "properties": {"text": {"type": "string"}, "row_label": {"type": "string"}}}},
            "page_limit": {"type": "integer"},
            "notes": {"type": "string"},
        },
    }


def ai_draft(api_key: str, model: str, assignment_pdf: Path, guide_path: Path, http_client=None) -> dict:
    from openai import OpenAI
    kw = {"http_client": http_client} if http_client is not None else {}
    client = OpenAI(api_key=api_key, timeout=300, max_retries=2, **kw)
    assignment = _pdf_text(assignment_pdf)
    guide = _pdf_text(guide_path) if guide_path.suffix.lower() == ".pdf" else guide_path.read_text(errors="replace")
    resp = client.responses.create(
        model=model, instructions=DRAFT_SYSTEM, store=False,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": "=== ASSIGNMENT HANDOUT ===\n" + assignment},
            {"type": "input_text", "text": "=== INSTRUCTOR GUIDE (reference solution and rubric) ===\n" + guide}]}],
        text={"format": {"type": "json_schema", "name": "pack_draft", "schema": draft_schema(), "strict": True}},
        max_output_tokens=6000)
    return json.loads(resp.output_text)


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:40] or "row"


def build_pack(folder: Path, template: dict, title: str, short_name: str, assignment_pdf: Path,
               guide_path: Path, reference_code: Path | None, rubric_rows: list[dict], grading_rules: list[str],
               alternatives: list[str], headings: list[dict], page_limit: int) -> Path:
    """Write pack.json and copy the documents into folder."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(assignment_pdf, folder / ("assignment" + assignment_pdf.suffix.lower()))
    shutil.copy(guide_path, folder / ("instructor_guide" + guide_path.suffix.lower()))
    files = {"assignment": "assignment" + assignment_pdf.suffix.lower(),
             "instructor_guide": "instructor_guide" + guide_path.suffix.lower()}
    if reference_code and reference_code.exists():
        shutil.copy(reference_code, folder / ("reference_code" + reference_code.suffix.lower()))
        files["reference_code"] = "reference_code" + reference_code.suffix.lower()

    rubric, seen = [], set()
    for r in rubric_rows:
        rid = slug(r["label"])
        while rid in seen:
            rid += "_2"
        seen.add(rid)
        rubric.append({"id": rid, "group": r.get("group", ""), "label": r["label"], "max": float(r["max"]),
                       "description": r.get("description", ""), "screening_focus": r.get("screening_focus", "")})
    by_label = {r["label"].lower(): r["id"] for r in rubric}
    req = []
    for h in headings:
        rid = by_label.get((h.get("row_label") or "").lower())
        if h.get("text") and rid:
            req.append({"text": h["text"], "row": rid})

    data = {
        "pack_version": 1,
        "id": slug(short_name or title),
        "course": template.get("course", ""),
        "title": title,
        "short_name": short_name,
        "files": files,
        "model": template.get("model", {}),
        "report": {**template.get("report", {}), "page_limit": int(page_limit) or None, "required_headings": req},
        "rubric": rubric,
        "levels": template.get("levels", [100, 75, 50, 25, 0]),
        "level_descriptions": template.get("level_descriptions", {}),
        "grading_rules": grading_rules or DEFAULT_RULES,
        "accepted_alternatives": alternatives,
        "integrity": json.loads(json.dumps(template.get("integrity", {}))),
        "reference_checks": [],
        "trace_checks": [],
        "chat_placeholder_patterns": template.get("chat_placeholder_patterns", []),
    }
    # integrity default rows must point at rows that exist in this pack
    ids = {r["id"] for r in rubric}
    for c in data["integrity"].get("categories", []):
        c["default_rows"] = [x for x in c.get("default_rows", []) if x in ids]
    (folder / "pack.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return folder
