# Changelog -- Verschnyx Erknyxowitsch Bot

## v2.5 (2026-04-10) -- KB-Deduplikation + Git

### Knowledge-Base Bereinigung
- **KB-Dedup-Skript** (`omx_validator/kb_dedup.py`): Analyse + Archivierung redundanter WordPress-Revisionen
- **1989 -> 1189 Dateien**: 800 Duplikate in `_archive/safe/` und `_archive/review/` verschoben
- **5 Kategorien**: IDENTICAL (44), TRIVIAL (106), MINOR (134), MAJOR_SUBSET (84), MAJOR_UNIQUE (81)
- **Review-Queue**: 128 Dateien mit einzigartigen Zeilen zur manuellen Pruefung

### Infrastruktur
- **Git-Repository initialisiert**: 2534 Dateien, ~21 MB, saubere .gitignore
- **Dokumentation aktualisiert**: CHANGELOG, README, BRIEFING auf Stand gebracht

---

## v2.4 (2026-04-09) -- OMX-Validator + Overnight-Scheduler

### OMX-Validator Pipeline (6 Phasen)
- **Phase 1+2**: Extraktion + Qualitaetsbewertung (md, docx, epub) mit Multi-Dim-Scoring
- **Phase 3**: Kapitel-Segmentierung (4 Strategien) + Shingle-basiertes Cross-Source-Matching
- **Phase 4**: Quality-Aware Merge mit Union-Find Cliques und striktem Matching
- **Phase 5**: KB-Match via Inverted Shingle Index (509.646 Shingles, 1989 KB-Eintraege)
- **Phase 6**: Integrations-Vorschlag -- **594 neue Kapitel** identifiziert
  - 457 aus Vorarbeit.md (Google Sites)
  - 108 aus Smashwords (DOCX/EPUB)
  - 16 aus Hauptwerk (neue Kapitel)
  - 13 aus Hauptwerk (partielle Uebereinstimmung)
- Ergebnisse in `memory/new_material/` mit YAML-Frontmatter + INTEGRATION_MANIFEST.json

### Overnight-Scheduler
- **night_run.py**: Automatisierte Gruebel/Monolog-Zyklen via Docker stdin-Pipe
- Erster Nachtlauf erfolgreich: 20:34-22:59 (10 Schritte, ~2h24m)
- 4 Gruebel-Sessions, 4 Monologe, 1 Identitaets-Scan

---

## v2.3 (2026-04-09) -- Patch v1.2 "Smart Recherche"

### Bugfixes & Verbesserungen
- **Null-Safety fuer alle 4 Query-Funktionen**: None-Antworten -> leerer String (verhindert NoneType-Crash)
- **_already_researched()**: Prueft research_notes.md gegen Doppel-Recherche
- **_extract_research_query_smart()**: Mercury-basierte Kontext-Analyse statt erster Fragesatz
- Gruebel-Recherche nutzt jetzt intelligente Suchbegriffe statt roher Fragesaetze

### Bekanntes offenes Problem
- **0-Zeichen-Korrektur**: Leere Mercury-Antwort fuehrt zu false-positive Widerspruch (deferred zu v1.2.1)

---

## v2.2 (2026-04-08) -- Patch v1.1 "3-Tier Model Routing"

### Neue Features
- **3-Tier-Modell-Routing**: Mercury 2 (billig) -> Sonnet 4 (Qualitaet) -> Opus 4.6 (Exzellenz)
- **TaskRouter Klasse**: Keyword-basierte automatische Modellwahl mit OPUS_KEYWORDS und SONNET_KEYWORDS
- **query_mercury()**: Inception Mercury 2 via OpenRouter (Tier 1 -- schnell + guenstig)
- **query_claude_opus()**: Claude Opus 4.6 via Anthropic API (Tier 3 -- Spitzenqualitaet)

### Korrekturen
- **OpenRouter/auto -> OpenRouter/free**: `openrouter/auto` routete zu kostenpflichtigen Modellen!
- **Alle Call-Sites migriert**: Gruebeln, Monolog, Recherche nutzen jetzt Tier-gesteuertes Routing

---

## v2.1 (2026-04-07) -- Patch v1.0 "Gruebel-Fixes"

### Bugfixes
- **Gruebel-Retry-Loop behoben**: `tried_queries` Set verhindert wiederholte fehlgeschlagene Suchen
- **Query-Laengen-Guard**: Max 300 Zeichen fuer DuckDuckGo (verhindert curl_cffi-Crash)
- **_extract_search_query()**: Extrahiert ersten Fragesatz (max 150 Zeichen) statt gesamter Nachricht
- **DuckDuckGo Impersonate-Bug umgangen**: Kuerzere Queries vermeiden Profil-Inkompatibilitaet

### Stabilitaet (v2.1 vom 06. April)
- **Surrogat-Crash behoben**: `_sanitize_text()` vor allen API-Calls
- **Chat-Historie Crash behoben**: Atomares Schreiben (.tmp -> rename), .bak Backup
- **Session-Archiv**: Jede Session separat in memory/archive/
- **/exit robuster**: Erkennt exit/quit mit Steuerzeichen
- **/gruebeln Minutenangabe repariert**: Liest aus user_input statt gekuerztem cmd
- **ChromaDB-Telemetrie abgestellt**: ANONYMIZED_TELEMETRY=false
- **Embedding-Modell Cache**: chroma_cache Volume verhindert Re-Download

---

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

---

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
