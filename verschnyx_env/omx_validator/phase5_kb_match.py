"""
OMX-Validator -- Phase 5: Abgleich mit Knowledge-Base
======================================================

Vergleicht alle Kapitel aus Pool_gemischte-Daten/merge_candidates/ mit
der bestehenden Knowledge-Base in wordpress-blog_parsen/knowledge/.

Ziel: Herausfinden, welche Inhalte NEU sind (nicht in der KB) und
welche bereits vorhanden sind (redundant oder als Near-Match).

Performance: Inverted-Shingle-Index fuer schnelles Candidate-Lookup
statt brute-force O(N*M) Vergleich.

Output:
  verschnyx_env/omx_validator/reports/phase5_kb_match/
    ├── summary.md
    ├── new_chapters.md        (die Goldmine!)
    ├── near_matches.md        (aehnlich aber nicht identisch)
    └── redundant.md           (schon in KB)

Verwendung:
    cd verschnyx_env
    python omx_validator/phase5_kb_match.py
"""
import html
import io
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
REPORTS_DIR = os.path.join(HERE, "reports", "phase5_kb_match")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# Schwellwerte
THR_EXACT = 0.50     # content_sim >= 0.50 -> bereits in KB
THR_NEAR = 0.20      # 0.20 <= content_sim < 0.50 -> Near-Match (manuell pruefen)
# < 0.20 -> NEU

STOPWORDS_DE = {
    "der", "die", "das", "und", "oder", "ist", "in", "zu", "den", "ein",
    "eine", "einen", "dem", "des", "mit", "auf", "fuer", "von", "im",
    "am", "es", "sich", "an", "als", "wie", "auch", "aber", "nicht",
    "was", "dass", "so", "nur", "noch", "schon", "sehr", "aus",
    "bei", "nach", "aus", "durch", "ohne", "ueber", "unter", "vor",
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


@dataclass
class KBEntry:
    filename: str
    kb_kind: str  # "blog" | "omx_essenz" | "other"
    title: str
    body: str
    shingles: set = field(default_factory=set)


@dataclass
class MatchResult:
    chapter: Chapter
    best_kb: KBEntry = None
    best_sim: float = 0.0
    status: str = "NEW"  # "NEW" | "NEAR" | "EXACT"
    # Top 3 Alternativen fuer Debugging
    alternates: list = field(default_factory=list)


# =============================================================================
# Shingle + Jaccard (aus Phase 3/4)
# =============================================================================
def normalize_title(title: str) -> str:
    t = re.sub(r"\|[a-z]*omx?[a-z]*", "", title, flags=re.IGNORECASE)
    t = re.sub(r"^\s*\d+\.\s*", "", t)
    t = re.sub(r"[^a-zA-Z0-9\u00c0-\u017f\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


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
# KB-Loader
# =============================================================================
def parse_frontmatter(content: str):
    """Extrahiert YAML-Frontmatter-Titel und Body aus einer .md-Datei."""
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


def load_kb(kb_dir: str) -> list:
    """Laedt alle .md-Dateien aus knowledge/ und baut KBEntry-Liste."""
    entries = []
    for fname in sorted(os.listdir(kb_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(kb_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"  [warn] {fname}: {e}")
            continue

        title, body = parse_frontmatter(content)
        if title is None:
            # Kein Frontmatter -- nimm ersten Heading oder Dateinamen
            h1_m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            title = h1_m.group(1).strip() if h1_m else os.path.splitext(fname)[0]

        if fname.startswith("OMX-Essenz_"):
            kind = "omx_essenz"
        elif re.match(r"^\d{4}-\d{2}-\d{2}_", fname):
            kind = "blog"
        else:
            kind = "other"

        entries.append(KBEntry(
            filename=fname, kb_kind=kind, title=title, body=body
        ))

    return entries


# =============================================================================
# Inverted Shingle Index
# =============================================================================
def build_shingle_index(entries):
    """Baut Map: shingle -> set(entry_idx), fuer schnelles Candidate-Lookup."""
    index = defaultdict(set)
    for i, e in enumerate(entries):
        e.shingles = shingle_set(e.body, k=5)
        for sh in e.shingles:
            index[sh].add(i)
    return index


def find_kb_candidates(chapter: Chapter, entries, index, top_k=20):
    """
    Findet die top_k KB-Eintraege mit den meisten gemeinsamen Shingles.
    """
    if not chapter.shingles:
        return []
    hit_counts = defaultdict(int)
    for sh in chapter.shingles:
        for idx in index.get(sh, ()):
            hit_counts[idx] += 1
    if not hit_counts:
        return []
    # Top-K nach Shingle-Overlap
    top = sorted(hit_counts.items(), key=lambda x: -x[1])[:top_k]
    return [idx for idx, _ in top]


def classify_chapter(chapter: Chapter, entries, index):
    """Bestimmt Status eines Kapitels: EXACT/NEAR/NEW."""
    candidate_idxs = find_kb_candidates(chapter, entries, index)
    if not candidate_idxs:
        return MatchResult(chapter=chapter, best_sim=0.0, status="NEW")

    # Exakte Jaccard gegen die Top-Kandidaten berechnen
    scored = []
    for idx in candidate_idxs:
        entry = entries[idx]
        sim = jaccard(chapter.shingles, entry.shingles)
        scored.append((sim, entry))

    scored.sort(key=lambda x: -x[0])
    best_sim, best_entry = scored[0]

    if best_sim >= THR_EXACT:
        status = "EXACT"
    elif best_sim >= THR_NEAR:
        status = "NEAR"
    else:
        status = "NEW"

    alternates = [(s, e.filename) for s, e in scored[1:4] if s > 0.1]

    return MatchResult(
        chapter=chapter,
        best_kb=best_entry,
        best_sim=best_sim,
        status=status,
        alternates=alternates,
    )


# =============================================================================
# Quellen-Segmenter (aus phase4_merge.py kopiert)
# =============================================================================
def read_md(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return html.unescape(f.read())


def segment_md(path: str, filename: str):
    content = read_md(path)

    h1_pattern = re.compile(r"^#\s+(.+)$", re.MULTILINE)
    matches = list(h1_pattern.finditer(content))
    if len(matches) >= 5:
        chapters = []
        for i, m in enumerate(matches):
            title = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[start:end].strip()
            chapters.append(Chapter(title=title, content=body, source_file=filename, index=i))
        return chapters

    # HTML-Anker-Strategie
    toc_links = re.findall(r"\[([^\]]+)\]\(#([^)]+)\)", content)
    if len(toc_links) >= 20:
        toc_anchors, seen = [], set()
        for title, anchor in toc_links:
            if anchor not in seen:
                toc_anchors.append((title.strip(), anchor))
                seen.add(anchor)
        chapters = []
        for i, (title, anchor) in enumerate(toc_anchors):
            anchor_pattern = re.compile(
                r'<a\s+(?:name|id)=["\']' + re.escape(anchor) + r'["\']',
                re.IGNORECASE,
            )
            found = None
            for m in anchor_pattern.finditer(content):
                if m.start() > 0 and content[m.start() - 1] in "(]#":
                    continue
                found = m
                break
            if found is None:
                continue
            start_pos = found.end()
            end_pos = len(content)
            for _, next_anchor in toc_anchors[i + 1:]:
                next_p = re.compile(
                    r'<a\s+(?:name|id)=["\']' + re.escape(next_anchor) + r'["\']',
                    re.IGNORECASE,
                )
                next_matches = [m for m in next_p.finditer(content) if m.start() > start_pos]
                if next_matches:
                    end_pos = next_matches[0].start()
                    break
            body = content[start_pos:end_pos].strip()
            if len(body) >= 20:
                chapters.append(Chapter(title=title[:150], content=body, source_file=filename, index=i))
        return chapters

    return [Chapter(title=f"(gesamt: {filename})", content=content, source_file=filename, index=0)]


def segment_docx(path: str, filename: str):
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


def segment_epub(path: str, filename: str):
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

            # Clean body text (vereinfacht)
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

            if len(text) >= 20:
                chapters.append(Chapter(title=title, content=text, source_file=filename, index=idx))
                idx += 1
    return chapters


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 90)
    print("  OMX-Validator -- Phase 5: Abgleich mit Knowledge-Base")
    print("=" * 90)
    print()

    # 1. KB laden
    print(f"  [1/4] Lade Knowledge-Base aus {KB_DIR}...")
    kb_entries = load_kb(KB_DIR)
    print(f"        -> {len(kb_entries)} KB-Eintraege")

    # Statistik
    kinds = defaultdict(int)
    for e in kb_entries:
        kinds[e.kb_kind] += 1
    for k, v in kinds.items():
        print(f"        {k}: {v}")
    print()

    # 2. Inverted Index bauen
    print("  [2/4] Baue Inverted-Shingle-Index...")
    index = build_shingle_index(kb_entries)
    print(f"        -> {len(index):,} unique shingles")
    print()

    # 3. Quellen-Kapitel einlesen
    print("  [3/4] Segmentiere Quellen-Kapitel...")
    all_chapters = []
    segmenters = {".md": segment_md, ".docx": segment_docx, ".epub": segment_epub}
    for fname in sorted(os.listdir(MERGE_SRC)):
        fpath = os.path.join(MERGE_SRC, fname)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext not in segmenters:
            continue
        try:
            chapters = segmenters[ext](fpath, fname)
        except Exception as e:
            print(f"        [FEHLER] {fname}: {e}")
            continue
        for c in chapters:
            c.word_count = len(c.content.split())
            c.shingles = shingle_set(c.content, k=5)
        print(f"        {fname}: {len(chapters)} Kapitel")
        all_chapters.extend(chapters)
    print(f"        Total: {len(all_chapters)} Kapitel")
    print()

    # 4. Klassifizierung
    print("  [4/4] Klassifiziere Kapitel via KB-Abgleich...")
    results = []
    for i, c in enumerate(all_chapters):
        if (i + 1) % 100 == 0:
            print(f"        ... {i + 1}/{len(all_chapters)}")
        r = classify_chapter(c, kb_entries, index)
        results.append(r)

    # Statistik
    by_status = defaultdict(list)
    for r in results:
        by_status[r.status].append(r)

    print()
    print("=" * 90)
    print("  Ergebnis")
    print("=" * 90)
    print()
    print(f"  NEU        (in KB nicht gefunden, sim < {THR_NEAR}): {len(by_status['NEW']):>5d}")
    print(f"  NEAR-MATCH (partieller Overlap, {THR_NEAR} <= sim < {THR_EXACT}):      {len(by_status['NEAR']):>5d}")
    print(f"  EXACT      (bereits in KB, sim >= {THR_EXACT}):      {len(by_status['EXACT']):>5d}")
    print()

    # Pro Quelle Aufschluesselung
    print("  Nach Quell-Datei:")
    per_source = defaultdict(lambda: defaultdict(int))
    for r in results:
        per_source[r.chapter.source_file][r.status] += 1
    for fname in sorted(per_source.keys()):
        counts = per_source[fname]
        total = sum(counts.values())
        new_pct = (counts.get("NEW", 0) / total * 100) if total else 0
        short = fname[:50] if len(fname) <= 50 else fname[:47] + "..."
        print(
            f"    {short:<50s}  NEW={counts.get('NEW',0):>4d}  "
            f"NEAR={counts.get('NEAR',0):>4d}  EXACT={counts.get('EXACT',0):>4d}  "
            f"({new_pct:.0f}% neu)"
        )
    print()

    # Report-Dateien schreiben
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # summary.md
    summary_path = os.path.join(REPORTS_DIR, "summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"# Phase 5 -- KB-Abgleich Summary\n\n")
        f.write(f"**Erzeugt:** {datetime.now().isoformat(timespec='seconds')}\n\n")
        f.write(f"**Knowledge-Base:** {len(kb_entries)} Eintraege\n")
        for k, v in kinds.items():
            f.write(f"- {k}: {v}\n")
        f.write(f"\n**Total analysierte Kapitel:** {len(all_chapters)}\n\n")
        f.write("## Klassifizierung\n\n")
        f.write(f"| Status | Anzahl | Bedeutung |\n|---|---|---|\n")
        f.write(f"| NEW | {len(by_status['NEW'])} | In KB nicht gefunden (sim < {THR_NEAR}) |\n")
        f.write(f"| NEAR | {len(by_status['NEAR'])} | Partieller Overlap ({THR_NEAR}-{THR_EXACT}) |\n")
        f.write(f"| EXACT | {len(by_status['EXACT'])} | Bereits in KB (sim >= {THR_EXACT}) |\n\n")
        f.write("## Aufschluesselung nach Quelle\n\n")
        f.write("| Quelle | NEW | NEAR | EXACT | % neu |\n|---|---|---|---|---|\n")
        for fname in sorted(per_source.keys()):
            counts = per_source[fname]
            total = sum(counts.values())
            new_pct = (counts.get("NEW", 0) / total * 100) if total else 0
            f.write(
                f"| `{fname}` | {counts.get('NEW',0)} | {counts.get('NEAR',0)} | "
                f"{counts.get('EXACT',0)} | {new_pct:.0f}% |\n"
            )

    # new_chapters.md
    new_path = os.path.join(REPORTS_DIR, "new_chapters.md")
    new_results = sorted(by_status["NEW"], key=lambda r: -r.chapter.word_count)
    with open(new_path, "w", encoding="utf-8") as f:
        f.write(f"# Neue Kapitel (nicht in KB)\n\n")
        f.write(f"**{len(new_results)} Kapitel** haben keinen Near-Match in der KB.\n")
        f.write(f"Sortiert nach Wortanzahl absteigend.\n\n")
        f.write("| # | Titel | Quelle | Woerter | Best-Sim |\n|---|---|---|---|---|\n")
        for i, r in enumerate(new_results, 1):
            title = r.chapter.title[:70].replace("|", "\\|").replace("\n", " ")
            src = r.chapter.source_file[:30]
            f.write(f"| {i} | {title} | {src} | {r.chapter.word_count} | {r.best_sim:.2f} |\n")

    # near_matches.md
    near_path = os.path.join(REPORTS_DIR, "near_matches.md")
    near_results = sorted(by_status["NEAR"], key=lambda r: -r.best_sim)
    with open(near_path, "w", encoding="utf-8") as f:
        f.write(f"# Near-Matches (partieller Overlap mit KB)\n\n")
        f.write(f"**{len(near_results)} Kapitel** haben einen partiellen Overlap zur KB.\n")
        f.write(f"Diese koennten aktualisierte Versionen sein oder teilweise Neuinhalt enthalten.\n")
        f.write(f"Sortiert nach Similarity absteigend.\n\n")
        f.write("| # | Sim | Titel (Quelle) | Quelle | Best KB-Match |\n|---|---|---|---|---|\n")
        for i, r in enumerate(near_results, 1):
            title = r.chapter.title[:50].replace("|", "\\|").replace("\n", " ")
            src = r.chapter.source_file[:25]
            kb_fn = r.best_kb.filename[:40] if r.best_kb else "-"
            f.write(f"| {i} | {r.best_sim:.2f} | {title} | {src} | {kb_fn} |\n")

    # redundant.md
    red_path = os.path.join(REPORTS_DIR, "redundant.md")
    red_results = sorted(by_status["EXACT"], key=lambda r: -r.best_sim)
    with open(red_path, "w", encoding="utf-8") as f:
        f.write(f"# Redundante Kapitel (bereits in KB)\n\n")
        f.write(f"**{len(red_results)} Kapitel** sind bereits in der KB vorhanden.\n\n")
        f.write("| # | Sim | Titel (Quelle) | Quelle | KB-Match |\n|---|---|---|---|---|\n")
        for i, r in enumerate(red_results, 1):
            title = r.chapter.title[:50].replace("|", "\\|").replace("\n", " ")
            src = r.chapter.source_file[:25]
            kb_fn = r.best_kb.filename[:40] if r.best_kb else "-"
            f.write(f"| {i} | {r.best_sim:.2f} | {title} | {src} | {kb_fn} |\n")

    print(f"  Reports geschrieben nach: {REPORTS_DIR}")
    print(f"    - summary.md")
    print(f"    - new_chapters.md      ({len(by_status['NEW'])} Eintraege)")
    print(f"    - near_matches.md      ({len(by_status['NEAR'])} Eintraege)")
    print(f"    - redundant.md         ({len(by_status['EXACT'])} Eintraege)")
    print()
    print("=" * 90)


if __name__ == "__main__":
    main()
