"""
OMX-Validator -- Phase 4: Quality-Aware Merge
==============================================

Merged inhaltlich gematchte Kapitel aus verschiedenen Quellen zu einer
"besten Version" pro Kapitel. Pro Clique (transitiv gematchte Kapitel)
wird der Exemplar mit dem hoechsten Quality Score gewaehlt.

Output:
  verschnyx_env/omx_validator/reports/merged/<cluster_name>/
    ├── 0001_kapitel_titel.md    (gemerged, Frontmatter mit Quellen)
    ├── 0002_kapitel_titel.md
    └── ...
  Plus: cluster_<name>_report.md  (Uebersicht + Provenienz)

Verwendung:
    cd verschnyx_env
    python omx_validator/phase4_merge.py
"""
import html
import io
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.dirname(HERE)
BASE_DIR = os.path.dirname(ENV_DIR)
MERGE_SRC = os.path.join(BASE_DIR, "Pool_gemischte-Daten", "merge_candidates", "ofub")
REPORTS_DIR = os.path.join(HERE, "reports")
MERGED_ROOT = os.path.join(REPORTS_DIR, "merged")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# Cluster-Definition: Welche Dateien gehoeren (laut Phase 3) zusammen?
CLUSTERS = {
    "cluster1_noch_mehr_ofub": [
        "Noch mehr offene Fragen und unf - zarko maroli.docx",
        "noch-mehr-offene-fragen-und-unfertige-bilder.epub",
    ],
    "cluster2_ofub_smashwords": [
        "Offene Fragen, unfertige Bilder - zarko maroli.docx",
        "offene-fragen-unfertige-bilder-prebook.epub",
        "OffeneFragenUnfertigeBilder_Vorarbeit.md",
    ],
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
    signals: dict = field(default_factory=dict)
    score: float = 0.0


# =============================================================================
# Extraktoren (kompakt, auf Kapitel-Ebene)
# =============================================================================
def read_md(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return html.unescape(f.read())


def segment_md(path: str, filename: str):
    content = read_md(path)

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
            chapters.append(Chapter(title=title, content=body, source_file=filename, index=i))
        return chapters, "md_h1"

    # Strategie 2: HTML-Anker via TOC
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
        if len(chapters) >= 5:
            return chapters, "md_html_anchors"

    # Fallback
    return [Chapter(title=f"(gesamt: {filename})", content=content, source_file=filename, index=0)], "md_monolith"


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
        return chapters, "docx_heading1"

    full_text = "\n".join(p[1] for p in paragraphs if p[1])
    return [Chapter(title=f"(gesamt: {filename})", content=full_text, source_file=filename, index=0)], "docx_monolith"


def _extract_epub_chapter_title(content: str, fallback_idx: int) -> str:
    """
    Extrahiert den Kapiteltitel aus einer XHTML-Datei.

    Strategie (in Reihenfolge):
      1. Erstes <h1>/<h2>/<h3> im <body> (richtige Semantik)
      2. Erster substanzieller <p> im body -- falls kurz (~< 120 Zeichen) und
         nicht offensichtlich CSS / @page / Fliesstext
      3. <title> im <head> (letzte Notloesung, oft nur Buchtitel)
    """
    # Body isolieren (alle Kopf-Daten ausblenden)
    body_match = re.search(r"<body[^>]*>(.*?)</body>", content, re.IGNORECASE | re.DOTALL)
    body = body_match.group(1) if body_match else content

    # 1. h1/h2/h3 im body
    h_match = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", body, re.IGNORECASE | re.DOTALL)
    if h_match:
        raw = h_match.group(1)
        raw = re.sub(r"<[^>]+>", "", raw)  # innere Tags entfernen
        raw = html.unescape(raw).strip()
        if raw and 3 <= len(raw) <= 200:
            return raw

    # 2. Erster kurzer substanzieller <p>
    # Skippe Paragraphs, die wie CSS/@page/Copyright aussehen
    p_matches = re.finditer(r"<p[^>]*>(.*?)</p>", body, re.IGNORECASE | re.DOTALL)
    for pm in p_matches:
        raw = pm.group(1)
        raw = re.sub(r"<[^>]+>", "", raw)
        raw = html.unescape(raw).strip()
        if not raw:
            continue
        # Filter: CSS-aehnlich, zu lang oder leer
        if "@page" in raw or "margin-" in raw or "font-" in raw:
            continue
        if len(raw) > 150 or len(raw) < 3:
            continue
        # Gute Kandidaten: kurz, substanziell
        return raw

    # 3. Notloesung: <title> aus dem head (ausserhalb body gesucht)
    head_title = re.search(r"<title[^>]*>([^<]+)</title>", content, re.IGNORECASE)
    if head_title:
        return html.unescape(head_title.group(1)).strip()

    return f"(Datei {fallback_idx})"


def _clean_epub_body_text(content: str) -> str:
    """
    Extrahiert sauberen Text aus XHTML:
    - <style>, <script>, <head> komplett entfernen (inkl. Inhalt!)
    - CSS-/@-Direktiven filtern
    - HTML-Tags strippen
    - Leerzeilen kanonisieren
    """
    # Alles im <head> entfernen (Meta, Title, Style)
    content = re.sub(r"<head[^>]*>.*?</head>", "", content, flags=re.IGNORECASE | re.DOTALL)
    # <style> und <script> komplett entfernen (inkl. Inhalt)
    content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.IGNORECASE | re.DOTALL)
    # Nur den <body> behalten
    body_match = re.search(r"<body[^>]*>(.*?)</body>", content, re.IGNORECASE | re.DOTALL)
    if body_match:
        content = body_match.group(1)

    # Block-Elemente zu Zeilenumbruechen
    content = re.sub(r"</(p|div|h[1-6]|li|br|pre)>", "\n", content, flags=re.IGNORECASE)
    content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)
    # Tags entfernen
    content = re.sub(r"<[^>]+>", "", content)
    # Entities dekodieren
    content = html.unescape(content)
    # CSS-Reste filtern (Zeilen mit @ oder mit ; { })
    cleaned_lines = []
    for line in content.split("\n"):
        stripped = line.strip()
        # Skippe reine CSS-Zeilen
        if re.match(r"^\s*@(page|media|font|import)", stripped):
            continue
        if re.match(r"^\s*[{}]", stripped):
            continue
        if re.search(r"(margin-|padding-|font-size:|font-family:|color:\s*#)", stripped):
            continue
        cleaned_lines.append(line)
    content = "\n".join(cleaned_lines)
    # Mehrfache Leerzeilen auf max 2 reduzieren
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


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

            title = _extract_epub_chapter_title(content, idx)
            text = _clean_epub_body_text(content)

            if len(text) >= 20:
                chapters.append(Chapter(title=title[:150], content=text, source_file=filename, index=idx))
                idx += 1
    return chapters, "epub_per_xhtml"


# =============================================================================
# Quality Signals (aus Phase 2)
# =============================================================================
def compute_signals(text: str) -> dict:
    lines = text.split("\n")
    n_words = len(text.split())
    ws_4plus = sum(1 for l in lines if re.search(r"\s{4,}\S", l))
    ws_8plus = sum(1 for l in lines if re.search(r"\s{8,}", l))
    ws_16plus = sum(1 for l in lines if re.search(r"\s{16,}", l))
    empty_lines = sum(1 for l in lines if not l.strip())
    empty_ratio = empty_lines / max(len(lines), 1)
    html_entities = len(re.findall(r"&(?:nbsp|amp|lt|gt|quot|#\d+);", text))
    em_dashes = text.count("\u2014")
    en_dashes = text.count("\u2013")
    smart_q_d = text.count("\u201c") + text.count("\u201d")
    smart_q_s = text.count("\u2018") + text.count("\u2019")
    nbsp_u = text.count("\u00a0")
    ellipsis = text.count("\u2026")
    tabs = text.count("\t")

    return {
        "n_words": n_words,
        "n_chars": len(text),
        "ws_4plus": ws_4plus,
        "ws_8plus": ws_8plus,
        "ws_16plus": ws_16plus,
        "empty_ratio": round(empty_ratio, 3),
        "html_entities": html_entities,
        "em_dashes": em_dashes,
        "en_dashes": en_dashes,
        "smart_q_d": smart_q_d,
        "smart_q_s": smart_q_s,
        "nbsp_u": nbsp_u,
        "ellipsis": ellipsis,
        "tabs": tabs,
    }


def quality_score(signals: dict) -> float:
    """Multi-dim score, aggregiert. Anpassung aus Phase 2 fuer Kapitel-Level."""
    words = max(signals["n_words"], 1)
    norm = 1000.0 / words

    ws_fid = (
        signals["ws_16plus"] * 5.0
        + signals["ws_8plus"] * 2.0
        + signals["ws_4plus"] * 0.3
        + signals["tabs"] * 0.5
    ) * norm

    uni_fid = (
        signals["em_dashes"] * 0.5
        + signals["en_dashes"] * 0.3
        + signals["smart_q_d"] * 0.2
        + signals["smart_q_s"] * 0.2
        + signals["nbsp_u"] * 0.5
        + signals["ellipsis"] * 0.3
    ) * norm

    er = signals["empty_ratio"]
    if 0.10 <= er <= 0.40:
        struct_fid = 10.0
    elif 0.05 <= er < 0.10 or 0.40 < er <= 0.55:
        struct_fid = 5.0
    else:
        struct_fid = 2.0

    # Content-Volume-Bonus: Laengere Kapitel bekommen kleinen Bonus
    # (denn wenn zwei Kapitel gleichwertig formatiert sind, ist mehr Inhalt besser)
    volume_bonus = min(5.0, signals["n_words"] / 200.0)

    penalty = signals["html_entities"] * 0.3 * norm

    return round(ws_fid + uni_fid + struct_fid + volume_bonus - penalty, 2)


# =============================================================================
# Matching (aus Phase 3)
# =============================================================================
STOPWORDS_DE = {
    "der", "die", "das", "und", "oder", "ist", "in", "zu", "den", "ein",
    "eine", "einen", "dem", "des", "mit", "auf", "fuer", "von", "im",
    "am", "es", "sich", "an", "als", "wie", "auch", "aber", "nicht",
    "was", "dass", "so", "nur", "noch", "schon", "sehr", "aus",
}


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


def chapters_match(a: Chapter, b: Chapter):
    """
    Strengeres Matching: Content-Aehnlichkeit ist das Hauptkriterium.
    Titel sind ein schwaches Signal (Sprachmuster wie "Noch mehr..." fuehren
    zu falschen Treffern), daher nur als Tie-Breaker.

    Match-Regeln (ODER-verknuepft):
      1. Sehr starker Content-Match: content_sim >= 0.40 (allein ausreichend)
      2. Starker Titel + mittlerer Content: title_sim >= 0.80 UND content_sim >= 0.15
      3. Identischer Titel: title_sim == 1.0 UND content_sim >= 0.10
    """
    a_tw = set(normalize_title(a.title).split())
    b_tw = set(normalize_title(b.title).split())
    title_sim = jaccard(a_tw, b_tw)
    a_sh = shingle_set(a.content, k=5)
    b_sh = shingle_set(b.content, k=5)
    content_sim = jaccard(a_sh, b_sh)

    is_match = (
        content_sim >= 0.40
        or (title_sim >= 0.80 and content_sim >= 0.15)
        or (title_sim >= 0.99 and content_sim >= 0.10)
    )
    return is_match, title_sim, content_sim


# =============================================================================
# Clique-Building via Union-Find
# =============================================================================
class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def build_cliques(chapters, match_pairs_idx):
    uf = UnionFind(len(chapters))
    for a_idx, b_idx, _, _ in match_pairs_idx:
        uf.union(a_idx, b_idx)
    groups = defaultdict(list)
    for i in range(len(chapters)):
        groups[uf.find(i)].append(i)
    return list(groups.values())


# =============================================================================
# Datei-Output
# =============================================================================
def clean_display_title(title: str) -> str:
    """
    Entfernt Kapitel-Nummerierung und Quellen-Suffixe, behaelt aber den
    eigentlichen Titel mit Gross-/Kleinschreibung und Sonderzeichen.

    Rationale: Kapitelnummern sind nicht stabil -- sie haengen von der
    Zusammenstellung ab. Der Titel ist der eigentliche Identifier.
    """
    t = title
    # OMX-Suffix wie "|omx", "| omx", "|omy" entfernen
    t = re.sub(r"\s*\|\s*[a-z]*omx?[a-z]*", "", t, flags=re.IGNORECASE)
    # Fuehrende Nummerierung "1. " oder "12. " entfernen
    t = re.sub(r"^\s*\d+\.\s+", "", t)
    # Trailing Google-Sites-Marker "- Hembelz Om(x)" entfernen
    t = re.sub(r"\s*[-\u2013\u2014]\s*Hembelz\s*Om\(x\)\s*$", "", t, flags=re.IGNORECASE)
    return t.strip()


def safe_filename(title: str, max_len: int = 60) -> str:
    """
    Generiert einen dateisystem-sicheren Namen aus dem cleanen Titel.
    Kapitelnummern werden entfernt (nicht Teil der Identitaet).
    """
    s = clean_display_title(title)
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:max_len] or "untitled"


def write_merged_chapter(winner: Chapter, alternates: list, out_dir: str, idx: int) -> str:
    # m0001_ = "merge order", NICHT Zarkos Kapitelnummer! Nur fuer Sortierung.
    display_title = clean_display_title(winner.title)
    fname = f"m{idx:04d}_{safe_filename(winner.title)}.md"
    path = os.path.join(out_dir, fname)

    lines = ["---"]
    lines.append(f'title: "{display_title}"')
    lines.append(f'original_title_in_source: "{winner.title}"')
    lines.append(f"source_file: {winner.source_file}")
    lines.append(f"word_count: {winner.word_count}")
    lines.append(f"quality_score: {winner.score:.2f}")
    if alternates:
        lines.append("alternate_sources:")
        for alt in alternates:
            lines.append(f"  - file: {alt.source_file}")
            alt_clean = clean_display_title(alt.title)
            if alt_clean != display_title:
                lines.append(f"    title_in_source: \"{alt.title}\"")
            lines.append(f"    words: {alt.word_count}")
            lines.append(f"    score: {alt.score:.2f}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {display_title}")
    lines.append("")
    lines.append(winner.content)
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return fname


# =============================================================================
# Cluster-Merger
# =============================================================================
def process_cluster(cluster_name: str, file_list: list, verbose: bool = True):
    print()
    print("=" * 90)
    print(f"  Cluster: {cluster_name}")
    print(f"  Dateien: {len(file_list)}")
    print("=" * 90)
    print()

    # 1. Alle Dateien einlesen und segmentieren
    all_chapters = []
    per_file_counts = {}

    for fname in file_list:
        fpath = os.path.join(MERGE_SRC, fname)
        if not os.path.exists(fpath):
            print(f"  [WARN] Nicht gefunden: {fname}")
            continue

        ext = os.path.splitext(fname)[1].lower()
        if ext == ".md":
            chapters, strategy = segment_md(fpath, fname)
        elif ext == ".docx":
            chapters, strategy = segment_docx(fpath, fname)
        elif ext in (".epub", ".htm", ".html"):
            chapters, strategy = segment_epub(fpath, fname)
        else:
            print(f"  [SKIP] Kein Extractor fuer: {fname}")
            continue

        # Signals + Score pro Kapitel
        for c in chapters:
            c.word_count = len(c.content.split())
            c.signals = compute_signals(c.content)
            c.score = quality_score(c.signals)

        per_file_counts[fname] = len(chapters)
        print(f"  [segment] {fname} -> {len(chapters)} Kapitel ({strategy})")
        all_chapters.extend(chapters)

    if not all_chapters:
        print("  Keine Kapitel gefunden. Abbruch.")
        return

    total = len(all_chapters)
    print(f"\n  Gesamt: {total} Kapitel")

    # 2. Paar-Matching
    print(f"  Matche Kapitel paarweise...")
    match_pairs_idx = []
    for i in range(total):
        for j in range(i + 1, total):
            if all_chapters[i].source_file == all_chapters[j].source_file:
                continue
            is_m, t_sim, c_sim = chapters_match(all_chapters[i], all_chapters[j])
            if is_m:
                match_pairs_idx.append((i, j, t_sim, c_sim))

    print(f"  -> {len(match_pairs_idx)} Kapitel-Paare matchen")

    # 3. Cliques via Union-Find
    cliques = build_cliques(all_chapters, match_pairs_idx)
    multi_cliques = [c for c in cliques if len(c) > 1]
    singletons = [c for c in cliques if len(c) == 1]
    print(f"  -> {len(cliques)} Cliquen insgesamt")
    print(f"     davon {len(multi_cliques)} Merge-Cliquen (Mehrfach-Quellen)")
    print(f"     davon {len(singletons)} Singletons (Orphan-Kapitel)")

    # 4. Output-Ordner vorbereiten
    out_dir = os.path.join(MERGED_ROOT, cluster_name)
    os.makedirs(out_dir, exist_ok=True)

    # 5. Pro Clique: Winner waehlen und schreiben
    merged_entries = []
    idx = 1

    # Erst die Merge-Cliquen (sortiert nach Winner-Titel)
    multi_results = []
    for clique_idxs in multi_cliques:
        members = [all_chapters[i] for i in clique_idxs]
        winner = max(members, key=lambda c: c.score)
        alternates = [c for c in members if c is not winner]
        multi_results.append((winner, alternates))

    multi_results.sort(key=lambda r: r[0].title.lower())

    for winner, alternates in multi_results:
        fname_written = write_merged_chapter(winner, alternates, out_dir, idx)
        merged_entries.append({
            "idx": idx,
            "file": fname_written,
            "title": winner.title,
            "winner_src": winner.source_file,
            "winner_score": winner.score,
            "winner_words": winner.word_count,
            "alternates": [
                {"src": a.source_file, "score": a.score, "words": a.word_count}
                for a in alternates
            ],
            "type": "merged",
        })
        idx += 1

    # Dann die Singletons (sortiert nach Titel)
    singleton_chapters = [all_chapters[c[0]] for c in singletons]
    singleton_chapters.sort(key=lambda c: c.title.lower())

    for chap in singleton_chapters:
        fname_written = write_merged_chapter(chap, [], out_dir, idx)
        merged_entries.append({
            "idx": idx,
            "file": fname_written,
            "title": chap.title,
            "winner_src": chap.source_file,
            "winner_score": chap.score,
            "winner_words": chap.word_count,
            "alternates": [],
            "type": "singleton",
        })
        idx += 1

    # 6. Report schreiben
    report_path = os.path.join(REPORTS_DIR, f"merge_{cluster_name}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Merge-Report: {cluster_name}\n\n")
        f.write(f"**Erzeugt:** {datetime.now().isoformat(timespec='seconds')}\n\n")
        f.write("## Quellen\n\n")
        for fname, cnt in per_file_counts.items():
            f.write(f"- `{fname}`: {cnt} Kapitel\n")
        f.write(f"\n**Total eingelesen:** {total} Kapitel\n\n")
        f.write("## Merge-Bilanz\n\n")
        f.write(f"- **Merge-Cliquen:** {len(multi_cliques)} ")
        f.write(f"(mehrere Quellen pro Kapitel, beste gewinnt)\n")
        f.write(f"- **Singletons:** {len(singletons)} ")
        f.write(f"(nur eine Quelle, 1:1 uebernommen)\n")
        f.write(f"- **Ausgabe-Dateien:** {len(merged_entries)}\n\n")

        f.write("## Merge-Cliquen (wer hat gewonnen?)\n\n")
        f.write("| # | Titel | Gewinner (Quelle) | Score | Woerter | Alternate(n) |\n")
        f.write("|---|---|---|---|---|---|\n")
        for e in merged_entries:
            if e["type"] != "merged":
                continue
            alts_str = "<br>".join(
                f"{a['src'][:30]} ({a['score']:.1f}/{a['words']}w)"
                for a in e["alternates"]
            )
            title_esc = clean_display_title(e["title"])[:60].replace("|", "\\|")
            src_esc = e["winner_src"][:30]
            f.write(
                f"| {e['idx']} | {title_esc} | {src_esc} | "
                f"{e['winner_score']:.1f} | {e['winner_words']} | {alts_str} |\n"
            )

        f.write("\n## Singletons (nur eine Quelle)\n\n")
        f.write("| # | Titel | Quelle | Woerter |\n")
        f.write("|---|---|---|---|\n")
        for e in merged_entries:
            if e["type"] != "singleton":
                continue
            title_esc = clean_display_title(e["title"])[:70].replace("|", "\\|")
            src_esc = e["winner_src"][:30]
            f.write(f"| {e['idx']} | {title_esc} | {src_esc} | {e['winner_words']} |\n")

    print(f"\n  [ok] {len(merged_entries)} Dateien geschrieben nach: {out_dir}")
    print(f"  [ok] Report: {report_path}")


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 90)
    print("  OMX-Validator -- Phase 4: Quality-Aware Merge")
    print("=" * 90)

    os.makedirs(MERGED_ROOT, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    for cluster_name, file_list in CLUSTERS.items():
        process_cluster(cluster_name, file_list)

    print()
    print("=" * 90)
    print("  Fertig. Alle Cluster verarbeitet.")
    print("=" * 90)


if __name__ == "__main__":
    main()
