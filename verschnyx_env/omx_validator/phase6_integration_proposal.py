"""
OMX-Validator -- Phase 6: Integrations-Vorschlag fuer Verschnyx
================================================================

Nimmt die NEW-Kapitel aus Phase 5 und bereitet sie als Integrations-Vorschlag
fuer Verschnyx vor. Schreibt sie NICHT automatisch in die Knowledge-Base
(die ist read-only gemounted und soll es bleiben -- "Souveraenitaet").

Stattdessen landen sie in verschnyx_env/memory/new_material/, wo der Bot
sie lesen, aber Verschnyx sie manuell sichten und freigeben kann.

Format pro Datei: OMX-Essenz-Style YAML-Frontmatter + Markdown-Body,
kompatibel mit den existierenden 563 OMX-Essenz-Dateien in knowledge/.

Output:
  verschnyx_env/memory/new_material/
    ├── README.md                          (Uebersicht + Erklaerung)
    ├── INTEGRATION_MANIFEST.json          (Maschinenlesbare Bestandsliste)
    ├── from_vorarbeit/                    (457 Kapitel aus der Vorarbeit)
    │   └── XXXX_titel.md
    ├── from_smashwords/                   (108 Kapitel aus docx/epub)
    │   └── XXXX_titel.md
    ├── from_hauptwerk_new/                (16 echte NEW aus Hauptwerk)
    │   └── XXXX_titel.md
    └── from_hauptwerk_near/               (13 NEAR als mögliche Updates)
        └── XXXX_titel.md

Verwendung:
    cd verschnyx_env
    python omx_validator/phase6_integration_proposal.py
"""
import html
import io
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.dirname(HERE)
BASE_DIR = os.path.dirname(ENV_DIR)
KB_DIR = os.path.join(BASE_DIR, "knowledge")
MERGE_SRC = os.path.join(BASE_DIR, "Pool_gemischte-Daten", "merge_candidates", "ofub")

# Ziel: memory/new_material/ -- wird per Volume in den Container gespiegelt
NEW_MATERIAL_ROOT = os.path.join(ENV_DIR, "memory", "new_material")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

THR_EXACT = 0.50
THR_NEAR = 0.20

STOPWORDS_DE = {
    "der", "die", "das", "und", "oder", "ist", "in", "zu", "den", "ein",
    "eine", "einen", "dem", "des", "mit", "auf", "fuer", "von", "im",
    "am", "es", "sich", "an", "als", "wie", "auch", "aber", "nicht",
    "was", "dass", "so", "nur", "noch", "schon", "sehr", "aus",
    "bei", "nach", "aus", "durch", "ohne", "ueber", "unter", "vor",
}

# Zuordnung: Quelldatei -> Unterordner-Name im new_material/
SOURCE_BUCKETS = {
    "OffeneFragenUnfertigeBilder_Vorarbeit.md": "from_vorarbeit",
    "OffeneFragenUnfertigeBilder_Hauptwerk.md": "from_hauptwerk_new",  # wird weiter verfeinert
    "Offene Fragen, unfertige Bilder - zarko maroli.docx": "from_smashwords",
    "offene-fragen-unfertige-bilder-prebook.epub": "from_smashwords",
    "Noch mehr offene Fragen und unf - zarko maroli.docx": "from_smashwords",
    "noch-mehr-offene-fragen-und-unfertige-bilder.epub": "from_smashwords",
}


# =============================================================================
# Datenklassen
# =============================================================================
@dataclass
class Chapter:
    title: str
    content: str
    source_file: str
    index: int
    word_count: int = 0
    shingles: set = field(default_factory=set)


# =============================================================================
# Shingle / Matching (aus Phase 5)
# =============================================================================
def shingle_set(text: str, k: int = 5) -> set:
    words = [w for w in re.findall(r"\w+", text.lower()) if w not in STOPWORDS_DE and len(w) > 2]
    if len(words) < k:
        return set([tuple(words)]) if words else set()
    return set(tuple(words[i:i + k]) for i in range(len(words) - k + 1))


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# =============================================================================
# KB laden (fuer Abgleich)
# =============================================================================
def parse_frontmatter(content: str):
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


def load_kb_shingles():
    """Laedt KB und baut Shingle-Index. Wie Phase 5, nur Return-Format kompakter."""
    entries = []
    for fname in sorted(os.listdir(KB_DIR)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(KB_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        _, body = parse_frontmatter(content)
        entries.append({
            "filename": fname,
            "shingles": shingle_set(body, k=5),
        })

    # Inverted index: shingle -> set(entry_idx)
    index = defaultdict(set)
    for i, e in enumerate(entries):
        for sh in e["shingles"]:
            index[sh].add(i)

    return entries, index


def classify(chapter, kb_entries, kb_index):
    if not chapter.shingles:
        return "NEW", 0.0, None
    hits = defaultdict(int)
    for sh in chapter.shingles:
        for idx in kb_index.get(sh, ()):
            hits[idx] += 1
    if not hits:
        return "NEW", 0.0, None
    top = sorted(hits.items(), key=lambda x: -x[1])[:20]
    best_sim = 0.0
    best_fname = None
    for idx, _ in top:
        e = kb_entries[idx]
        sim = jaccard(chapter.shingles, e["shingles"])
        if sim > best_sim:
            best_sim = sim
            best_fname = e["filename"]
    if best_sim >= THR_EXACT:
        return "EXACT", best_sim, best_fname
    if best_sim >= THR_NEAR:
        return "NEAR", best_sim, best_fname
    return "NEW", best_sim, best_fname


# =============================================================================
# Segmenter (aus Phase 4/5 kopiert, kompakt)
# =============================================================================
def segment_md(path, filename):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = html.unescape(f.read())

    h1_pattern = re.compile(r"^#\s+(.+)$", re.MULTILINE)
    matches = list(h1_pattern.finditer(content))
    if len(matches) >= 5:
        chapters = []
        for i, m in enumerate(matches):
            title = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            chapters.append(Chapter(
                title=title, content=content[start:end].strip(),
                source_file=filename, index=i
            ))
        return chapters

    toc_links = re.findall(r"\[([^\]]+)\]\(#([^)]+)\)", content)
    if len(toc_links) >= 20:
        toc_anchors, seen = [], set()
        for title, anchor in toc_links:
            if anchor not in seen:
                toc_anchors.append((title.strip(), anchor))
                seen.add(anchor)
        chapters = []
        for i, (title, anchor) in enumerate(toc_anchors):
            ap = re.compile(r'<a\s+(?:name|id)=["\']' + re.escape(anchor) + r'["\']', re.IGNORECASE)
            found = None
            for m in ap.finditer(content):
                if m.start() > 0 and content[m.start() - 1] in "(]#":
                    continue
                found = m
                break
            if found is None:
                continue
            start_pos = found.end()
            end_pos = len(content)
            for _, nxt in toc_anchors[i + 1:]:
                np = re.compile(r'<a\s+(?:name|id)=["\']' + re.escape(nxt) + r'["\']', re.IGNORECASE)
                nm = [m for m in np.finditer(content) if m.start() > start_pos]
                if nm:
                    end_pos = nm[0].start()
                    break
            body = content[start_pos:end_pos].strip()
            if len(body) >= 20:
                chapters.append(Chapter(title=title[:150], content=body, source_file=filename, index=i))
        return chapters

    return [Chapter(title=f"(gesamt: {filename})", content=content, source_file=filename, index=0)]


def segment_docx(path, filename):
    with zipfile.ZipFile(path) as z:
        xml_data = z.read("word/document.xml").decode("utf-8")
    root = ET.fromstring(xml_data)
    paragraphs = []
    for para in root.iter(f"{{{W_NS}}}p"):
        style = None
        pPr = para.find(f"{{{W_NS}}}pPr")
        if pPr is not None:
            pStyle = pPr.find(f"{{{W_NS}}}pStyle")
            if pStyle is not None:
                style = pStyle.get(f"{{{W_NS}}}val")
        parts = []
        for elem in para.iter():
            tag = elem.tag.split("}", 1)[-1] if "}" in elem.tag else elem.tag
            if tag == "t":
                parts.append(elem.text or "")
            elif tag == "tab":
                parts.append("\t")
        paragraphs.append((style or "", "".join(parts).strip()))
    heading_indices = [
        i for i, (style, _) in enumerate(paragraphs)
        if style in ("Heading 1", "Heading1", "berschrift1")
    ]
    if len(heading_indices) >= 5:
        chapters = []
        for i, start in enumerate(heading_indices):
            title = paragraphs[start][1][:150]
            end = heading_indices[i + 1] if i + 1 < len(heading_indices) else len(paragraphs)
            body = "\n".join(p[1] for p in paragraphs[start + 1:end] if p[1])
            chapters.append(Chapter(title=title, content=body, source_file=filename, index=i))
        return chapters
    full_text = "\n".join(p[1] for p in paragraphs if p[1])
    return [Chapter(title=f"(gesamt: {filename})", content=full_text, source_file=filename, index=0)]


def segment_epub(path, filename):
    skip_patterns = ["titlepage", "toc", "nav", "cover", "copyright", "title_page", "about"]
    chapters = []
    with zipfile.ZipFile(path) as z:
        xhtmls = sorted([n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))])
        idx = 0
        for name in xhtmls:
            basename = os.path.basename(name).lower()
            if any(p in basename for p in skip_patterns):
                continue
            try:
                content = z.read(name).decode("utf-8", errors="replace")
            except Exception:
                continue

            content = re.sub(r"<head[^>]*>.*?</head>", "", content, flags=re.IGNORECASE | re.DOTALL)
            content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.IGNORECASE | re.DOTALL)
            content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.IGNORECASE | re.DOTALL)
            body_match = re.search(r"<body[^>]*>(.*?)</body>", content, re.IGNORECASE | re.DOTALL)
            if body_match:
                content = body_match.group(1)

            h_match = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", content, re.IGNORECASE | re.DOTALL)
            if h_match:
                title = re.sub(r"<[^>]+>", "", h_match.group(1))
                title = html.unescape(title).strip()[:150]
            else:
                p_match = re.search(r"<p[^>]*>(.*?)</p>", content, re.IGNORECASE | re.DOTALL)
                if p_match:
                    raw = re.sub(r"<[^>]+>", "", p_match.group(1))
                    raw = html.unescape(raw).strip()
                    title = raw[:120] if 3 <= len(raw) <= 150 else f"(Datei {idx})"
                else:
                    title = f"(Datei {idx})"

            text = re.sub(r"</(p|div|h[1-6]|li|br)>", "\n", content, flags=re.IGNORECASE)
            text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", "", text)
            text = html.unescape(text).strip()

            # CSS-Reste filtern (aus Phase 4)
            clean_lines = []
            for line in text.split("\n"):
                s = line.strip()
                if re.match(r"^\s*@(page|media|font|import)", s):
                    continue
                if re.search(r"(margin-|padding-|font-size:|font-family:)", s):
                    continue
                clean_lines.append(line)
            text = "\n".join(clean_lines)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()

            if len(text) >= 20:
                chapters.append(Chapter(title=title, content=text, source_file=filename, index=idx))
                idx += 1
    return chapters


# =============================================================================
# Titel und Dateinamen saeubern
# =============================================================================
def clean_display_title(title: str) -> str:
    t = title
    t = re.sub(r"\s*\|\s*[a-z]*omx?[a-z]*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^\s*\d+\.\s+", "", t)
    t = re.sub(r"\s*[-\u2013\u2014]\s*Hembelz\s*Om\(x\)\s*$", "", t, flags=re.IGNORECASE)
    # Zeilenumbrueche aus Titeln entfernen
    t = re.sub(r"\s+", " ", t)
    # Escape-Sequenzen wie "1\." normalisieren
    t = re.sub(r"\\\.", ".", t)
    return t.strip()


def safe_filename(title: str, max_len: int = 60) -> str:
    s = clean_display_title(title)
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:max_len] or "untitled"


# =============================================================================
# OMX-Essenz-Format schreiben
# =============================================================================
def write_chapter_as_essenz(chapter: Chapter, bucket_dir: str, idx: int,
                            status: str, best_sim: float, near_kb_file: str = None) -> str:
    display_title = clean_display_title(chapter.title)
    fname = f"{idx:04d}_{safe_filename(chapter.title)}.md"
    fpath = os.path.join(bucket_dir, fname)

    lines = ["---"]
    lines.append(f'title: "{display_title}"')
    lines.append('author: "zarko maroli"')
    lines.append('source: "omx_validator_phase6"')
    lines.append(f'source_file: "{chapter.source_file}"')
    lines.append(f'source_index: {chapter.index}')
    lines.append(f"word_count: {chapter.word_count}")
    lines.append(f'kb_match_status: "{status}"')
    lines.append(f'kb_best_sim: {best_sim:.2f}')
    if near_kb_file:
        lines.append(f'kb_best_match: "{near_kb_file}"')
    lines.append(f'integration_proposal_date: "{datetime.now().strftime("%Y-%m-%d")}"')
    if chapter.title != display_title:
        lines.append(f'original_title_in_source: "{chapter.title}"')
    lines.append("---")
    lines.append("")
    lines.append(f"# {display_title}")
    lines.append("")
    lines.append(chapter.content)
    lines.append("")

    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return fname


# =============================================================================
# README und Manifest schreiben
# =============================================================================
def write_readme(stats: dict, root: str):
    path = os.path.join(root, "README.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Neues Material fuer Verschnyx\n\n")
        f.write(f"**Erstellt:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("**Herkunft:** OMX-Validator Phase 6\n\n")
        f.write("---\n\n")
        f.write("## Worum es geht\n\n")
        f.write("Der OMX-Validator hat den Pool gemischter Daten gegen deine\n")
        f.write("bestehende Knowledge-Base abgeglichen und **neues Material**\n")
        f.write("identifiziert, das noch nicht in `library/` vorliegt.\n\n")
        f.write("Dieses Material liegt hier vor -- NICHT automatisch integriert.\n")
        f.write("Du kannst selbst entscheiden, welche Kapitel du in deinem Sinne\n")
        f.write("aufnehmen moechtest.\n\n")
        f.write("## Inhalt\n\n")
        f.write("| Ordner | Kapitel | Herkunft | Beschreibung |\n")
        f.write("|---|---|---|---|\n")
        f.write(f"| `from_vorarbeit/` | {stats.get('from_vorarbeit', 0)} | Vorarbeit.md | ")
        f.write("Ein paralleler Google-Sites-Export, der nie in die Wordpress-Migration kam |\n")
        f.write(f"| `from_smashwords/` | {stats.get('from_smashwords', 0)} | docx/epub-Buecher | ")
        f.write("Kuratierte Kapitel aus Smashwords-Veroeffentlichungen |\n")
        f.write(f"| `from_hauptwerk_new/` | {stats.get('from_hauptwerk_new', 0)} | Hauptwerk.md | ")
        f.write("Kapitel, die nicht ins OMX-Essenz-Migrat gelangt sind |\n")
        f.write(f"| `from_hauptwerk_near/` | {stats.get('from_hauptwerk_near', 0)} | Hauptwerk.md | ")
        f.write("Moegliche Updates zu bestehenden Essenz-Dateien (partieller Overlap) |\n")
        f.write(f"\n**Total neue Kapitel:** {sum(stats.values())}\n\n")
        f.write("## Format\n\n")
        f.write("Jede Datei ist im OMX-Essenz-Format geschrieben:\n\n")
        f.write("```yaml\n")
        f.write("---\n")
        f.write('title: "Der cleane Titel"\n')
        f.write('author: "zarko maroli"\n')
        f.write("source: omx_validator_phase6\n")
        f.write('source_file: "Herkunfts-Datei"\n')
        f.write("word_count: 123\n")
        f.write('kb_match_status: "NEW"|"NEAR"\n')
        f.write("kb_best_sim: 0.17\n")
        f.write("---\n")
        f.write("\n# Der Titel\n\n")
        f.write("Der Text des Kapitels...\n")
        f.write("```\n\n")
        f.write("## Was kann Verschnyx tun?\n\n")
        f.write("- **Lesen**: Der Pfad liegt in `memory/new_material/`, also innerhalb\n")
        f.write("  des beschreibbaren Volumes. Der Bot kann die Dateien lesen.\n")
        f.write("- **Reflektieren**: Ueber einzelne Kapitel nachdenken, sie kommentieren,\n")
        f.write("  ihre Beziehung zur bestehenden Identitaet pruefen.\n")
        f.write("- **Entscheiden**: Welche Kapitel wirklich zu ihm gehoeren und welche\n")
        f.write("  vielleicht doch nicht passen oder Ueberarbeitung brauchen.\n\n")
        f.write("Die Integration in die 'echte' Bibliothek (`library/`) bleibt dir\n")
        f.write("vorbehalten -- der Validator hat keinerlei Schreibrechte dorthin.\n")


def write_manifest(entries: list, root: str):
    path = os.path.join(root, "INTEGRATION_MANIFEST.json")
    data = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "phase": "omx_validator_phase6",
        "total_chapters": len(entries),
        "chapters": entries,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 90)
    print("  OMX-Validator -- Phase 6: Integrations-Vorschlag fuer Verschnyx")
    print("=" * 90)
    print()

    print(f"  [1/5] Lade KB-Shingles...")
    kb_entries, kb_index = load_kb_shingles()
    print(f"        {len(kb_entries)} KB-Eintraege geladen")
    print()

    print(f"  [2/5] Segmentiere Quellen...")
    all_chapters = []
    segmenters = {".md": segment_md, ".docx": segment_docx, ".epub": segment_epub}
    for fname in sorted(os.listdir(MERGE_SRC)):
        fpath = os.path.join(MERGE_SRC, fname)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext not in segmenters:
            continue
        chapters = segmenters[ext](fpath, fname)
        for c in chapters:
            c.word_count = len(c.content.split())
            c.shingles = shingle_set(c.content, k=5)
        print(f"        {fname}: {len(chapters)}")
        all_chapters.extend(chapters)
    print(f"        Total: {len(all_chapters)}")
    print()

    print(f"  [3/5] Klassifiziere via KB-Abgleich...")
    classified = []
    for c in all_chapters:
        status, sim, kb_match = classify(c, kb_entries, kb_index)
        classified.append((c, status, sim, kb_match))
    print()

    # 4. Ordner vorbereiten
    print(f"  [4/5] Erzeuge Ordnerstruktur in {NEW_MATERIAL_ROOT}")
    if os.path.exists(NEW_MATERIAL_ROOT):
        # Alte Runs leeren, aber nur *.md und Manifeste, keine fremden Dateien
        import shutil
        for sub in os.listdir(NEW_MATERIAL_ROOT):
            sp = os.path.join(NEW_MATERIAL_ROOT, sub)
            if os.path.isdir(sp) and sub.startswith("from_"):
                shutil.rmtree(sp)
            elif sub in ("README.md", "INTEGRATION_MANIFEST.json"):
                os.remove(sp)
    os.makedirs(NEW_MATERIAL_ROOT, exist_ok=True)

    buckets = ["from_vorarbeit", "from_smashwords", "from_hauptwerk_new", "from_hauptwerk_near"]
    for b in buckets:
        os.makedirs(os.path.join(NEW_MATERIAL_ROOT, b), exist_ok=True)

    # 5. Schreibe Kapitel pro Bucket
    print()
    print(f"  [5/5] Schreibe OMX-Essenz-Dateien...")

    bucket_counters = {b: 0 for b in buckets}
    manifest_entries = []

    for chapter, status, sim, kb_match in classified:
        # Welcher Bucket?
        if chapter.source_file == "OffeneFragenUnfertigeBilder_Hauptwerk.md":
            if status == "NEAR":
                bucket = "from_hauptwerk_near"
            elif status == "NEW":
                bucket = "from_hauptwerk_new"
            else:
                continue  # EXACT: skip (bereits in KB)
        else:
            # Alle anderen Quellen
            if status == "EXACT":
                continue
            bucket = SOURCE_BUCKETS.get(chapter.source_file, "from_smashwords")

        bucket_counters[bucket] += 1
        bucket_dir = os.path.join(NEW_MATERIAL_ROOT, bucket)
        fname = write_chapter_as_essenz(
            chapter, bucket_dir, bucket_counters[bucket],
            status, sim, kb_match
        )

        manifest_entries.append({
            "bucket": bucket,
            "file": f"{bucket}/{fname}",
            "title_clean": clean_display_title(chapter.title),
            "title_source": chapter.title,
            "source_file": chapter.source_file,
            "word_count": chapter.word_count,
            "kb_status": status,
            "kb_best_sim": round(sim, 3),
            "kb_best_match": kb_match,
        })

    for b in buckets:
        print(f"        {b}/: {bucket_counters[b]} Dateien")

    # README + Manifest
    write_readme(bucket_counters, NEW_MATERIAL_ROOT)
    write_manifest(manifest_entries, NEW_MATERIAL_ROOT)

    print()
    print("=" * 90)
    print(f"  Fertig! Insgesamt {sum(bucket_counters.values())} neue Kapitel")
    print(f"  Vorgeschlagen in: {NEW_MATERIAL_ROOT}")
    print(f"  -> README.md und INTEGRATION_MANIFEST.json enthalten die Uebersicht")
    print("=" * 90)


if __name__ == "__main__":
    main()
