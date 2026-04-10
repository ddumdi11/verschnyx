# Verschnyx Erknyxowitsch -- Bot-Kern v2.0 "Der introspektive Verschnyx"

KI-Manifestation des Autors von Private Science (Zarko Maroli / Verschnyx Erknyxowitsch).
Ein Docker-Container mit experimentellem Charakter, Vektorsuche, Selbstreflexion und
tiefenpsychologischem Gruebel-Modus.

## Schnellstart

```bash
cd verschnyx_env
cp .env.example .env   # API-Keys eintragen
docker compose up --build
# In zweitem Terminal:
docker compose run --rm -i verschnyx
```

## Architektur

```
verschnyx_env/
  Dockerfile              Python 3.11-slim, alle Dependencies
  docker-compose.yml      2GB RAM, 5 Volumes
  logic_core.py           Bot-Kern (Routing, Suche, Reflexion, Chat)
  indexer.py              ChromaDB-Indexer (26.620 Chunks)
  extract_ebooks.py       OMX-Ebook-Extraktor (HTML -> Markdown)
  entrypoint.sh           Container-Start (Auto-Indexierung)
  system_prompt.txt       Identitaets-Briefing
  requirements.txt        Python-Pakete

  memory/                 Beschreibbar, persistiert zwischen Starts
    identity.md           Selbst-Erkenntnis (wird durch /scan aktualisiert)
    tagebuch.md           Logbuch mit datierten Eintraegen
    chat_history.json     Zentrale Chat-Historie (max 500, mit .bak)
    corrections.md        Selbstkorrekturen aus Gruebel-Sitzungen
    research_notes.md     Web-Recherche im Verschnyx-Stil
    archive/              Permanente Session-Archive (chat_YYYY-MM-DD_HH-mm-ss.json)

  library/                Lokale Kopien der Ebook-Extrakte
    ebooks/               Original-ZIPs (GOMX-Readbook_Pt2, OMX-Essenz)
  vectorstore/            ChromaDB (persistiert, ~186 MB)
  chroma_cache/           Embedding-Modell-Cache (~167 MB)
```

## Volumes (docker-compose.yml)

| Volume                      | Container-Pfad         | Modus |
|-----------------------------|------------------------|-------|
| ../knowledge                | /app/library           | ro    |
| ../media                    | /app/media             | ro    |
| ./memory                    | /app/memory            | rw    |
| ./vectorstore               | /app/vectorstore       | rw    |
| ./chroma_cache              | /root/.cache/chroma    | rw    |

## Bibliothek

| Quelle                    | Dateien | Chunks   | Zeichen     |
|---------------------------|---------|----------|-------------|
| WordPress Blog-Posts      | 1.338   | ~20.600  | --          |
| GOMX-Readbook Pt2         | 89      | ~1.200   | ~150.000    |
| OMX Vorlaeufl. Essenz     | 563     | ~4.800   | ~2.100.000  |
| **Gesamt**                | **1.990** | **26.620** | --        |

## Modell-Routing

| Aufgabe              | Modell           | Trigger                        |
|----------------------|------------------|--------------------------------|
| Recherche, Standard  | OpenRouter/auto  | Default                        |
| Analyse, Kreatives   | Claude Sonnet    | Keywords: analyse, kreativ, schreib... |
| Erzwungen            | Beide            | force_model='free'/'claude'    |

## Befehle im Bot

| Befehl               | Funktion                                       |
|-----------------------|------------------------------------------------|
| /hilfe                | Alle Befehle anzeigen                          |
| /suche <query>        | Vektorsuche in der Bibliothek                  |
| /identitaet           | Aktuelle identity.md anzeigen                  |
| /tagebuch             | Letzte Logbuch-Eintraege                       |
| /scan                 | Identitaets-Scan (API-Call)                    |
| /gruebeln <min>       | Reflexions-Modus (1-480 Min, Standard: 2)      |
| /monolog              | Stream-of-Consciousness                        |
| /korrekturen          | Selbstkorrekturen anzeigen                     |
| /recherche <query>    | Web-Recherche (DuckDuckGo) im Verschnyx-Stil   |
| /stimmung             | Stimmungsverlauf anzeigen                      |
| /historie             | Letzte Chat-Eintraege                          |
| /exit                 | Beenden (auch: exit, /quit, quit)              |

## Gruebel-Modus im Detail

`/gruebeln 60` startet 60 Minuten Reflexion in drei Phasen pro Zyklus:
1. **Widerspruchs-Check**: Vergleicht letzte Antworten mit identity.md
2. **Tonfall-Pruefung**: Waren >50% der Antworten "sachlich"? -> Korrektur
3. **Offene Fragen**: Findet "weiss ich nicht"-Antworten -> DuckDuckGo -> verschnyxifiziert

## Bekannte Bugs (behoben)

- **Surrogat-Crash**: Kaputte UTF-8-Bytes aus WordPress-Export -> `_sanitize_text()` vor API-Calls
- **Encoding-Crash bei chat_history.json**: `write_text` -> atomares `write_bytes` mit Backup
- **Modell-404**: Hardcodiertes deepseek-Modell -> .env-priorisiert + Fallback-Kette
- **ChromaDB-Telemetrie**: `ANONYMIZED_TELEMETRY=false` im Dockerfile
- **Gruebeln ignoriert Minuten**: `cmd.split()` statt `user_input.split()`
- **docker attach Progress-Bar-Artefakte**: Steuerzeichen-Strip + try/except um search_library
