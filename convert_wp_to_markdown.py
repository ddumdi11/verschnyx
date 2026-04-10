#!/usr/bin/env python
"""
WordPress-Export zu Markdown Konverter

Extrahiert Posts aus WordPress-Export-XMLs, wandelt HTML in Markdown um,
passt Bild-Pfade auf lokale Medien an und erstellt eine mapping.json.

Verwendung:
    py -3.11 convert_wp_to_markdown.py

Erwartet im selben Verzeichnis:
    - Eine .zip mit WordPress-Export-XMLs
    - Eine .tar mit dem Medien-Export
"""

import json
import os
import re
import sys
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import urlparse, unquote

from bs4 import BeautifulSoup
from markdownify import markdownify as md

# --- Konfiguration ---
SCRIPT_DIR = Path(__file__).parent
ZIP_FILE = next(SCRIPT_DIR.glob("*.zip"))
TAR_FILE = next(SCRIPT_DIR.glob("*.tar"))
OUTPUT_DIR = SCRIPT_DIR / "knowledge"
MEDIA_DIR = SCRIPT_DIR / "media"

WP_NS = {
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

# Regex: WordPress upload URLs -> lokaler Pfad
WP_UPLOAD_PATTERN = re.compile(
    r"https?://[^\"'\s]+/wp-content/uploads/(\d{4}/\d{2}/[^\"'\s\)]+)"
)


def extract_media(tar_path: Path, media_dir: Path) -> dict[str, str]:
    """Entpackt den Medien-Export und gibt ein Mapping URL-Pfad -> lokaler Pfad zurück."""
    media_dir.mkdir(parents=True, exist_ok=True)
    url_to_local = {}

    with tarfile.open(tar_path) as tar:
        for member in tar.getmembers():
            if member.isfile():
                # Pfad ist z.B. "2013/07/dateiname.png"
                rel_path = member.name  # schon relativ
                target = media_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)

                with tar.extractfile(member) as src:
                    target.write_bytes(src.read())

                # Normalisierter Schlüssel ohne Query-Parameter
                url_to_local[rel_path] = str(target.relative_to(SCRIPT_DIR)).replace("\\", "/")

    print(f"  {len(url_to_local)} Medien-Dateien entpackt nach {media_dir}")
    return url_to_local


def parse_xml_files(zip_path: Path) -> tuple[list[dict], dict[int, dict]]:
    """Parst alle XML-Dateien aus dem ZIP und gibt Posts und Attachments zurück."""
    posts = []
    attachments = {}  # post_id -> {url, parent_id, filename}

    with zipfile.ZipFile(zip_path) as z:
        for name in sorted(z.namelist()):
            if not name.endswith(".xml"):
                continue

            print(f"  Parse {name}...")
            root = ET.fromstring(z.read(name))

            for item in root.findall(".//item"):
                post_type_el = item.find("wp:post_type", WP_NS)
                post_type = post_type_el.text if post_type_el is not None else None

                post_id_el = item.find("wp:post_id", WP_NS)
                post_id = int(post_id_el.text) if post_id_el is not None else 0

                title_el = item.find("title")
                title = title_el.text if title_el is not None and title_el.text else ""

                if post_type == "attachment":
                    url_el = item.find("wp:attachment_url", WP_NS)
                    parent_el = item.find("wp:post_parent", WP_NS)
                    attachments[post_id] = {
                        "url": url_el.text if url_el is not None else "",
                        "parent_id": int(parent_el.text) if parent_el is not None else 0,
                        "title": title,
                    }

                elif post_type == "post":
                    status_el = item.find("wp:status", WP_NS)
                    status = status_el.text if status_el is not None else "draft"

                    content_el = item.find("content:encoded", WP_NS)
                    content = content_el.text if content_el is not None and content_el.text else ""

                    date_el = item.find("wp:post_date", WP_NS)
                    date = date_el.text if date_el is not None and date_el.text else ""

                    slug_el = item.find("wp:post_name", WP_NS)
                    slug = slug_el.text if slug_el is not None and slug_el.text else ""

                    # Kategorien und Tags
                    categories = []
                    tags = []
                    for cat in item.findall("category"):
                        domain = cat.get("domain", "")
                        if domain == "category" and cat.text:
                            categories.append(cat.text)
                        elif domain == "post_tag" and cat.text:
                            tags.append(cat.text)

                    posts.append({
                        "id": post_id,
                        "title": title,
                        "slug": slug,
                        "date": date,
                        "status": status,
                        "content_html": content,
                        "categories": categories,
                        "tags": tags,
                    })

    print(f"  {len(posts)} Posts, {len(attachments)} Attachments gefunden")
    return posts, attachments


def sanitize_filename(title: str, post_id: int, date: str) -> str:
    """Erstellt einen sicheren Dateinamen aus dem Post-Titel."""
    # Datum-Prefix
    date_prefix = date[:10] if date else "0000-00-00"

    # Titel bereinigen
    name = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    name = re.sub(r"[\s]+", "-", name.strip())
    name = name[:80] if name else f"post-{post_id}"

    return f"{date_prefix}_{name}.md"


def replace_image_urls(html: str, media_map: dict[str, str]) -> tuple[str, list[str]]:
    """
    Ersetzt WordPress-Upload-URLs im HTML durch lokale Pfade.
    Gibt das modifizierte HTML und eine Liste genutzter Medien zurück.
    """
    used_media = []

    def replacer(match):
        full_url = match.group(0)
        rel_path = match.group(1)

        # Query-Parameter entfernen (z.B. ?w=300)
        clean_path = rel_path.split("?")[0]

        if clean_path in media_map:
            local_path = media_map[clean_path]
            used_media.append(local_path)
            return local_path
        else:
            # Nicht im Medien-Export vorhanden, URL beibehalten
            return full_url

    modified_html = WP_UPLOAD_PATTERN.sub(replacer, html)
    return modified_html, used_media


def html_to_markdown(html: str) -> str:
    """Konvertiert HTML in sauberes Markdown."""
    if not html.strip():
        return ""

    # Vorbereinigung mit BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # Leere div/span-Tags entfernen die nur Styling haben
    for tag in soup.find_all(["div", "span"]):
        if not tag.get_text(strip=True) and not tag.find(["img", "a", "iframe"]):
            tag.decompose()

    cleaned_html = str(soup)

    # markdownify Konvertierung
    markdown = md(
        cleaned_html,
        heading_style="atx",
        bullets="-",
        strip=["script", "style"],
    )

    # Aufräumen: mehrfache Leerzeilen reduzieren
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = markdown.strip()

    return markdown


def build_frontmatter(post: dict) -> str:
    """Erstellt YAML-Frontmatter für den Markdown-Post."""
    lines = ["---"]
    safe_title = post["title"].replace('"', '\\"')
    lines.append(f'title: "{safe_title}"')
    lines.append(f'date: "{post["date"]}"')
    lines.append(f'status: "{post["status"]}"')
    lines.append(f"wordpress_id: {post['id']}")
    if post["slug"]:
        lines.append(f"slug: \"{post['slug']}\"")
    if post["categories"]:
        cats = ", ".join(f'"{c}"' for c in post["categories"])
        lines.append(f"categories: [{cats}]")
    if post["tags"]:
        tags_str = ", ".join(f'"{t}"' for t in post["tags"])
        lines.append(f"tags: [{tags_str}]")
    lines.append("---")
    return "\n".join(lines)


def main():
    print("WordPress-Export zu Markdown Konverter")
    print("=" * 50)

    # 1. Medien entpacken
    print("\n1. Entpacke Medien-Export...")
    media_map = extract_media(TAR_FILE, MEDIA_DIR)

    # 2. XMLs parsen
    print("\n2. Parse WordPress-Export-XMLs...")
    posts, attachments = parse_xml_files(ZIP_FILE)

    # 3. Attachment -> Post Zuordnung aufbauen
    attachment_to_post = {}
    for att_id, att_info in attachments.items():
        parent_id = att_info["parent_id"]
        if parent_id > 0:
            if parent_id not in attachment_to_post:
                attachment_to_post[parent_id] = []
            attachment_to_post[parent_id].append(att_info)

    # 4. Posts konvertieren
    print("\n3. Konvertiere Posts zu Markdown...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    mapping = {}
    converted = 0
    skipped = 0

    for post in posts:
        # HTML-Bild-URLs durch lokale Pfade ersetzen
        modified_html, used_media_from_content = replace_image_urls(
            post["content_html"], media_map
        )

        # Attachments des Posts auch erfassen
        post_attachments = attachment_to_post.get(post["id"], [])
        attachment_media = []
        for att in post_attachments:
            url = att["url"]
            parsed = urlparse(url)
            path = unquote(parsed.path)
            # Extrahiere den relativen Pfad (YYYY/MM/datei.ext)
            match = re.search(r"uploads/(\d{4}/\d{2}/.+)$", path)
            if match:
                rel = match.group(1)
                if rel in media_map:
                    attachment_media.append(media_map[rel])

        all_media = list(dict.fromkeys(used_media_from_content + attachment_media))

        # HTML -> Markdown
        markdown_content = html_to_markdown(modified_html)

        if not markdown_content.strip():
            skipped += 1
            continue

        # Frontmatter + Content
        frontmatter = build_frontmatter(post)
        full_md = f"{frontmatter}\n\n{markdown_content}\n"

        # Dateiname
        filename = sanitize_filename(post["title"], post["id"], post["date"])
        filepath = OUTPUT_DIR / filename

        # Bei Duplikaten ID anhängen
        if filepath.exists():
            stem = filepath.stem
            filepath = OUTPUT_DIR / f"{stem}_{post['id']}.md"

        filepath.write_text(full_md, encoding="utf-8")
        converted += 1

        # Mapping
        mapping[str(post["id"])] = {
            "title": post["title"],
            "filename": filepath.name,
            "date": post["date"],
            "status": post["status"],
            "media": all_media,
        }

    # 5. mapping.json speichern
    mapping_path = OUTPUT_DIR / "mapping.json"
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    # Zusammenfassung
    print(f"\n{'=' * 50}")
    print(f"Fertig!")
    print(f"  {converted} Posts konvertiert")
    print(f"  {skipped} leere Posts übersprungen")
    print(f"  {len(media_map)} Medien-Dateien extrahiert")
    posts_with_media = sum(1 for v in mapping.values() if v["media"])
    total_media_refs = sum(len(v["media"]) for v in mapping.values())
    print(f"  {posts_with_media} Posts mit Medien-Referenzen ({total_media_refs} gesamt)")
    print(f"\n  Markdown-Dateien: {OUTPUT_DIR}")
    print(f"  Medien-Dateien:   {MEDIA_DIR}")
    print(f"  Mapping:          {mapping_path}")


if __name__ == "__main__":
    main()
