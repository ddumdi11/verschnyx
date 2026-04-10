"""
indexer.py -- Indiziert die Markdown-Bibliothek in ChromaDB

Liest alle .md-Dateien aus /app/library, splittet sie in Chunks
und speichert sie in der lokalen ChromaDB-Vektordatenbank.
Nutzt ChromaDBs eingebautes Embedding (all-MiniLM-L6-v2, kein API-Key noetig).
"""

import json
import re
import sys
from pathlib import Path

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

LIBRARY_DIR = Path("/app/library")
VECTORSTORE_DIR = Path("/app/vectorstore")
MAPPING_FILE = LIBRARY_DIR / "mapping.json"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
BATCH_SIZE = 100  # ChromaDB Batch-Limit


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Trennt YAML-Frontmatter vom Body."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            fm_block = text[3:end].strip()
            body = text[end + 3:].strip()

            metadata = {}
            for line in fm_block.split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    val = val.strip().strip('"').strip("'")
                    metadata[key.strip()] = val
            return metadata, body

    return {}, text


def index_library():
    """Hauptfunktion: Liest, splittet und indiziert alle Markdown-Dateien."""
    print("=" * 60)
    print("  Verschnyx-Indexer -- Bibliothek -> ChromaDB")
    print("=" * 60)

    # ChromaDB initialisieren
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))

    # Alte Collection loeschen und neu erstellen
    try:
        client.delete_collection("bibliothek")
        print("[index] Alte Collection geloescht")
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name="bibliothek",
        metadata={"hnsw:space": "cosine"},
    )

    # Mapping laden (optional, fuer erweiterte Metadaten)
    post_mapping = {}
    if MAPPING_FILE.exists():
        with open(MAPPING_FILE, encoding="utf-8") as f:
            post_mapping = json.load(f)

    # Text-Splitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    # Alle Markdown-Dateien verarbeiten
    md_files = sorted(LIBRARY_DIR.glob("*.md"))
    print(f"[index] {len(md_files)} Markdown-Dateien gefunden")

    all_ids = []
    all_documents = []
    all_metadatas = []
    total_chunks = 0
    skipped = 0

    for i, md_file in enumerate(md_files):
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  [skip] {md_file.name}: {e}")
            skipped += 1
            continue

        metadata, body = parse_frontmatter(text)

        if not body.strip():
            skipped += 1
            continue

        # Chunks erstellen
        chunks = splitter.split_text(body)

        for j, chunk in enumerate(chunks):
            chunk_id = f"{md_file.stem}_chunk{j:03d}"
            chunk_meta = {
                "source": md_file.name,
                "title": metadata.get("title", ""),
                "date": metadata.get("date", ""),
                "status": metadata.get("status", ""),
                "chunk_index": j,
                "total_chunks": len(chunks),
            }

            # WordPress-ID fuer Mapping-Referenz
            wp_id = metadata.get("wordpress_id", "")
            if wp_id:
                chunk_meta["wordpress_id"] = wp_id

            all_ids.append(chunk_id)
            all_documents.append(chunk)
            all_metadatas.append(chunk_meta)
            total_chunks += 1

        # Fortschritt
        if (i + 1) % 200 == 0:
            print(f"  [{i + 1}/{len(md_files)}] {total_chunks} Chunks bisher...")

    # In Batches in ChromaDB schreiben
    print(f"\n[index] Schreibe {total_chunks} Chunks in ChromaDB...")

    for start in range(0, len(all_ids), BATCH_SIZE):
        end = min(start + BATCH_SIZE, len(all_ids))
        collection.add(
            ids=all_ids[start:end],
            documents=all_documents[start:end],
            metadatas=all_metadatas[start:end],
        )
        if (start // BATCH_SIZE + 1) % 20 == 0:
            print(f"  Batch {start // BATCH_SIZE + 1}... ({end}/{total_chunks})")

    # Zusammenfassung
    final_count = collection.count()
    print(f"\n{'=' * 60}")
    print(f"  Indexierung abgeschlossen!")
    print(f"  {len(md_files) - skipped} Dateien verarbeitet ({skipped} uebersprungen)")
    print(f"  {final_count} Chunks in der Vektordatenbank")
    print(f"  Speicherort: {VECTORSTORE_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    index_library()
