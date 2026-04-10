#!/bin/bash
set -e

echo "=============================================="
echo "  Verschnyx Erknyxowitsch -- Container Start"
echo "=============================================="

# Memory-Verzeichnis sicherstellen
mkdir -p /app/memory

# Pruefen ob die Bibliothek gemountet ist
MD_COUNT=$(find /app/library -name "*.md" -maxdepth 1 2>/dev/null | wc -l)
echo "[start] $MD_COUNT Markdown-Dateien in /app/library"

if [ "$MD_COUNT" -eq 0 ]; then
    echo "[error] Keine Bibliothek gefunden! Ist das Volume korrekt gemountet?"
    exit 1
fi

# Indexierung beim ersten Start (wenn Vektordatenbank leer/nicht vorhanden)
if [ ! -f /app/vectorstore/chroma.sqlite3 ]; then
    echo "[start] Erster Start erkannt -- indiziere Bibliothek..."
    python indexer.py
    echo "[start] Indexierung abgeschlossen"
else
    echo "[start] Vektordatenbank existiert bereits -- ueberspringe Indexierung"
fi

# Bot starten
echo "[start] Starte Bot-Kern..."
exec python logic_core.py
