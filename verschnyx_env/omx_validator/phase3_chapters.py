"""
OMX-Validator -- Phase 3: Kapitel-Segmentierung + Cross-Source-Matching
=======================================================================

Zerlegt jede Quelldatei in Mini-Kapitel und baut eine Matrix, die zeigt,
welche Kapitel in welchen Quellen vorkommen.

Das ist der erste Schritt zum Quality-Aware Merge: Wir koennen keinen
sinnvollen Merge machen, ohne zu wissen, welche Blocks in verschiedenen
Quellen "dasselbe Kapitel" darstellen.

Verwendung:
    cd verschnyx_env
    python omx_validator/phase3_chapters.py
"""
import html
import io
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.dirname(HERE)
BASE_DIR = os.path.dirname(ENV_DIR)
MERGE_DIR = os.path.join(BASE_DIR, "Pool_gemischte-Daten", "merge_candidates", "ofub")
REPORTS_DIR = os.path.join(HERE, "reports")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# =============================================================================
# Datenklassen
# =============================================================================
@dataclass
class Chapter:
    title: str
    content: str
    source_file: str
    index: int  # Position innerhalb der Quelldatei
    word_count: int = 0
    fingerprint: str = ""


@dataclass
class SourceDoc:
    filename: str
    source_type: str
    chapters: list = field(default_factory=list)
    strategy_used: str = ""


# =============================================================================
# Segmenter
# =============================================================================
def segment_md(path: str, filename: str):
    """
    Segmentiert eine Markdown-Datei in Kapitel.
    Strategie 1: Split an H1-Headings.
    Strategie 2: Split an HTML-Anker-Tags (fuer Google-Sites-Export)
    Strategie 3 (Fallback): Split an Zeilen, die wie nummerierte Titel aussehen.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = html.unescape(f.read())

    # Strategie 1: H1-Headings
    h1_pattern = re.compile(r"^#\s+(.+)$", re.MULTILINE)
    matches = list(h1_pattern.finditer(content))

    if len(matches) >= 5:
        chapters = []
        for i, m in enumerate(matches):
            title = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[start:end].strip()
            chapters.append(Chapter(
                title=title, content=body, source_file=filename, index=i
            ))
        return chapters, "md_h1"

    # Strategie 2: HTML-Anker-Tags via TOC-Linkreferenzen
    # (Google-Sites-Export: <a name="Top_of_section_XXXX_html"></a>)
    toc_links = re.findall(
        r"\[([^\]]+)\]\(#([^)]+)\)", content
    )
    if len(toc_links) >= 20:
        # Sammle Anchor-IDs aus TOC
        toc_anchors = []
        seen = set()
        for title, anchor in toc_links:
            if anchor not in seen:
                toc_anchors.append((title.strip(), anchor))
                seen.add(anchor)

        # Finde jeden Anchor im Body (ausserhalb des TOC)
        chapters = []
        for i, (title, anchor) in enumerate(toc_anchors):
            # Suche nach <a name="anchor">, <a id="anchor">, oder Anchor im Text
            anchor_pattern = re.compile(
                r'<a\s+(?:name|id)=["\']' + re.escape(anchor) + r'["\']',
                re.IGNORECASE,
            )
            # Ueberspringe Matches, die noch im TOC-Bereich liegen (also Links selber)
            # Finde das ERSTE Match NACH einer initialen TOC-Region
            found = None
            for m in anchor_pattern.finditer(content):
                # Vermeide, dass wir einen Markdown-Link-Target matchen
                pos = m.start()
                # Wenn das Zeichen direkt davor ein '(' oder '#' oder ']' ist -> Link, kein Anker
                if pos > 0 and content[pos - 1] in "(]#":
                    continue
                found = m
                break

            if found is None:
                continue

            start_pos = found.end()
            # Ende: naechster Anker aus TOC, oder Dateiende
            end_pos = len(content)
            for j, (_, next_anchor) in enumerate(toc_anchors[i + 1:]):
                next_pattern = re.compile(
                    r'<a\s+(?:name|id)=["\']' + re.escape(next_anchor) + r'["\']',
                    re.IGNORECASE,
                )
                next_matches = [
                    m for m in next_pattern.finditer(content)
                    if m.start() > start_pos
                ]
                if next_matches:
                    end_pos = next_matches[0].start()
                    break

            body = content[start_pos:end_pos].strip()
            if len(body) < 20:
                continue
            chapters.append(Chapter(
                title=title[:150],
                content=body,
                source_file=filename,
                index=i,
            ))

        if len(chapters) >= 5:
            return chapters, "md_html_anchors"

    # Strategie 3: nummerierte Titel wie "1. Titel|omx" oder "2. Etwas"
    num_pattern = re.compile(
        r"^(\d+)\.\s+(.+\|[a-z]*omx?[a-z]*)$",
        re.MULTILINE | re.IGNORECASE,
    )
    matches = list(num_pattern.finditer(content))
    if len(matches) >= 5:
        chapters = []
        for i, m in enumerate(matches):
            title = m.group(2).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[start:end].strip()
            chapters.append(Chapter(
                title=title, content=body, source_file=filename, index=i
            ))
        return chapters, "md_numbered_omx"

    # Strategie 4: Split an horizontalen Linien
    hr_parts = re.split(r"^\s*---\s*$", content, flags=re.MULTILINE)
    if len(hr_parts) >= 5:
        chapters = []
        for i, part in enumerate(hr_parts):
            part = part.strip()
            if len(part) < 50:
                continue
            lines = [l.strip() for l in part.split("\n") if l.strip()]
            title = lines[0] if lines else f"(Abschnitt {i})"
            chapters.append(Chapter(
                title=title[:100], content=part, source_file=filename,
                index=i,
            ))
        if len(chapters) >= 5:
            return chapters, "md_hr_split"

    # Fallback: eine einzige "Kapitel"-Einheit
    return [Chapter(
        title=f"(gesamt: {filename})",
        content=content,
        source_file=filename,
        index=0,
    )], "md_monolith"


def segment_epub(path: str, filename: str):
    """
    Segmentiert eine EPUB-Datei: Jede XHTML-Datei ist ein Kapitel.
    Ueberspringt bekannte Struktur-Dateien (titlepage, toc, nav, etc).
    """
    skip_patterns = [
        "titlepage", "toc", "nav", "cover", "copyright",
        "title_page", "about",
    ]

    chapters = []
    with zipfile.ZipFile(path) as z:
        xhtmls = sorted([
            n for n in z.namelist()
            if n.lower().endswith((".xhtml", ".html", ".htm"))
        ])

        idx = 0
        for name in xhtmls:
            basename = os.path.basename(name).lower()
            if any(p in basename for p in skip_patterns):
                continue
            try:
                content = z.read(name).decode("utf-8", errors="replace")
            except Exception:
                continue

            # Title extrahieren: erstes <h1>/<h2>/<h3>, sonst <title>
            title_match = re.search(
                r"<(h[1-3]|title)[^>]*>([^<]+)</\1>", content, re.IGNORECASE
            )
            if title_match:
                title = html.unescape(title_match.group(2)).strip()
            else:
                # Ersten fett gesetzten Text oder ersten <p>
                first_p = re.search(
                    r"<p[^>]*>([^<]+)</p>", content, re.IGNORECASE
                )
                title = html.unescape(first_p.group(1))[:80].strip() if first_p else f"(Datei {idx})"

            # Clean text
            text = re.sub(r"</(p|div|h[1-6]|li|br)>", "\n", content, flags=re.IGNORECASE)
            text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", "", text)
            text = html.unescape(text).strip()

            if len(text) < 20:  # Leere oder zu kurze "Kapitel" skippen
                continue

            chapters.append(Chapter(
                title=title[:100], content=text,
                source_file=filename, index=idx,
            ))
            idx += 1

    return chapters, "epub_per_xhtml"


def segment_docx(path: str, filename: str):
    """
    Segmentiert eine DOCX-Datei.
    Strategie 1: Split an Paragraphs mit 'Heading 1' Style.
    Strategie 2 (Fallback): Split an nummerierten Paragraphs.
    """
    with zipfile.ZipFile(path) as z:
        xml_data = z.read("word/document.xml").decode("utf-8")

    root = ET.fromstring(xml_data)

    # Sammle alle Absaetze mit Style + Text
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
        text = "".join(parts).strip()
        paragraphs.append((style or "", text))

    # Strategie 1: Heading 1 als Kapitelgrenze
    heading_indices = [
        i for i, (style, _) in enumerate(paragraphs)
        if style in ("Heading 1", "Heading1", "berschrift1")
    ]

    if len(heading_indices) >= 5:
        chapters = []
        for i, start in enumerate(heading_indices):
            title = paragraphs[start][1][:100]
            end = heading_indices[i + 1] if i + 1 < len(heading_indices) else len(paragraphs)
            body = "\n".join(p[1] for p in paragraphs[start + 1:end] if p[1])
            chapters.append(Chapter(
                title=title, content=body, source_file=filename, index=i,
            ))
        return chapters, "docx_heading1"

    # Strategie 2: Nummerierte Titel
    num_pattern = re.compile(r"^(\d+)\.\s+(.{3,200})$")
    title_indices = []
    for i, (_, text) in enumerate(paragraphs):
        if num_pattern.match(text):
            title_indices.append(i)

    if len(title_indices) >= 5:
        chapters = []
        for i, start in enumerate(title_indices):
            title = paragraphs[start][1][:100]
            end = title_indices[i + 1] if i + 1 < len(title_indices) else len(paragraphs)
            body = "\n".join(p[1] for p in paragraphs[start + 1:end] if p[1])
            chapters.append(Chapter(
                title=title, content=body, source_file=filename, index=i,
            ))
        return chapters, "docx_numbered"

    # Fallback
    full_text = "\n".join(p[1] for p in paragraphs if p[1])
    return [Chapter(
        title=f"(gesamt: {filename})",
        content=full_text,
        source_file=filename,
        index=0,
    )], "docx_monolith"


# =============================================================================
# Fingerprinting & Matching
# =============================================================================
STOPWORDS_DE = {
    "der", "die", "das", "und", "oder", "ist", "in", "zu", "den", "ein",
    "eine", "einen", "dem", "des", "mit", "auf", "fuer", "von", "im",
    "am", "es", "sich", "an", "als", "wie", "auch", "aber", "nicht",
    "was", "dass", "so", "nur", "noch", "schon", "sehr", "auch", "aus",
}


def normalize_title(title: str) -> str:
    """Normalisiert einen Kapitel-Titel fuer Matching."""
    # OMX-Suffixe wie |omx, |omy entfernen
    t = re.sub(r"\|[a-z]*omx?[a-z]*", "", title, flags=re.IGNORECASE)
    # Fuehrende Nummerierung entfernen
    t = re.sub(r"^\s*\d+\.\s*", "", t)
    # Zeichen filtern
    t = re.sub(r"[^a-zA-Z0-9\u00c0-\u017f\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def shingle_set(text: str, k: int = 5) -> set:
    """Erzeugt K-Wort-Shingles aus Text (lowercased, ohne Stopwoerter)."""
    words = [
        w for w in re.findall(r"\w+", text.lower())
        if w not in STOPWORDS_DE and len(w) > 2
    ]
    if len(words) < k:
        return set(tuple(words),) if words else set()
    return set(tuple(words[i:i + k]) for i in range(len(words) - k + 1))


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def compute_fingerprint(chapter: Chapter) -> str:
    """Erzeugt kurzen Fingerprint aus Titel + Anfang des Textes."""
    norm_title = normalize_title(chapter.title)
    first_words = " ".join(chapter.content.split()[:30]).lower()
    return f"{norm_title[:60]} | {first_words[:200]}"


def chapters_match(a: Chapter, b: Chapter, title_thr: float = 0.5,
                   content_thr: float = 0.3):
    """
    Entscheidet, ob zwei Kapitel "dasselbe" sind.
    Nutzt Titel-Jaccard + Content-Shingle-Jaccard.
    """
    # Title match
    a_title_words = set(normalize_title(a.title).split())
    b_title_words = set(normalize_title(b.title).split())
    title_sim = jaccard(a_title_words, b_title_words)

    # Content shingles
    a_shingles = shingle_set(a.content, k=5)
    b_shingles = shingle_set(b.content, k=5)
    content_sim = jaccard(a_shingles, b_shingles)

    # Kombinierte Entscheidung: Entweder Titel stark ODER Content stark
    is_match = title_sim >= title_thr or content_sim >= content_thr
    return is_match, title_sim, content_sim


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 90)
    print("  OMX-Validator -- Phase 3: Kapitel-Segmentierung + Cross-Source-Match")
    print("=" * 90)
    print()

    segmenters = {
        ".md": segment_md,
        ".docx": segment_docx,
        ".epub": segment_epub,
    }

    sources = []
    for fname in sorted(os.listdir(MERGE_DIR)):
        fpath = os.path.join(MERGE_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext not in segmenters:
            continue

        print(f"  [segment] {fname}")
        try:
            chapters, strategy = segmenters[ext](fpath, fname)
        except Exception as e:
            print(f"            FEHLER: {e}")
            continue

        for c in chapters:
            c.word_count = len(c.content.split())
            c.fingerprint = compute_fingerprint(c)

        src = SourceDoc(
            filename=fname,
            source_type=ext.lstrip("."),
            chapters=chapters,
            strategy_used=strategy,
        )
        sources.append(src)
        print(f"            -> {len(chapters)} Kapitel via '{strategy}'")

    print()
    print("=" * 90)
    print("  Uebersicht pro Quelle")
    print("=" * 90)
    print()
    print(f"  {'Datei':<44s} {'Strategie':<18s} {'Kapitel':>8s} {'Ø-Woerter':>12s}")
    print("-" * 90)
    for src in sources:
        avg_words = (
            sum(c.word_count for c in src.chapters) / max(len(src.chapters), 1)
        )
        fn = src.filename[:44] if len(src.filename) <= 44 else src.filename[:41] + "..."
        print(
            f"  {fn:<44s} {src.strategy_used:<18s} "
            f"{len(src.chapters):>8d} {avg_words:>12.0f}"
        )
    print()

    # Kapitel-Paar-Matching berechnen
    print("=" * 90)
    print("  Cross-Source-Matching (naive O(n^2) -- akzeptabel fuer aktuelle Groesse)")
    print("=" * 90)
    print()

    # Flache Liste aller Kapitel
    all_chapters = []
    for src in sources:
        for c in src.chapters:
            all_chapters.append(c)
    total = len(all_chapters)
    print(f"  Gesamt: {total} Kapitel aus {len(sources)} Quellen")
    print()

    # Matrix: source -> {source -> Anzahl matches}
    match_matrix = {}
    match_details = []
    for i, a in enumerate(all_chapters):
        for j, b in enumerate(all_chapters):
            if i >= j:
                continue
            if a.source_file == b.source_file:
                continue
            is_match, t_sim, c_sim = chapters_match(a, b)
            if is_match:
                key = (a.source_file, b.source_file)
                match_matrix[key] = match_matrix.get(key, 0) + 1
                match_details.append((a, b, t_sim, c_sim))

    # Matrix ausgeben
    print("  Matches pro Dateipaar:")
    for (f1, f2), count in sorted(match_matrix.items(), key=lambda x: -x[1]):
        short1 = f1[:38] if len(f1) <= 38 else f1[:35] + "..."
        short2 = f2[:38] if len(f2) <= 38 else f2[:35] + "..."
        print(f"    {short1:<38s} <-> {short2:<38s} : {count} Kapitel-Matches")
    print()

    # Top 10 der "sichersten" Matches (hoher Titel + Content Sim)
    print("  Top 10 staerkste Kapitel-Matches (Titel-Sim + Content-Sim):")
    top_matches = sorted(
        match_details,
        key=lambda x: -(x[2] + x[3])
    )[:10]
    for a, b, t_sim, c_sim in top_matches:
        print(f"    [{t_sim:.2f}/{c_sim:.2f}] {a.title[:50]}")
        print(f"           {a.source_file}")
        print(f"           <-> {b.source_file}")
    print()

    # Kapitel, die NUR in einer Quelle vorkommen (keine Matches)
    matched_chapters = set()
    for a, b, _, _ in match_details:
        matched_chapters.add((a.source_file, a.index))
        matched_chapters.add((b.source_file, b.index))

    unique_per_source = {}
    for src in sources:
        unique_count = sum(
            1 for c in src.chapters
            if (c.source_file, c.index) not in matched_chapters
        )
        unique_per_source[src.filename] = (unique_count, len(src.chapters))

    print("  Einzigartige Kapitel pro Quelle (kommen nirgendwo sonst vor):")
    for fname, (unique, total_) in sorted(
        unique_per_source.items(), key=lambda x: -x[1][0]
    ):
        short = fname[:50] if len(fname) <= 50 else fname[:47] + "..."
        pct = (unique / max(total_, 1)) * 100
        print(f"    {short:<50s}  {unique:>4d}/{total_:<4d}  ({pct:.0f}% unique)")
    print()

    # Speichere kurzen Report
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(REPORTS_DIR, "phase3_chapters.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# OMX-Validator -- Phase 3 Report\n\n")
        f.write(f"**Total Kapitel:** {total}\n\n")
        f.write("## Pro Quelle\n\n")
        for src in sources:
            f.write(f"- `{src.filename}`: {len(src.chapters)} Kapitel via `{src.strategy_used}`\n")
        f.write("\n## Match-Matrix\n\n")
        for (f1, f2), count in sorted(match_matrix.items(), key=lambda x: -x[1]):
            f.write(f"- `{f1}` <-> `{f2}`: **{count}** Matches\n")
        f.write("\n## Unique per Source\n\n")
        for fname, (unique, total_) in sorted(
            unique_per_source.items(), key=lambda x: -x[1][0]
        ):
            f.write(f"- `{fname}`: {unique}/{total_} unique\n")

    print(f"  Report gespeichert: {report_path}")
    print()
    print("=" * 90)


if __name__ == "__main__":
    main()
