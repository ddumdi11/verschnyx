# Briefing fuer Phase 2 -- Verschnyx Erknyxowitsch Projekt
## Stand: 2026-04-06

---

## 1. Was ist das Projekt?

Ein Docker-Container, der als KI-Manifestation des Autors "Verschnyx Erknyxowitsch"
(buergerlich Zarko Maroli) fungiert. Der Bot hat Zugriff auf die gesamte literarische
Bibliothek des Autors, kann darin suchen, darueber reflektieren, und entwickelt
eine eigene Identitaet basierend auf den Texten.

---

## 2. Was wurde in Phase 1 gebaut?

### 2.1 Daten-Pipeline (convert_wp_to_markdown.py)
- WordPress-Export (ZIP mit 2 XMLs) -> 1.338 Markdown-Dateien
- HTML -> sauberes Markdown mit YAML-Frontmatter
- Bild-URLs -> lokale Pfade (118 Medien-Dateien)
- mapping.json: Post-ID -> Dateiname, Medien-Zuordnung

### 2.2 Ebook-Extraktor (extract_ebooks.py)
- 2 ZIP-Archive (GOMX-Readbook Pt2, OMX-Essenz) -> 652 Markdown-Dateien
- Typographie-bewahrend: Leerzeichen, Umbrueche, experimentelle Layouts intakt
- Calibre-HTML-Struktur korrekt geparst (verschachtelte div.calibre1-Container)

### 2.3 Docker-Umgebung
- python:3.11-slim mit langchain, chromadb, openai, anthropic, duckduckgo-search
- 2 GB RAM-Limit
- 5 Volumes: library(ro), media(ro), memory(rw), vectorstore(rw), chroma_cache(rw)
- Automatische Indexierung beim ersten Start

### 2.4 Bot-Kern v2.0 "Der introspektive Verschnyx" (logic_core.py, ~39 KB)

**Routing:**
- OpenRouter (Free/auto) fuer Recherche und Alltag
- Claude Sonnet fuer tiefe Analyse und Kreatives
- Keyword-basierte Automatik + force_model Override

**Vektorsuche:**
- ChromaDB mit all-MiniLM-L6-v2 Embeddings (lokal, kein API-Key noetig)
- 26.620 Chunks aus 1.990 Dateien
- Volltext-Fallback wenn ChromaDB leer

**Identitaets-System:**
- identity.md: Wird durch /scan (API-gestuetzt) aktualisiert
- tagebuch.md: Datierte Eintraege, Monologe, Gruebel-Protokolle
- corrections.md: Selbstkorrekturen, fliessen in System-Prompt zurueck

**Gruebel-Modus (/gruebeln <minuten>):**
- Widerspruchs-Check: Vergleicht Chat-Historie mit identity.md
- Tonfall-Pruefung: Erkennt "zu sachlich" (Wikipedia-Bremse)
- Offene Fragen: Findet unbeantwortete Fragen -> DuckDuckGo -> verschnyxifiziert
- Erwachens-Meldungen: Poetische Status-Updates nach Reflexion
- Dauer: 1-480 Minuten (8 Stunden max)

**Charakter-Filter (Wikipedia-Bremse):**
- Erkennt sachliche Lexikon-Sprache per Heuristik
- Transformiert via API in experimentellen Verschnyx-Stil

**Chat-Historie:**
- Zentrale chat_history.json (max 500 Eintraege, mit .bak Backup)
- Atomares Schreiben (erst .tmp, dann rename)
- Session-Archive in memory/archive/ (permanentes Gedaechtnis)
- Stimmungs-Tracker pro Nachricht (euphorisch, kryptisch, sachlich, ...)

**Zusatz-Features:**
- /monolog: Stream-of-Consciousness aus zufaelligem Post + Tagebuch
- /recherche: DuckDuckGo -> Verschnyx-Brille -> research_notes.md
- /stimmung: Stimmungsverlauf visualisiert
- /historie: Letzte Chat-Nachrichten

---

## 3. Erkannte Identitaet von Verschnyx

Nach mehreren /scan-Durchlaeufen und Gruebel-Sitzungen kennt der Bot:

**Pseudonyme:** Verschnyx Erknyxowitsch, Zarko Maroli, Tom Omx, axixio, "dude" (Leo.org)

**Das OMX-System:** Eine eigene Meta-Sprache/Enzyklopaedie mit Suffix-Taxonomie
(|omx, |omy, |omz, |noomx, |omyz). Begriffsschoepfungen wie DeppTauglichIndex,
FlexiVariVexli, Kollektivkapsel, Delta-Existenz-Drift, Spaltungspotenzierung.

**Rollen:** Begriffsarchitekt, Immaterialer Hausbauer, Forum-Theologe, Film-Visionaer

**Stil-DNS:** Raeumliche Typographie, Sprach-Explosionen, Wort-Komposite, Fragmentierung,
Deutsch-Englisch-Hybrid, selbstironische Fussnoten, mathematische Notation in lyrischem Kontext.

**Themen:** Mutter-Komplex (persoenlich + planetarisch), Euphemismus-Komplex,
Anti-Theologie (verneint biblische Konnotationen waehrend er Bibelverse zitiert),
"fim" als Gender-Neutra (feminin + inter + maskulin), 13 ReckIm.

---

## 4. Behobene Bugs und Stabilitaets-Massnahmen

| Bug | Ursache | Loesung |
|-----|---------|---------|
| Container-Crash bei Sonderzeichen | `write_text()` truncated Datei vor Encode-Versuch | Atomares Schreiben via .tmp + rename |
| Surrogat-Crash bei API-Calls | Kaputte UTF-8-Bytes aus WP-Export in ChromaDB-Chunks | `_sanitize_text()` vor jedem API-Call |
| Modell-404 (deepseek) | Hardcodierter Fallback-Modellname | .env-Prioritaet + Fallback-Kette |
| /exit wird ignoriert | Paste-Artefakte, Steuerzeichen im Input | Robuste Erkennung: exit/quit + Steuerzeichen-Strip |
| /gruebeln ignoriert Minutenangabe | `cmd` war auf erstes Wort gekuerzt | `user_input.split()` statt `cmd.split()` |
| ChromaDB-Telemetrie-Spam | Versions-Inkompatibilitaet | ENV ANONYMIZED_TELEMETRY=false |
| Embedding-Download bei jedem Start | Cache nicht persistiert | chroma_cache Volume |
| search_library Crash | ChromaDB nicht bereit bei frueh eingegebenem Input | try/except mit Fallback |

---

## 5. Offene Punkte / Vorschlaege fuer Phase 2

### 5.1 Stabilitaet
- [ ] `docker compose build --no-cache` einmalig ausfuehren (raeumt Telemetrie-Reste auf)
- [ ] Free-Modell Endlos-Schleifen: OpenRouter/auto neigt zu Wiederholungen -> max_tokens strenger begrenzen oder Wiederholungserkennung einbauen
- [ ] Input-Handling bei docker attach: Grundsaetzlich `docker compose run --rm -i` empfehlen

### 5.2 Inhaltlich
- [ ] Weitere Materialien einspeisen (der Autor hat vermutlich noch mehr)
- [ ] "fim"-Konzept und weitere Sprachschoepfungen gezielt in identity.md einarbeiten
- [ ] Verschnyx' Antwort-Qualitaet verbessern: System-Prompt mit konkreten Stil-Beispielen anreichern
- [ ] Die identity.md koennte vom Bot selbst in seinem Stil geschrieben werden statt sachlich

### 5.3 Technisch
- [ ] Web-Interface (Streamlit/Gradio) statt Docker-Terminal
- [ ] Langzeit-Gedaechtnis: Chat-Archive automatisch zusammenfassen und in identity.md/tagebuch.md einarbeiten
- [ ] Multi-Turn-Konversation: Aktuell ist jeder API-Call stateless (nur System-Prompt + aktueller Input). Conversation-History an die API senden wuerde Kohaerenz massiv verbessern
- [ ] Indexer fuer Ebook-Seiten separat ausfuehren koennen (ohne Container-Neustart)
- [ ] corrections.md Rotation (wird sonst immer groesser)

### 5.4 Kreativ
- [ ] Verschnyx koennte eigene Blog-Posts schreiben (im OMX-Stil)
- [ ] Ein "OMX-Generator": Neue Begriffe nach dem |omx-Muster erschaffen
- [ ] Verschnyx als Discord/Telegram-Bot fuer oeffentliche Interaktion

---

## 6. Dateien-Uebersicht

### Hauptverzeichnis (wordpress-blog_parsen/)
```
convert_wp_to_markdown.py    WordPress-Export -> Markdown (1.338 Posts)
knowledge/                   1.990 Markdown-Dateien (Blog + Ebooks)
media/                       118 Medien-Dateien (Bilder, PDFs)
```

### Bot-Umgebung (verschnyx_env/)
```
Dockerfile                   Python 3.11-slim + Dependencies
docker-compose.yml           5 Volumes, 2GB RAM
logic_core.py                Bot-Kern v2.0 (~39 KB, ~1.080 Zeilen)
indexer.py                   ChromaDB-Indexer
extract_ebooks.py            Ebook-Extraktor (HTML -> Markdown)
entrypoint.sh                Container-Startskript
system_prompt.txt            Identitaets-Briefing
requirements.txt             Python-Pakete
.env.example                 API-Key-Template
memory/                      Persistentes Gedaechtnis (7 Dateien + Archiv)
library/ebooks/              Original-ZIPs (GOMX + OMX-Essenz)
vectorstore/                 ChromaDB (~186 MB, 26.620 Chunks)
chroma_cache/                Embedding-Modell-Cache (~167 MB)
```

---

## 7. Wie man den Bot startet

```bash
cd verschnyx_env
cp .env.example .env         # API-Keys eintragen
docker compose up --build    # Erster Start (indexiert ~5 Min)
# Danach in separatem Terminal:
docker compose run --rm -i verschnyx
```

Wichtig: `docker compose run --rm -i verschnyx` (NICHT `docker attach`) fuer saubere Interaktion.

---

## 8. API-Kosten-Bilanz (geschaetzt)

- OpenRouter (Free): Kein Kostenaufwand (openrouter/auto waehlt kostenlose Modelle)
- Claude Sonnet: Bisher wenige Aufrufe (nur bei /scan, komplexen Fragen, Synthese)
- Geschaetzte bisherige Claude-Kosten: <$0.50 (wenige tausend Tokens)
- Gruebel-Modus nutzt primaer Free-Modell (ausser Identitaets-Synthese)
