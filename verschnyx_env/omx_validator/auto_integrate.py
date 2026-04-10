#!/usr/bin/env python3
"""
Auto-Integration Pipeline
==========================

Prueft neue Materialien gegen die aktuelle Knowledge-Base und
importiert genuinely neue Kapitel automatisch.

Workflow:
  1. KB laden (knowledge/) + Shingle-Index aufbauen
  2. Neue Dateien scannen (memory/new_material/ oder beliebiger Ordner)
  3. Jede Datei gegen KB matchen (Jaccard-Similarity)
  4. Klassifikation:
     - NEW  (sim < 0.20): Auto-Import nach knowledge/
     - NEAR (0.20-0.50):  Review-Queue (nur Log, kein Import)
     - EXACT (>= 0.50):   Uebersprungen (schon in KB)
  5. Report mit Ergebnissen

Verwendung:
    python omx_validator/auto_integrate.py                    # Standard: memory/new_material/
    python omx_validator/auto_integrate.py --source /pfad/    # Beliebiger Ordner
    python omx_validator/auto_integrate.py --dry-run           # Nur pruefen, nichts kopieren
    python omx_validator/auto_integrate.py --threshold 0.15    # Strengerer NEW-Schwellwert

Stdlib-only (kein pip install noetig).
"""

import io
import os
import re
import sys
import json
import shutil
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# UTF-8 fuer Windows-Konsole
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ─── Pfade ───────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
ENV_DIR = HERE.parent
BASE_DIR = ENV_DIR.parent
KB_DIR = BASE_DIR / "knowledge"
DEFAULT_SOURCE = ENV_DIR / "memory" / "new_material"
REPORTS_DIR = HERE / "reports"

# ─── Schwellwerte ────────────────────────────────────────────────
THR_EXACT = 0.50
THR_NEAR = 0.20

# ─── CLI-Argumente ───────────────────────────────────────────────
DRY_RUN = "--dry-run" in sys.argv or "-n" in sys.argv
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

SOURCE_DIR = DEFAULT_SOURCE
THR_NEW_OVERRIDE = None
for i, arg in enumerate(sys.argv):
    if arg == "--source" and i + 1 < len(sys.argv):
        SOURCE_DIR = Path(sys.argv[i + 1])
    if arg == "--threshold" and i + 1 < len(sys.argv):
        try:
            THR_NEW_OVERRIDE = float(sys.argv[i + 1])
        except ValueError:
            pass

if THR_NEW_OVERRIDE is not None:
    THR_NEAR = THR_NEW_OVERRIDE

# ─── Stopwords ───────────────────────────────────────────────────
STOPWORDS_DE = {
    "der", "die", "das", "und", "oder", "ist", "in", "zu", "den", "ein",
    "eine", "einen", "dem", "des", "mit", "auf", "fuer", "von", "im",
    "am", "es", "sich", "an", "als", "wie", "auch", "aber", "nicht",
    "was", "dass", "so", "nur", "noch", "schon", "sehr", "aus",
    "bei", "nach", "aus", "durch", "ohne", "ueber", "unter", "vor",
}


# ─── Datenklassen ────────────────────────────────────────────────

@dataclass
class KBEntry:
    filename: str
    title: str
    body: str
    shingles: set = field(default_factory=set)


@dataclass
class NewFile:
    path: Path
    filename: str
    title: str
    body: str
    source_bucket: str  # z.B. "from_vorarbeit", "from_smashwords"
    word_count: int = 0
    shingles: set = field(default_factory=set)
    # Match-Ergebnisse
    best_sim: float = 0.0
    best_match: str = ""
    status: str = "NEW"


# ─── Core-Funktionen (aus Phase 5) ──────────────────────────────

def shingle_set(text: str, k: int = 5) -> set:
    words = [w for w in re.findall(r"\w+", text.lower())
             if w not in STOPWORDS_DE and len(w) > 2]
    if len(words) < k:
        return set([tuple(words)]) if words else set()
    return set(tuple(words[i:i + k]) for i in range(len(words) - k + 1))


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def parse_frontmatter(content: str):
    """Extrahiert Titel und Body aus YAML-Frontmatter."""
    if not content.startswith("---"):
        return None, content
    try:
        end_idx = content.index("\n---", 3)
    except ValueError:
        return None, content
    fm_text = content[3:end_idx]
    body = content[end_idx + 4:].lstrip("\n")
    title_m = re.search(r"^\s*title:\s*['\"]?([^'\"\n]+)['\"]?\s*$", fm_text, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else None
    return title, body


# ─── KB laden ────────────────────────────────────────────────────

def load_kb(kb_dir: Path) -> list:
    """Laedt alle .md-Dateien aus knowledge/ (ohne _archive/)."""
    entries = []
    for f in sorted(kb_dir.iterdir()):
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        # _archive/ Unterordner ueberspringen
        if f.name.startswith("_"):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            if VERBOSE:
                print(f"  [warn] {f.name}: {e}")
            continue

        title, body = parse_frontmatter(content)
        if title is None:
            h1_m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            title = h1_m.group(1).strip() if h1_m else f.stem

        entries.append(KBEntry(filename=f.name, title=title, body=body))
    return entries


def build_shingle_index(entries: list) -> dict:
    """Baut Inverted Shingle Index fuer schnelles Matching."""
    index = defaultdict(set)
    for i, e in enumerate(entries):
        e.shingles = shingle_set(e.body, k=5)
        for sh in e.shingles:
            index[sh].add(i)
    return index


# ─── Neue Dateien laden ─────────────────────────────────────────

def load_new_files(source_dir: Path) -> list:
    """Laedt alle .md-Dateien aus dem Source-Verzeichnis (rekursiv)."""
    files = []
    for root, dirs, filenames in os.walk(source_dir):
        # Bucket-Name aus Unterordner ableiten
        rel = Path(root).relative_to(source_dir)
        bucket = str(rel) if str(rel) != "." else "root"

        for fname in sorted(filenames):
            if not fname.endswith(".md") or fname == "README.md":
                continue
            fpath = Path(root) / fname
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            title, body = parse_frontmatter(content)
            if title is None:
                h1_m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
                title = h1_m.group(1).strip() if h1_m else fpath.stem

            word_count = len(body.split())

            files.append(NewFile(
                path=fpath,
                filename=fname,
                title=title,
                body=body,
                source_bucket=bucket,
                word_count=word_count,
            ))
    return files


# ─── Matching ────────────────────────────────────────────────────

def match_file(new_file: NewFile, entries: list, index: dict):
    """Matcht eine neue Datei gegen den KB-Index."""
    new_file.shingles = shingle_set(new_file.body, k=5)

    if not new_file.shingles:
        new_file.status = "NEW"
        new_file.best_sim = 0.0
        return

    # Kandidaten via Inverted Index finden
    hit_counts = defaultdict(int)
    for sh in new_file.shingles:
        for idx in index.get(sh, ()):
            hit_counts[idx] += 1

    if not hit_counts:
        new_file.status = "NEW"
        new_file.best_sim = 0.0
        return

    # Top-20 Kandidaten, dann exakte Jaccard berechnen
    top = sorted(hit_counts.items(), key=lambda x: -x[1])[:20]
    best_sim = 0.0
    best_match = ""
    for idx, _ in top:
        sim = jaccard(new_file.shingles, entries[idx].shingles)
        if sim > best_sim:
            best_sim = sim
            best_match = entries[idx].filename

    new_file.best_sim = best_sim
    new_file.best_match = best_match

    if best_sim >= THR_EXACT:
        new_file.status = "EXACT"
    elif best_sim >= THR_NEAR:
        new_file.status = "NEAR"
    else:
        new_file.status = "NEW"


# ─── Import-Logik ───────────────────────────────────────────────

def sanitize_filename(title: str, max_len: int = 80) -> str:
    """Erzeugt einen sicheren Dateinamen aus einem Titel."""
    # Umlaute ersetzen
    replacements = {
        "ae": "ae", "oe": "oe", "ue": "ue", "ss": "ss",
    }
    s = title
    for old, new in replacements.items():
        s = s.replace(old, new)
    # Nur alphanumerisch + Bindestrich
    s = re.sub(r"[^a-zA-Z0-9\u00c0-\u017f\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s[:max_len]


def generate_import_filename(new_file: NewFile) -> str:
    """Erzeugt den Dateinamen fuer den Import nach knowledge/."""
    # Prefix nach Bucket
    prefix_map = {
        "from_vorarbeit": "Vorarbeit",
        "from_smashwords": "Smashwords",
        "from_hauptwerk_new": "Hauptwerk",
        "from_hauptwerk_near": "Hauptwerk-near",
    }
    prefix = prefix_map.get(new_file.source_bucket, "imported")
    safe_title = sanitize_filename(new_file.title)
    if not safe_title:
        safe_title = new_file.path.stem
    return f"{prefix}_{safe_title}.md"


def import_file(new_file: NewFile, kb_dir: Path) -> bool:
    """Kopiert eine neue Datei nach knowledge/."""
    target_name = generate_import_filename(new_file)
    target_path = kb_dir / target_name

    # Namenskollision vermeiden
    if target_path.exists():
        # Hash anhaengen
        h = hashlib.md5(new_file.body[:500].encode()).hexdigest()[:6]
        stem = target_path.stem
        target_path = kb_dir / f"{stem}_{h}.md"

    if DRY_RUN:
        if VERBOSE:
            print(f"  [DRY-RUN] {new_file.filename} -> {target_path.name}")
        return True

    shutil.copy2(str(new_file.path), str(target_path))
    return True


# ─── Report ──────────────────────────────────────────────────────

def generate_report(new_files: list, imported: int, skipped: int,
                    review: int, elapsed: float) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode = "DRY-RUN" if DRY_RUN else "LIVE"

    lines = [
        f"# Auto-Integration Report",
        f"",
        f"**Datum:** {timestamp}  ",
        f"**Modus:** {mode}  ",
        f"**Quelle:** {SOURCE_DIR}  ",
        f"**KB-Verzeichnis:** {KB_DIR}  ",
        f"**Dauer:** {elapsed:.1f}s  ",
        f"",
        f"## Zusammenfassung",
        f"",
        f"| Status | Dateien | Aktion |",
        f"|--------|---------|--------|",
        f"| NEW (sim < {THR_NEAR:.2f}) | {imported} | {'Wuerde importieren' if DRY_RUN else 'Importiert'} |",
        f"| NEAR ({THR_NEAR:.2f}-{THR_EXACT:.2f}) | {review} | Review-Queue (nicht importiert) |",
        f"| EXACT (>= {THR_EXACT:.2f}) | {skipped} | Uebersprungen (schon in KB) |",
        f"| **Gesamt** | **{len(new_files)}** | |",
        f"",
    ]

    # NEW-Dateien auflisten
    new_items = [f for f in new_files if f.status == "NEW"]
    if new_items:
        lines.append(f"## Importiert ({len(new_items)} Dateien)")
        lines.append("")
        lines.append(f"| Datei | Bucket | Woerter | Best-Sim | Best-Match |")
        lines.append(f"|-------|--------|---------|----------|------------|")
        for f in sorted(new_items, key=lambda x: x.source_bucket):
            lines.append(
                f"| {f.filename} | {f.source_bucket} | {f.word_count} | "
                f"{f.best_sim:.3f} | {f.best_match or '-'} |"
            )
        lines.append("")

    # NEAR-Dateien auflisten
    near_items = [f for f in new_files if f.status == "NEAR"]
    if near_items:
        lines.append(f"## Review-Queue ({len(near_items)} Dateien)")
        lines.append("")
        lines.append(f"| Datei | Bucket | Woerter | Best-Sim | Best-Match |")
        lines.append(f"|-------|--------|---------|----------|------------|")
        for f in sorted(near_items, key=lambda x: -x.best_sim):
            lines.append(
                f"| {f.filename} | {f.source_bucket} | {f.word_count} | "
                f"**{f.best_sim:.3f}** | {f.best_match} |"
            )
        lines.append("")

    # EXACT-Dateien (nur Anzahl, nicht alle auflisten)
    exact_items = [f for f in new_files if f.status == "EXACT"]
    if exact_items:
        lines.append(f"## Uebersprungen ({len(exact_items)} Dateien, bereits in KB)")
        lines.append("")
        for f in sorted(exact_items, key=lambda x: -x.best_sim)[:10]:
            lines.append(f"- `{f.filename}` (sim={f.best_sim:.3f} -> `{f.best_match}`)")
        if len(exact_items) > 10:
            lines.append(f"- ... und {len(exact_items) - 10} weitere")
        lines.append("")

    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────

def main():
    t_start = datetime.now()

    print(f"{'=' * 60}")
    print(f"  Auto-Integration Pipeline")
    print(f"  Modus: {'DRY-RUN' if DRY_RUN else 'LIVE'}")
    print(f"  Quelle: {SOURCE_DIR}")
    print(f"  KB: {KB_DIR}")
    print(f"  Schwellwerte: NEW < {THR_NEAR:.2f} | NEAR {THR_NEAR:.2f}-{THR_EXACT:.2f} | EXACT >= {THR_EXACT:.2f}")
    print(f"{'=' * 60}")
    print()

    # 1. KB laden
    print("1/4  Knowledge-Base laden ...")
    entries = load_kb(KB_DIR)
    print(f"     {len(entries)} KB-Eintraege geladen")

    # 2. Shingle-Index aufbauen
    print("2/4  Shingle-Index aufbauen ...")
    index = build_shingle_index(entries)
    total_shingles = len(index)
    print(f"     {total_shingles:,} einzigartige Shingles indexiert")
    print()

    # 3. Neue Dateien laden
    print("3/4  Neue Dateien scannen ...")
    if not SOURCE_DIR.exists():
        print(f"     FEHLER: {SOURCE_DIR} existiert nicht!")
        sys.exit(1)

    new_files = load_new_files(SOURCE_DIR)
    print(f"     {len(new_files)} neue Dateien gefunden")

    # Buckets anzeigen
    buckets = defaultdict(int)
    for f in new_files:
        buckets[f.source_bucket] += 1
    for bucket, count in sorted(buckets.items()):
        print(f"       {bucket}: {count}")
    print()

    # 4. Matching + Import
    print("4/4  Matching + Integration ...")
    imported = 0
    skipped = 0
    review = 0

    for i, nf in enumerate(new_files):
        match_file(nf, entries, index)

        if nf.status == "NEW":
            if import_file(nf, KB_DIR):
                imported += 1
        elif nf.status == "NEAR":
            review += 1
        else:
            skipped += 1

        # Fortschritt alle 100 Dateien
        if (i + 1) % 100 == 0 or i + 1 == len(new_files):
            print(f"     [{i + 1}/{len(new_files)}] "
                  f"NEW={imported} NEAR={review} EXACT={skipped}")

    elapsed = (datetime.now() - t_start).total_seconds()
    print()

    # Report schreiben
    report = generate_report(new_files, imported, skipped, review, elapsed)
    report_path = REPORTS_DIR / "auto_integrate_report.md"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report: {report_path}")

    print()
    print(f"{'=' * 60}")
    action = "Wuerde importieren" if DRY_RUN else "Importiert"
    print(f"  {action}: {imported} neue Dateien")
    print(f"  Review-Queue: {review} (NEAR-Matches)")
    print(f"  Uebersprungen: {skipped} (bereits in KB)")
    if not DRY_RUN and imported > 0:
        print(f"  HINWEIS: ChromaDB muss nach Import neu indexiert werden!")
        print(f"           -> docker compose down && docker compose up --build")
    print(f"  Dauer: {elapsed:.1f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
