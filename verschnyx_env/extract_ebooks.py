"""
extract_ebooks.py -- Extrahiert die Ur-Matrix (OMX-Ebooks) in die Bibliothek

Bewahrt die visuelle Integritaet: Leerzeichen, Umbrueche, experimentelle
Typographie von Zarko Maroli (2005/2026).

Konvertiert HTML -> Text/Markdown mit folgender Strategie:
- <br> -> Zeilenumbruch (nicht Absatz)
- <pre>/<code> -> Inhalt 1:1 bewahren
- Mehrfache Leerzeichen in einer Zeile -> bewahren (&nbsp; -> Leerzeichen)
- Headings -> # Markdown-Headings
- Navigations- und Calibre-Boilerplate -> entfernen
"""

import os
import re
import sys
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

SCRIPT_DIR = Path(__file__).parent
EBOOK_DIR = SCRIPT_DIR / "library" / "ebooks"
OUTPUT_DIR = SCRIPT_DIR / "library"

# Klassen die Navigation/Boilerplate sind (NICHT calibreEbookContent -- da steckt der Content drin!)
SKIP_CLASSES = {
    "calibreEbNavTop", "calibreEbNav",
    "calibreToc", "calibreMeta",
}


def extract_zip(zip_path: Path, book_prefix: str) -> list[dict]:
    """Extrahiert alle HTML-Dateien aus einem ZIP."""
    results = []

    with zipfile.ZipFile(zip_path) as z:
        html_files = sorted(
            n for n in z.namelist()
            if n.endswith(".html") and "/OEBPS" in n
        )
        # Falls kein OEBPS-Unterordner, alle HTMLs nehmen
        if not html_files:
            html_files = sorted(
                n for n in z.namelist()
                if n.endswith(".html")
            )

        print(f"  {len(html_files)} HTML-Dateien in {zip_path.name}")

        for html_path in html_files:
            raw = z.read(html_path).decode("utf-8", errors="replace")
            filename = Path(html_path).stem

            # Titel und Text extrahieren
            title, text = html_to_preserved_text(raw)

            if not text.strip():
                continue

            # Dateiname bereinigen
            safe_name = re.sub(r"[^\w\s-]", "", filename, flags=re.UNICODE)
            safe_name = re.sub(r"\s+", "-", safe_name.strip())
            if not safe_name:
                safe_name = f"seite-{len(results):03d}"

            results.append({
                "filename": f"{book_prefix}_{safe_name}.md",
                "title": title or safe_name,
                "text": text,
                "source_html": html_path,
                "book": book_prefix,
            })

    return results


def html_to_preserved_text(html: str) -> tuple[str, str]:
    """
    Konvertiert HTML in Text/Markdown mit bewahrter Typographie.
    Gibt (titel, text) zurueck.
    """
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    if not body:
        return "", ""

    # Autor aus Meta extrahieren (vor dem Entfernen)
    author = ""
    meta = body.find("div", class_="calibreMeta")
    if meta:
        author_el = meta.find("div", class_="calibreMetaAuthor")
        author = author_el.get_text(strip=True) if author_el else ""

    # Navigations- und Boilerplate entfernen
    for cls in SKIP_CLASSES:
        for el in body.find_all("div", class_=cls):
            el.decompose()

    # Content-Bereich finden (calibreEbookContent enthaelt den echten Content)
    content = body.find("div", class_="calibreEbookContent")
    if not content:
        content = body.find("div", class_="calibreMain")
    if not content:
        content = body

    # Seitentitel aus dem Content (erstes h1 oder span.title)
    title = ""
    first_h1 = content.find("h1")
    if first_h1:
        title_span = first_h1.find("span", class_="title")
        if title_span:
            title = title_span.get_text(strip=True)
        else:
            title = first_h1.get_text(strip=True)

    # Rekursive Textextraktion mit Typographie-Bewahrung
    lines = []
    _extract_node(content, lines)

    text = "\n".join(lines)

    # Nachbereinigung
    text = _cleanup_text(text)

    # Frontmatter hinzufuegen
    frontmatter = f"---\ntitle: \"{_escape_yaml(title or 'Untitled')}\"\n"
    if author:
        frontmatter += f"author: \"{_escape_yaml(author)}\"\n"
    frontmatter += f"source: ebook\n---\n\n"

    return title, frontmatter + text


def _extract_node(node, lines: list, depth: int = 0):
    """Rekursive Extraktion die Typographie bewahrt."""
    if isinstance(node, NavigableString):
        text = str(node)
        # &nbsp; -> normales Leerzeichen, aber BEHALTE mehrfache
        text = text.replace("\xa0", " ")
        # Nur \n am Anfang/Ende trimmen, nicht interne Whitespace
        if text.strip():
            lines.append(text.rstrip("\n"))
        return

    if not isinstance(node, Tag):
        return

    tag = node.name
    classes = set(node.get("class", []))

    # Skip Navigations-Elemente
    if classes & SKIP_CLASSES:
        return

    # Script/Style komplett ignorieren
    if tag in ("script", "style", "noscript"):
        return

    # <br> -> Zeilenumbruch
    if tag == "br":
        lines.append("")
        return

    # <hr> -> Trennlinie
    if tag == "hr":
        lines.append("\n---\n")
        return

    # <pre> und <code> -> Inhalt 1:1 bewahren
    if tag == "pre":
        lines.append("```")
        lines.append(node.get_text())
        lines.append("```")
        return

    if tag == "code":
        # Inline-Code oder Block? Pruefen ob mehrzeilig
        text = node.get_text()
        if "\n" in text or len(text) > 100:
            lines.append(text)
        else:
            lines.append(text)
        return

    # Headings
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        text = node.get_text(strip=True)
        if text:
            lines.append("")
            lines.append(f"{'#' * level} {text}")
            lines.append("")
        return

    # <a> Links -- nur Text behalten
    if tag == "a":
        # Anchor-Links (class=title mit nur id) ignorieren
        if node.get("id") and not node.get_text(strip=True):
            return
        text = node.get_text()
        if text.strip():
            lines.append(text)
        return

    # <img> -> Bildverweis
    if tag == "img":
        alt = node.get("alt", "")
        src = node.get("src", "")
        if src:
            lines.append(f"![{alt}]({src})")
        return

    # <table> -> Tabelleninhalte zeilenweise
    if tag == "table":
        _extract_table(node, lines)
        return

    # Block-Elemente: Absatz-Trennung
    block_tags = {"p", "div", "blockquote", "section", "article"}

    if tag in block_tags:
        # Kinder rekursiv verarbeiten
        for child in node.children:
            _extract_node(child, lines, depth + 1)
        return

    # <li> -> Aufzaehlungszeichen
    if tag == "li":
        li_lines = []
        for child in node.children:
            _extract_node(child, li_lines, depth + 1)
        text = " ".join(l.strip() for l in li_lines if l.strip())
        if text:
            lines.append(f"- {text}")
        return

    # <ul>/<ol> -> Kinder verarbeiten
    if tag in ("ul", "ol"):
        lines.append("")
        for child in node.children:
            _extract_node(child, lines, depth + 1)
        lines.append("")
        return

    # <strong>/<b> und <em>/<i> -> Markdown
    if tag in ("strong", "b"):
        text = node.get_text()
        if text.strip():
            lines.append(f"**{text}**")
        return

    if tag in ("em", "i"):
        text = node.get_text()
        if text.strip():
            lines.append(f"*{text}*")
        return

    # Alles andere: Kinder rekursiv
    for child in node.children:
        _extract_node(child, lines, depth + 1)


def _extract_table(table_node, lines: list):
    """Extrahiert Tabelleninhalt zeilenweise."""
    rows = table_node.find_all("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        cell_texts = []
        for cell in cells:
            cell_lines = []
            _extract_node(cell, cell_lines)
            text = " ".join(l.strip() for l in cell_lines if l.strip())
            cell_texts.append(text)
        if any(cell_texts):
            lines.append(" | ".join(cell_texts))


def _cleanup_text(text: str) -> str:
    """Bereinigt den extrahierten Text ohne Typographie zu zerstoeren."""
    # Mehr als 3 aufeinanderfolgende Leerzeilen -> 2
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # Navigations-Reste entfernen
    nav_patterns = [
        r"^Vorherige Seite\s*$",
        r"^Nächste Seite\s*$",
        r"^Start\s*$",
        r"^Inhaltsverzeichnis\s*$",
    ]
    for pattern in nav_patterns:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)

    # Anfangs- und End-Whitespace
    text = text.strip()

    return text


def _escape_yaml(s: str) -> str:
    return s.replace('"', '\\"').replace("\n", " ")


def main():
    print("=" * 60)
    print("  Ur-Matrix Extraktor -- OMX-Ebooks -> Bibliothek")
    print("=" * 60)

    zip_configs = [
        ("GOMX-Readbook_Pt2.zip", "GOMX-Pt2"),
        ("OMX-Essenz.zip", "OMX-Essenz"),
    ]

    total_extracted = 0

    for zip_name, prefix in zip_configs:
        zip_path = EBOOK_DIR / zip_name
        if not zip_path.exists():
            print(f"  [skip] {zip_name} nicht gefunden")
            continue

        print(f"\n  Extrahiere: {zip_name} (Prefix: {prefix})")
        pages = extract_zip(zip_path, prefix)

        for page in pages:
            out_path = OUTPUT_DIR / page["filename"]
            # Duplikate vermeiden
            if out_path.exists():
                stem = out_path.stem
                out_path = OUTPUT_DIR / f"{stem}_dup.md"

            out_path.write_text(page["text"], encoding="utf-8")
            total_extracted += 1

        print(f"  -> {len(pages)} Seiten extrahiert")

    print(f"\n{'=' * 60}")
    print(f"  Extraktion abgeschlossen: {total_extracted} Dateien")
    print(f"  Zielordner: {OUTPUT_DIR}")
    print(f"{'=' * 60}")

    # Vollzugsmeldung fuer Verschnyx
    meldung = (
        f"\n  *** MELDUNG AN VERSCHNYX ***\n"
        f"  Deine Ur-Matrix ist angekommen.\n"
        f"  {total_extracted} Seiten aus den OMX-Ebooks extrahiert:\n"
        f"    - GOMX-Readbook Part 2 (Zarko Maroli)\n"
        f"    - OMX - Vorläufige Essenz (Zarko Maroli)\n"
        f"  Die Texte liegen jetzt in deiner Bibliothek.\n"
        f"  AUFTRAG: Aktualisiere deine identity.md!\n"
        f"  Fuehre '/scan' aus, um die neuen alten Daten einzuarbeiten.\n"
    )
    print(meldung)

    return total_extracted


if __name__ == "__main__":
    main()
