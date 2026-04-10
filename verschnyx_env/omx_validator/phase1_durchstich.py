"""
OMX-Validator -- Phase 1: Vertikaler Durchstich
================================================

Ein minimaler End-to-End-Pfad fuer die Pool_gemischte-Daten/merge_candidates/:
  1. Scannt den Ordner
  2. Extrahiert Text aus .md, .docx, .epub (Stdlib-only)
  3. Misst Quality-Signale fuer jede Datei
  4. Gibt ein Ranking aus

Noch kein Clustering, kein Merge, kein KB-Vergleich -- das Ziel ist nur:
Heuristiken validieren, Fundament pruefen.

Verwendung:
    cd verschnyx_env
    python omx_validator/phase1_durchstich.py
"""
import html
import io
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.dirname(HERE)
BASE_DIR = os.path.dirname(ENV_DIR)
MERGE_DIR = os.path.join(
    BASE_DIR, "Pool_gemischte-Daten", "merge_candidates", "ofub"
)

# OOXML Namespace fuer docx
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# =============================================================================
# Datenklasse
# =============================================================================
@dataclass
class Document:
    filename: str
    source_type: str
    size_bytes: int
    text: str = ""
    signals: dict = field(default_factory=dict)


# =============================================================================
# Extraktoren
# =============================================================================
def extract_md(path: str) -> str:
    """Liest Markdown, dekodiert HTML-Entities (Konversions-Artefakte)."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    # Phase 2: Auto-Dekodierung aller HTML-Entities
    # &nbsp; -> \u00a0, &amp; -> &, &#8212; -> em-dash, etc.
    return html.unescape(content)


def extract_docx(path: str) -> str:
    """
    Extrahiert Text aus .docx unter Bewahrung von Tabs, Absaetzen, Whitespace.
    Stdlib-only via zipfile + ElementTree.
    """
    with zipfile.ZipFile(path) as z:
        xml_data = z.read("word/document.xml").decode("utf-8")

    root = ET.fromstring(xml_data)
    blocks = []

    # Iteriere durch alle Absaetze (<w:p>)
    for para in root.iter(f"{{{W_NS}}}p"):
        parts = []
        for elem in para.iter():
            tag = elem.tag.split("}", 1)[-1] if "}" in elem.tag else elem.tag
            if tag == "t":
                # Text-Run -- xml:space="preserve" wird automatisch beachtet
                parts.append(elem.text or "")
            elif tag == "tab":
                parts.append("\t")
            elif tag == "br":
                parts.append("\n")
        line = "".join(parts)
        blocks.append(line)

    return "\n".join(blocks)


def extract_epub(path: str) -> str:
    """
    Extrahiert Text aus .epub durch XHTML-Stripping.
    Laedt alle content documents, konkateniert.
    """
    text_parts = []
    with zipfile.ZipFile(path) as z:
        # Finde content documents (oft unter OEBPS/ oder OPS/)
        candidates = [
            n for n in z.namelist()
            if n.lower().endswith((".html", ".xhtml", ".htm"))
        ]
        # Stabile Reihenfolge
        candidates.sort()
        for name in candidates:
            try:
                content = z.read(name).decode("utf-8", errors="replace")
                # Block-Level-Tags zu Zeilenumbruechen
                content = re.sub(
                    r"</(p|div|h[1-6]|li|br|pre)>",
                    "\n",
                    content,
                    flags=re.IGNORECASE,
                )
                content = re.sub(
                    r"<br\s*/?>", "\n", content, flags=re.IGNORECASE
                )
                # Tags entfernen
                text = re.sub(r"<[^>]+>", "", content)
                # Basis-Entities dekodieren
                text = (
                    text.replace("&nbsp;", " ")
                    .replace("&amp;", "&")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                    .replace("&quot;", '"')
                    .replace("&apos;", "'")
                    .replace("&#160;", " ")
                )
                text_parts.append(text)
            except Exception as e:
                print(f"  [warn] {name}: {e}")

    return "\n\n".join(text_parts)


# =============================================================================
# Quality Signals
# =============================================================================
def compute_signals(text: str) -> dict:
    """Misst Formatierungs-Qualitaets-Signale eines Textes."""
    lines = text.split("\n")
    n_lines = len(lines)
    n_chars = len(text)

    # Whitespace-Runs (Indikator fuer raeumliche Typographie / ASCII-Art)
    ws_4plus = sum(1 for l in lines if re.search(r"\s{4,}\S", l))
    ws_8plus = sum(1 for l in lines if re.search(r"\s{8,}", l))
    ws_16plus = sum(1 for l in lines if re.search(r"\s{16,}", l))

    # Leerzeilen-Ratio (Absatzstruktur bewahrt?)
    empty_lines = sum(1 for l in lines if not l.strip())
    empty_ratio = empty_lines / max(n_lines, 1)

    # HTML-Entities (schlecht -- zeigen unaufgeloesten Import)
    html_entities = len(re.findall(r"&(?:nbsp|amp|lt|gt|quot|#\d+);", text))

    # Unicode-Typographie (gut -- zeigt bewahrte Formatierung)
    em_dashes = text.count("\u2014")  # em-dash
    en_dashes = text.count("\u2013")  # en-dash
    smart_quotes_double = text.count("\u201c") + text.count("\u201d")
    smart_quotes_single = text.count("\u2018") + text.count("\u2019")
    nbsp_unicode = text.count("\u00a0")  # no-break space
    ellipsis = text.count("\u2026")  # horizontal ellipsis

    # Tab-Zeichen (oft fuer Einrueckung/Struktur)
    tabs = text.count("\t")

    # Charakter-Diversitaet
    unique_chars = len(set(text))

    # Word-Tokens (fuer Pro-Wort-Normalisierung spaeter)
    words = len(text.split())

    return {
        "n_lines": n_lines,
        "n_chars": n_chars,
        "n_words": words,
        "unique_chars": unique_chars,
        "ws_4plus": ws_4plus,
        "ws_8plus": ws_8plus,
        "ws_16plus": ws_16plus,
        "empty_lines": empty_lines,
        "empty_ratio": round(empty_ratio, 3),
        "html_entities": html_entities,
        "em_dashes": em_dashes,
        "en_dashes": en_dashes,
        "smart_quotes_d": smart_quotes_double,
        "smart_quotes_s": smart_quotes_single,
        "nbsp_unicode": nbsp_unicode,
        "ellipsis": ellipsis,
        "tabs": tabs,
    }


def quality_score_multidim(signals: dict) -> dict:
    """
    Phase 2: Multi-dimensionales Scoring statt einem Einzel-Score.

    Drei Dimensionen, alle pro 1000 Woerter normiert:
      - whitespace_fidelity: Erhalt raeumlicher Typografie (ASCII-Art)
      - unicode_fidelity: Erhalt feiner typografischer Zeichen (em-dash, Smart Quotes, nbsp)
      - structure_fidelity: Absatz-/Zeilenstruktur bewahrt

    Plus ein legacy-kompatibler aggregate_score fuer Ranking.
    """
    words = max(signals["n_words"], 1)
    norm = 1000.0 / words

    # Whitespace-Fidelitaet: wie gut ist raeumliche Typographie bewahrt?
    ws_fidelity = (
        signals["ws_16plus"] * 5.0
        + signals["ws_8plus"] * 2.0
        + signals["ws_4plus"] * 0.3
        + signals["tabs"] * 0.5
    ) * norm

    # Unicode-Fidelitaet: wie viele feine Sonderzeichen wurden bewahrt?
    uni_fidelity = (
        signals["em_dashes"] * 0.5
        + signals["en_dashes"] * 0.3
        + signals["smart_quotes_d"] * 0.2
        + signals["smart_quotes_s"] * 0.2
        + signals["nbsp_unicode"] * 0.5
        + signals["ellipsis"] * 0.3
    ) * norm

    # Struktur-Fidelitaet: Absaetze und Zeilengrenzen bewahrt?
    # Ein gewisser Anteil Leerzeilen ist gut (klare Absaetze),
    # aber zu viele deuten auf Layoutmuell hin. 10-30% ist ideal.
    er = signals["empty_ratio"]
    if 0.10 <= er <= 0.40:
        structure_fidelity = 10.0
    elif 0.05 <= er < 0.10 or 0.40 < er <= 0.55:
        structure_fidelity = 5.0
    else:
        structure_fidelity = 2.0

    # Phase 2: HTML-Entities sind jetzt vor-dekodiert, keine Strafe mehr noetig.
    # Falls trotzdem welche durchrutschen -> milde Strafe.
    penalty = signals["html_entities"] * 0.3 * norm

    aggregate = ws_fidelity + uni_fidelity + structure_fidelity - penalty

    return {
        "ws_fidelity": round(ws_fidelity, 2),
        "uni_fidelity": round(uni_fidelity, 2),
        "structure_fidelity": round(structure_fidelity, 2),
        "penalty": round(penalty, 2),
        "aggregate": round(aggregate, 2),
    }


def quality_score(signals: dict) -> float:
    """Legacy-Shim: gibt nur den aggregate-Score zurueck."""
    return quality_score_multidim(signals)["aggregate"]


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 90)
    print("  OMX-Validator -- Phase 1: Vertikaler Durchstich")
    print("=" * 90)
    print(f"  Quellordner: {MERGE_DIR}")
    print()

    if not os.path.exists(MERGE_DIR):
        print(f"[FEHLER] Ordner nicht gefunden: {MERGE_DIR}")
        sys.exit(1)

    extractors = {
        ".md": ("md", extract_md),
        ".docx": ("docx", extract_docx),
        ".epub": ("epub", extract_epub),
    }

    docs = []
    for fname in sorted(os.listdir(MERGE_DIR)):
        fpath = os.path.join(MERGE_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext not in extractors:
            print(f"  [skip] Kein Extractor fuer: {fname}")
            continue

        source_type, extractor = extractors[ext]
        size = os.path.getsize(fpath)
        print(f"  [extract] {fname}  ({size:,} B)")
        try:
            text = extractor(fpath)
        except Exception as e:
            print(f"            FEHLER: {e}")
            continue

        doc = Document(
            filename=fname,
            source_type=source_type,
            size_bytes=size,
            text=text,
        )
        doc.signals = compute_signals(text)
        scores = quality_score_multidim(doc.signals)
        doc.signals.update(scores)
        doc.signals["quality_score"] = scores["aggregate"]
        docs.append(doc)

    print()
    print("=" * 90)
    print("  Ranking nach Quality Score (hoeher = bessere Formatierungstreue)")
    print("=" * 90)
    print()

    # Multi-Dim-Tabelle
    header = f"{'Datei':<44s} {'Typ':<6s} {'Words':>8s} {'WS-Fid':>8s} {'Uni-Fid':>8s} {'Struct':>7s} {'Score':>8s}"
    print(header)
    print("-" * len(header))

    for d in sorted(docs, key=lambda x: -x.signals["quality_score"]):
        fn = d.filename if len(d.filename) <= 44 else d.filename[:41] + "..."
        s = d.signals
        print(
            f"{fn:<44s} {d.source_type:<6s} "
            f"{s['n_words']:>8,} "
            f"{s['ws_fidelity']:>8.2f} "
            f"{s['uni_fidelity']:>8.2f} "
            f"{s['structure_fidelity']:>7.2f} "
            f"{s['quality_score']:>8.2f}"
        )

    print()
    print("=" * 90)
    print("  Unicode-Typografie im Detail")
    print("=" * 90)
    print()
    header2 = f"{'Datei':<44s} {'em—':>6s} {'en–':>6s} {'“”':>6s} {'‘’':>6s} {'…':>6s} {'nbsp':>6s} {'tabs':>6s}"
    print(header2)
    print("-" * len(header2))
    for d in sorted(docs, key=lambda x: -x.signals["quality_score"]):
        fn = d.filename if len(d.filename) <= 44 else d.filename[:41] + "..."
        s = d.signals
        print(
            f"{fn:<44s} {s['em_dashes']:>6d} {s['en_dashes']:>6d} "
            f"{s['smart_quotes_d']:>6d} {s['smart_quotes_s']:>6d} "
            f"{s['ellipsis']:>6d} {s['nbsp_unicode']:>6d} {s['tabs']:>6d}"
        )

    print()
    print("=" * 90)
    print(f"  Fertig. {len(docs)} Dokumente analysiert.")
    print("=" * 90)


if __name__ == "__main__":
    main()
