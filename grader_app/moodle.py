"""Moodle submission folders and the offline grading worksheet."""
from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

# "Full Name_123456_assignsubmission_file_" (folder) or the same prefix + filename (flat)
MOODLE_RE = re.compile(r"^(?P<name>.+?)_(?P<pid>\d{3,})_assignsubmission_(?P<plugin>[a-z]+)_?(?P<rest>.*)$")


@dataclass
class FoundSubmission:
    sub_id: str
    name: str
    layout: str          # "folder", "flat" or "plain"
    moodle_prefix: str   # folder name (folder) or filename prefix (flat); "" for plain
    pdf_path: Path
    note: str = ""


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def unpack_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):
                continue  # ignore unsafe paths
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(target, "wb") as out:
                    out.write(src.read())
    return dest


def scan_submissions(root: Path) -> tuple[list[FoundSubmission], list[str]]:
    root = Path(root)
    found: dict[str, FoundSubmission] = {}
    notes: list[str] = []
    pdfs = sorted(p for p in root.rglob("*") if p.suffix.lower() == ".pdf" and p.is_file()
                  and not p.name.startswith("._"))
    for pdf in pdfs:
        rel_parts = pdf.relative_to(root).parts
        sub = None
        # folder layout: any ancestor folder named like a Moodle submission folder
        for part in rel_parts[:-1]:
            m = MOODLE_RE.match(part)
            if m:
                sub = FoundSubmission(m["pid"], m["name"].strip(), "folder", part, pdf)
                break
        if sub is None:
            m = MOODLE_RE.match(pdf.name)
            if m:
                prefix = pdf.name[: len(pdf.name) - len(m["rest"])] if m["rest"] else pdf.stem + "_"
                sub = FoundSubmission(m["pid"], m["name"].strip(), "flat", prefix, pdf)
        if sub is None:
            sid = re.sub(r"[^\w\-]+", "_", pdf.stem)[:60]
            sub = FoundSubmission(sid, "", "plain", "", pdf)
        if sub.sub_id in found:
            prev = found[sub.sub_id]
            keep = max((prev, sub), key=lambda s: s.pdf_path.stat().st_size)
            keep.note = f"Several PDFs found for this student; using {keep.pdf_path.name}."
            found[sub.sub_id] = keep
            notes.append(f"{sub.sub_id}: more than one PDF, kept the largest ({keep.pdf_path.name}).")
        else:
            found[sub.sub_id] = sub
    return list(found.values()), notes


# grading worksheet ----------------------------------------------------------

@dataclass
class Worksheet:
    path: Path
    header: list[str]
    rows: list[dict]
    bom: bool
    delimiter: str

    def col(self, *names: str) -> str | None:
        low = {h.lower().strip(): h for h in self.header}
        for n in names:
            if n.lower() in low:
                return low[n.lower()]
        return None

    def pid_of(self, row: dict) -> str | None:
        c = self.col("Identifier")
        if not c:
            return None
        m = re.search(r"(\d+)", row.get(c, ""))
        return m.group(1) if m else None

    def max_grade(self) -> float | None:
        c = self.col("Maximum Grade", "Maximum grade")
        for r in self.rows:
            try:
                return float(str(r.get(c, "")).replace(",", "."))
            except (TypeError, ValueError):
                continue
        return None


def read_worksheet(path: Path) -> Worksheet:
    raw = Path(path).read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        delim = ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    rows = list(reader)
    return Worksheet(Path(path), list(reader.fieldnames or []), rows, bom, delim)


def write_worksheet(ws: Worksheet, out_path: Path) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=ws.header, delimiter=ws.delimiter, quoting=csv.QUOTE_MINIMAL)
    w.writeheader()
    for r in ws.rows:
        w.writerow(r)
    data = buf.getvalue().encode("utf-8")
    if ws.bom:
        data = b"\xef\xbb\xbf" + data
    Path(out_path).write_bytes(data)


def worksheet_identities(path: Path) -> dict[str, dict]:
    """participant id -> {full_name, email, id_number} from the grading worksheet."""
    ws = read_worksheet(path)
    name_c = ws.col("Full name")
    email_c = ws.col("Email address", "Email")
    idn_c = ws.col("ID number", "Idnumber", "Student ID")
    out = {}
    for r in ws.rows:
        pid = ws.pid_of(r)
        if pid:
            out[pid] = {"full_name": (r.get(name_c) or "").strip() if name_c else "",
                        "email": (r.get(email_c) or "").strip() if email_c else "",
                        "id_number": (r.get(idn_c) or "").strip() if idn_c else ""}
    return out


_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str) -> str:
    """Keep the name readable (spaces and Turkish letters stay) but legal on Windows and macOS."""
    return _BAD.sub("_", name).strip().rstrip(".")


# class list (Moodle gradebook export or assignment grading worksheet) ---------------

def _norm_key(name: str) -> str:
    """Key matching Moodle's file-name form, where spaces and non-ASCII letters become '_'."""
    return re.sub(r"[^A-Za-z0-9]", "_", name.strip())


def _fold_key(name: str) -> str:
    import unicodedata
    t = name.replace("ı", "i").replace("İ", "I")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", t.lower())


def read_class_list(path: Path) -> dict:
    """Read a Moodle gradebook export (.xlsx or .csv) or an assignment grading worksheet.

    Returns {"kind": "worksheet"|"roster", "students": [{full_name, id_number, email, participant}]}."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = list(wb.worksheets[0].iter_rows(values_only=True))
        header = [str(h or "").strip() for h in rows[0]]
        data = [{header[i]: ("" if v is None else str(v)).strip() for i, v in enumerate(r) if i < len(header)}
                for r in rows[1:] if r and any(v is not None for v in r)]
    else:
        ws = read_worksheet(path)
        header, data = ws.header, ws.rows
    low = {h.lower(): h for h in header}

    def col(*names):
        for n in names:
            if n.lower() in low:
                return low[n.lower()]
        return None
    c_first, c_last, c_full = col("First name"), col("Last name", "Surname"), col("Full name")
    c_id = col("ID number", "Bilkent ID", "Student ID", "Idnumber")
    c_mail, c_ident = col("Email address", "Email"), col("Identifier")
    out = []
    for r in data:
        full = (r.get(c_full) or "") if c_full else f"{r.get(c_first, '')} {r.get(c_last, '')}".strip()
        if not full:
            continue
        pid = ""
        if c_ident:
            m = re.search(r"(\d+)", r.get(c_ident, "") or "")
            pid = m.group(1) if m else ""
        idn = (r.get(c_id) or "") if c_id else ""
        if idn.endswith(".0"):
            idn = idn[:-2]
        out.append({"full_name": " ".join(full.split()), "id_number": idn,
                    "email": (r.get(c_mail) or "") if c_mail else "", "participant": pid})
    return {"kind": "worksheet" if c_ident else "roster", "students": out}


def match_student(file_name_part: str, pid: str, page1_ids: list[str], cls: dict) -> tuple[dict | None, str]:
    """Find the class-list entry for a submission. Returns (entry, note)."""
    studs = cls["students"]
    if cls["kind"] == "worksheet":
        hit = next((s for s in studs if s["participant"] == pid), None)
        if hit:
            return hit, ""
    by_key = [s for s in studs if _norm_key(s["full_name"]) == file_name_part]
    if not by_key:
        fk = _fold_key(file_name_part.replace("_", ""))
        by_key = [s for s in studs if _fold_key(s["full_name"]) == fk]
    by_id = [s for s in studs if s["id_number"] and s["id_number"] in page1_ids]
    if len(by_key) == 1:
        s = by_key[0]
        if page1_ids and s["id_number"] and s["id_number"] not in page1_ids:
            other = by_id[0]["full_name"] if by_id else None
            return s, ("The student ID on page 1 does not match the class list"
                       + (f" (it belongs to {other})." if other else "."))
        return s, ""
    if len(by_key) > 1:
        both = [s for s in by_key if s in by_id]
        if len(both) == 1:
            return both[0], ""
        return None, "Several students in the class list have this name. Check by hand."
    if len(by_id) == 1:
        return by_id[0], "Matched by the student ID on page 1 (name in the file did not match)."
    return None, "Not found in the class list."
