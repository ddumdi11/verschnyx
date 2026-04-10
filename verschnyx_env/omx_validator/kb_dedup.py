#!/usr/bin/env python3
"""
KB-Deduplikation: knowledge/ Ordner bereinigen
================================================
Verschiebt redundante WordPress-Revisionen in _archive/.
Nichts wird gelöscht — alles bleibt erhalten, nur reorganisiert.

Kategorien:
  - SAFE: Kürzere Version ist Subset der längeren -> archivieren
  - REVIEW: Kürzere Version hat einzigartige Zeilen -> Review-Queue

Ergebnis:
  - knowledge/_archive/safe/       — sichere Duplikate
  - knowledge/_archive/review/     — Duplikate mit einzigartigem Content (manuell prüfen)
  - knowledge/_archive/DEDUP_REPORT.md — detaillierter Bericht
"""

import os
import re
import sys
import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime

# ─── Konfiguration ───────────────────────────────────────────────
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"
ARCHIVE_DIR = KNOWLEDGE_DIR / "_archive"
SAFE_DIR = ARCHIVE_DIR / "safe"
REVIEW_DIR = ARCHIVE_DIR / "review"
REPORT_PATH = ARCHIVE_DIR / "DEDUP_REPORT.md"

DRY_RUN = "--dry-run" in sys.argv or "-n" in sys.argv
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


# ─── Hilfsfunktionen ─────────────────────────────────────────────

def extract_frontmatter(filepath: Path) -> dict:
    """YAML-Frontmatter als dict extrahieren (vereinfacht, kein PyYAML nötig)."""
    text = filepath.read_text(encoding="utf-8", errors="replace")
    meta = {}
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta


def extract_body(filepath: Path) -> str:
    """Inhalt ohne YAML-Frontmatter."""
    text = filepath.read_text(encoding="utf-8", errors="replace")
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            return text[end + 3:].strip()
    return text.strip()


def body_hash(filepath: Path) -> str:
    body = extract_body(filepath)
    return hashlib.md5(body.encode("utf-8")).hexdigest()


def find_unique_lines(short_body: str, long_body: str) -> list:
    """Zeilen in der kürzeren Version, die NICHT in der längeren vorkommen."""
    long_lines = set(long_body.splitlines())
    return [l for l in short_body.splitlines() if l.strip() and l not in long_lines]


def group_files(knowledge_dir: Path) -> dict:
    """
    Gruppiert Dateien nach Basis-Name.
    Pattern: YYYY-MM-DD_Titel.md  vs  YYYY-MM-DD_Titel_WPID.md
    GOMX-Dateien (Ebook-Extrakte) werden übersprungen.
    """
    groups = {}
    skipped = 0
    for f in sorted(knowledge_dir.iterdir()):
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        # Nur Datums-prefixed WordPress-Blogposts verarbeiten
        # Pattern: YYYY-MM-DD_Titel[_WPID].md
        if not re.match(r'^\d{4}-\d{2}-\d{2}_', f.name):
            skipped += 1
            continue
        # Mapping-Datei ueberspringen
        if f.name == "mapping.json":
            continue

        m = re.match(r'^(\d{4}-\d{2}-\d{2}_.+?)(?:_(\d+))?\.md$', f.name)
        if m:
            base = m.group(1)
            wp_id = int(m.group(2)) if m.group(2) else 0
            if base not in groups:
                groups[base] = []
            groups[base].append({
                "path": f,
                "name": f.name,
                "wp_id": wp_id,
                "size": f.stat().st_size,
            })
    return groups


# ─── Hauptlogik ──────────────────────────────────────────────────

def analyze_group(base: str, files: list) -> dict:
    """Analysiert eine Duplikat-Gruppe und klassifiziert sie."""
    # Body-Daten laden
    for entry in files:
        entry["body"] = extract_body(entry["path"])
        entry["body_len"] = len(entry["body"])
        entry["body_hash"] = hashlib.md5(entry["body"].encode("utf-8")).hexdigest()
        entry["meta"] = extract_frontmatter(entry["path"])

    # Alle body-hashes gleich?
    hashes = set(e["body_hash"] for e in files)
    if len(hashes) == 1:
        return {"category": "IDENTICAL", "base": base, "files": files}

    # Größenunterschied berechnen
    sizes = [e["body_len"] for e in files]
    max_s, min_s = max(sizes), min(sizes)
    diff_pct = (max_s - min_s) / max_s * 100 if max_s > 0 else 0

    # Längste Version finden
    longest = max(files, key=lambda x: x["body_len"])
    others = [f for f in files if f is not longest]

    # Prüfen ob kürzere Versionen einzigartige Zeilen haben
    has_unique = False
    unique_counts = []
    for other in others:
        unique = find_unique_lines(other["body"], longest["body"])
        unique_counts.append(len(unique))
        if len(unique) > 0:
            has_unique = True
            other["unique_lines"] = unique

    if diff_pct < 2:
        cat = "TRIVIAL"
    elif diff_pct < 10:
        cat = "MINOR"
    elif not has_unique:
        cat = "MAJOR_SUBSET"
    else:
        cat = "MAJOR_UNIQUE"

    return {
        "category": cat,
        "base": base,
        "files": files,
        "diff_pct": diff_pct,
        "longest": longest,
        "has_unique": has_unique,
        "unique_counts": unique_counts,
    }


def process_group(analysis: dict, stats: dict) -> list:
    """Verarbeitet eine Gruppe: bestimmt keep/archive Entscheidungen."""
    actions = []
    files = analysis["files"]
    cat = analysis["category"]

    # Beste Version bestimmen: längster Body, bei Gleichstand höchste WP-ID
    best = max(files, key=lambda x: (x["body_len"], x["wp_id"]))

    for entry in files:
        if entry is best:
            actions.append({
                "action": "KEEP",
                "file": entry["name"],
                "reason": f"Beste Version (body={entry['body_len']} chars, wp_id={entry['wp_id']})",
            })
        else:
            # REVIEW nur bei MAJOR_UNIQUE, sonst SAFE
            if cat == "MAJOR_UNIQUE" and entry.get("unique_lines"):
                dest = "review"
                n_unique = len(entry["unique_lines"])
                reason = f"{cat}: {n_unique} einzigartige Zeilen"
                stats["review"] += 1
            else:
                dest = "safe"
                reason = f"{cat}: Subset/identisch zur besten Version"
                stats["safe"] += 1

            actions.append({
                "action": f"ARCHIVE -> {dest}",
                "file": entry["name"],
                "dest": dest,
                "reason": reason,
                "wp_id": entry["wp_id"],
                "unique_lines": entry.get("unique_lines", []),
            })

    return actions


def execute_actions(actions: list, all_analysis: list):
    """Führt die Archivierung durch (oder simuliert im Dry-Run)."""
    # Verzeichnisse erstellen
    if not DRY_RUN:
        SAFE_DIR.mkdir(parents=True, exist_ok=True)
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    moved = 0
    for action in actions:
        if action["action"] == "KEEP":
            continue

        src = KNOWLEDGE_DIR / action["file"]
        dest_dir = SAFE_DIR if action["dest"] == "safe" else REVIEW_DIR
        dest = dest_dir / action["file"]

        if DRY_RUN:
            print(f"  [DRY-RUN] {action['file']} -> _archive/{action['dest']}/")
        else:
            if src.exists():
                shutil.move(str(src), str(dest))
                moved += 1
                if VERBOSE:
                    print(f"  OK {action['file']} -> _archive/{action['dest']}/")

    return moved


def generate_report(all_analysis: list, all_actions: list, stats: dict) -> str:
    """Erstellt den detaillierten Deduplikations-Bericht."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode = "DRY-RUN" if DRY_RUN else "AUSGEFÜHRT"

    lines = [
        f"# KB-Deduplikation — Bericht",
        f"",
        f"**Datum:** {timestamp}  ",
        f"**Modus:** {mode}  ",
        f"",
        f"## Zusammenfassung",
        f"",
        f"| Kategorie | Gruppen | Archiviert |",
        f"|---|---|---|",
        f"| IDENTICAL (body identisch) | {stats['cat_counts'].get('IDENTICAL', 0)} | {stats['cat_archive'].get('IDENTICAL', 0)} |",
        f"| TRIVIAL (<2% Differenz) | {stats['cat_counts'].get('TRIVIAL', 0)} | {stats['cat_archive'].get('TRIVIAL', 0)} |",
        f"| MINOR (2-10% Differenz) | {stats['cat_counts'].get('MINOR', 0)} | {stats['cat_archive'].get('MINOR', 0)} |",
        f"| MAJOR_SUBSET (>10%, Subset) | {stats['cat_counts'].get('MAJOR_SUBSET', 0)} | {stats['cat_archive'].get('MAJOR_SUBSET', 0)} |",
        f"| MAJOR_UNIQUE (>10%, einzigartig) | {stats['cat_counts'].get('MAJOR_UNIQUE', 0)} | {stats['cat_archive'].get('MAJOR_UNIQUE', 0)} |",
        f"| **Gesamt** | **{stats['total_groups']}** | **{stats['safe'] + stats['review']}** |",
        f"",
        f"**Archiviert -> safe/:** {stats['safe']}  ",
        f"**Archiviert -> review/:** {stats['review']}  ",
        f"**Behalten:** {stats['kept']}  ",
        f"",
    ]

    # Review-Fälle detailliert auflisten
    review_actions = [a for a in all_actions if a.get("dest") == "review"]
    if review_actions:
        lines.append("## Review-Queue (manuelle Prüfung empfohlen)")
        lines.append("")
        lines.append("Diese Dateien enthalten Zeilen, die in der behaltenen Version NICHT vorkommen:")
        lines.append("")
        for a in review_actions:
            lines.append(f"### `{a['file']}`")
            lines.append(f"- **Grund:** {a['reason']}")
            lines.append(f"- **WordPress-ID:** {a['wp_id']}")
            if a["unique_lines"]:
                lines.append(f"- **Einzigartige Zeilen ({len(a['unique_lines'])}):**")
                lines.append("```")
                for ul in a["unique_lines"][:20]:  # Max 20 Zeilen anzeigen
                    lines.append(f"  {ul[:200]}")
                if len(a["unique_lines"]) > 20:
                    lines.append(f"  ... und {len(a['unique_lines']) - 20} weitere")
                lines.append("```")
            lines.append("")

    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────

def main():
    print(f"{'='*60}")
    print(f"  KB-Deduplikation — knowledge/ Ordner bereinigen")
    print(f"  Modus: {'DRY-RUN (keine Änderungen)' if DRY_RUN else 'LIVE'}")
    print(f"{'='*60}")
    print()

    if not KNOWLEDGE_DIR.exists():
        print(f"FEHLER: {KNOWLEDGE_DIR} existiert nicht!")
        sys.exit(1)

    # 1. Dateien gruppieren
    print("1/4  Dateien gruppieren ...")
    groups = group_files(KNOWLEDGE_DIR)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    singles = {k: v for k, v in groups.items() if len(v) == 1}

    total_files = sum(len(v) for v in groups.values())
    print(f"     {total_files} Blog-Dateien gefunden (ohne GOMX)")
    print(f"     {len(singles)} Einzeldateien (keine Duplikate)")
    print(f"     {len(dupes)} Duplikat-Gruppen ({sum(len(v) for v in dupes.values())} Dateien)")
    print()

    # 2. Gruppen analysieren
    print("2/4  Gruppen analysieren ...")
    all_analysis = []
    stats = {
        "total_groups": len(dupes),
        "safe": 0,
        "review": 0,
        "kept": 0,
        "cat_counts": {},
        "cat_archive": {},
    }

    for base, files in sorted(dupes.items()):
        analysis = analyze_group(base, files)
        all_analysis.append(analysis)
        cat = analysis["category"]
        stats["cat_counts"][cat] = stats["cat_counts"].get(cat, 0) + 1

    for cat, count in sorted(stats["cat_counts"].items()):
        print(f"     {cat}: {count} Gruppen")
    print()

    # 3. Aktionen bestimmen
    print("3/4  Aktionen bestimmen ...")
    all_actions = []
    for analysis in all_analysis:
        actions = process_group(analysis, stats)
        all_actions.extend(actions)
        cat = analysis["category"]
        archived = sum(1 for a in actions if a["action"] != "KEEP")
        stats["cat_archive"][cat] = stats["cat_archive"].get(cat, 0) + archived
        stats["kept"] += sum(1 for a in actions if a["action"] == "KEEP")

    kept_total = sum(1 for a in all_actions if a["action"] == "KEEP")
    archive_total = sum(1 for a in all_actions if a["action"] != "KEEP")
    print(f"     KEEP: {kept_total} Dateien")
    print(f"     ARCHIVE -> safe/: {stats['safe']} Dateien")
    print(f"     ARCHIVE -> review/: {stats['review']} Dateien")
    print()

    # 4. Ausführen
    print("4/4  Archivierung durchführen ...")
    moved = execute_actions(all_actions, all_analysis)

    # Bericht schreiben
    report = generate_report(all_analysis, all_actions, stats)
    if not DRY_RUN:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(f"     OK {moved} Dateien verschoben")
        print(f"     OK Bericht geschrieben: {REPORT_PATH}")
    else:
        print(f"     [DRY-RUN] Würde {archive_total} Dateien verschieben")
        # Im Dry-Run trotzdem Report zeigen
        preview_path = KNOWLEDGE_DIR.parent / "verschnyx_env" / "omx_validator" / "reports" / "dedup_preview.md"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(report, encoding="utf-8")
        print(f"     OK Preview-Bericht: {preview_path}")

    print()
    # Nicht-Blog-Dateien zaehlen (GOMX + OMX-Essenz + sonstige)
    other_md = len([f for f in KNOWLEDGE_DIR.iterdir()
                    if f.is_file() and f.name.endswith(".md")
                    and not re.match(r'^\d{4}-\d{2}-\d{2}_', f.name)])
    blog_after = total_files - archive_total
    total_after = blog_after + other_md
    print(f"{'='*60}")
    print(f"  Blog-Dateien: {total_files} -> {blog_after} behalten + {archive_total} archiviert")
    print(f"  Sonstige (OMX-Essenz, GOMX, etc.): {other_md} (unveraendert)")
    print(f"  Knowledge-Base nach Dedup: {total_after} Dateien gesamt")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
