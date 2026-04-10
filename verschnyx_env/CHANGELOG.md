# Changelog -- Verschnyx Erknyxowitsch Bot

## v2.1 (2026-04-06) -- Stabilitaets-Patch

### Bugfixes
- **Surrogat-Crash behoben**: `_sanitize_text()` vor allen API-Calls (query_free, query_claude)
- **Chat-Historie Crash behoben**: Atomares Schreiben (.tmp -> rename), .bak Backup, errors='replace'
- **Session-Archiv**: Jede Session wird separat in memory/archive/ gespeichert
- **/exit robuster**: Erkennt exit, /exit, quit, /quit -- auch mit Steuerzeichen im Input
- **/gruebeln Minutenangabe repariert**: Liest aus user_input statt aus gekuerztem cmd
- **Gruebel-Limit erhoeht**: Max 480 Minuten (8 Stunden) statt 30
- **ChromaDB-Telemetrie abgestellt**: ENV ANONYMIZED_TELEMETRY=false
- **Embedding-Modell Cache**: Neues Volume chroma_cache verhindert Re-Download
- **search_library abgesichert**: try/except verhindert Crash bei nicht-initialisierter DB
- **Steuerzeichen-Strip**: Entfernt Progress-Bar-Artefakte aus docker attach Input

## v2.0 (2026-04-05) -- "Der introspektive Verschnyx"

### Neue Features
- Chat-Historie mit Stimmungs-Tracking (chat_history.json)
- /gruebeln <minuten>: Tiefenpsychologische Reflexion (Widerspruchs-Check, Tonfall, offene Fragen)
- /monolog: Stream-of-Consciousness aus zufaelligem Post + Tagebuch
- /recherche: DuckDuckGo-Suche durch die Verschnyx-Brille
- /korrekturen: Selbstkorrekturen anzeigen
- /stimmung: Stimmungsverlauf
- /historie: Letzte Chat-Nachrichten
- Charakter-Filter (Wikipedia-Bremse): Erkennt und transformiert sachliche Texte
- Corrections-Rueckfluss: corrections.md wird in System-Prompt injiziert

## v1.0 (2026-04-05) -- Erstversion

### Features
- Modell-Routing: OpenRouter (Free) vs Claude (Paid) mit Keyword-Erkennung
- Vektorsuche via ChromaDB (all-MiniLM-L6-v2 Embeddings)
- Identitaets-Management (identity.md, tagebuch.md)
- /scan: Bibliothek nach Identitaets-Hinweisen durchsuchen
- /suche: Vektorsuche in 26.620 Chunks
- Automatische Indexierung beim ersten Container-Start

### Infrastruktur
- Docker-Container (python:3.11-slim)
- WordPress-Export -> Markdown Pipeline (1.338 Posts)
- Ebook-Extraktor (652 Seiten, Typographie-bewahrend)
- Medien-Zuordnung (mapping.json, 118 Dateien)
