# Verschnyx Erknyxowitsch -- Bot v2.5

KI-Manifestation des Autors von Private Science (Zarko Maroli / Verschnyx Erknyxowitsch).
Ein Docker-Container mit experimentellem Charakter, Vektorsuche, Selbstreflexion,
3-Tier-Modell-Routing und einem philologischen OMX-Validator.

## Schnellstart

```bash
cd verschnyx_env
cp .env.example .env   # API-Keys eintragen (OPENROUTER + ANTHROPIC)
docker compose up --build
# In zweitem Terminal:
docker compose run --rm -i verschnyx
```

## Architektur

```
wordpress-blog_parsen/
  .gitignore                 Git-Konfiguration
  BRIEFING_PHASE2.md         Projekt-Briefing (fuer neue Teammitglieder)
  convert_wp_to_markdown.py  WordPress-Export -> Markdown (1.338 Posts)
  knowledge/                 1.189 bereinigte Markdown-Dateien (nach Dedup)
    _archive/                Deduplizierte Versionen (safe/ + review/)
  media/                     118 Medien-Dateien (Bilder, PDFs)

  verschnyx_env/             Bot-Umgebung
    logic_core.py            Bot-Kern v2.1 (~48 KB, ~1.306 Zeilen)
    indexer.py               ChromaDB-Indexer (26.620 Chunks)
    extract_ebooks.py        Ebook-Extraktor (HTML -> Markdown)
    Dockerfile               Python 3.11-slim, alle Dependencies
    docker-compose.yml       2GB RAM, 5 Volumes
    entrypoint.sh            Container-Start (Auto-Indexierung)
    system_prompt.txt        Identitaets-Briefing
    requirements.txt         Python-Pakete
    .env.example             API-Key-Template

    patches/                 Modulare Code-Patches
      apply_gruebel_fixes.py   v1.0: Gruebel-Robustheit
      apply_tier_routing.py    v1.1: 3-Tier-Modell-Routing
      apply_smart_recherche.py v1.2: Intelligente Recherche
      backups/                 Timestamped logic_core.py Backups

    omx_validator/           Philologische Validierungs-Pipeline
      phase1_durchstich.py     Extraktion + Qualitaetsbewertung
      phase3_chapters.py       Kapitel-Segmentierung + Matching
      phase4_merge.py          Quality-Aware Merge (Union-Find)
      phase5_kb_match.py       KB-Abgleich (Inverted Shingle Index)
      phase6_integration_proposal.py  Integrations-Vorschlag
      kb_dedup.py              KB-Deduplikation
      reports/                 Generierte Analyse-Berichte

    scheduler/               Automatisierung
      night_run.py             Overnight Gruebel/Monolog-Zyklen

    tests/                   Qualitaetssicherung
      ab_test_mercury.py       A/B-Test Mercury vs Sonnet vs Opus

    memory/                  Persistentes Gedaechtnis (rw, git-ignored)
    vectorstore/             ChromaDB (rw, git-ignored, ~186 MB)
    chroma_cache/            Embedding-Cache (rw, git-ignored, ~167 MB)
```

## 3-Tier Model Routing

| Tier | Modell | Einsatz | Kosten |
|------|--------|---------|--------|
| 1 | Mercury 2 (Inception) | Standard, Recherche, Widerspruchs-Check | Guenstig |
| 2 | Claude Sonnet 4 | Analyse, Essays, Reflexion, Interpretation | Mittel |
| 3 | Claude Opus 4.6 | Essenz-Synthese, Gesamtwerk, Identitaets-Updates | Hoch |
| Fallback | OpenRouter/free | Wenn Tier 1 fehlschlaegt | Kostenlos |

Die Modellwahl erfolgt automatisch via **TaskRouter** (Keyword-Erkennung)
oder manuell via `force_model` Parameter.

## Knowledge Base

| Quelle | Dateien | Status |
|--------|---------|--------|
| WordPress Blog-Posts | 537 | Dedupliziert (war: 1.337 mit WP-Revisionen) |
| OMX Vorlaeufl. Essenz | 563 | Vollstaendig |
| GOMX-Readbook Pt2 | 89 | Vollstaendig |
| **Gesamt (aktiv)** | **1.189** | **26.620 Chunks in ChromaDB** |
| Archiviert (Duplikate) | 800 | In knowledge/_archive/ |
| Neues Material (staged) | 594 | In memory/new_material/ (noch nicht integriert) |

## Bot-Befehle

| Befehl | Funktion |
|--------|----------|
| /hilfe | Alle Befehle anzeigen |
| /suche <query> | Vektorsuche in der Bibliothek |
| /identitaet | Aktuelle identity.md anzeigen |
| /tagebuch | Letzte Logbuch-Eintraege |
| /scan | Identitaets-Scan (API-Call, Tier 2/3) |
| /gruebeln <min> | Reflexions-Modus (1-480 Min, Standard: 2) |
| /monolog | Stream-of-Consciousness |
| /korrekturen | Selbstkorrekturen anzeigen |
| /recherche <query> | Web-Recherche (DuckDuckGo) im Verschnyx-Stil |
| /stimmung | Stimmungsverlauf anzeigen |
| /historie | Letzte Chat-Eintraege |
| /exit | Beenden (auch: exit, /quit, quit) |

## OMX-Validator Pipeline

Philologische Textrekonstruktion in 6 Phasen:

1. **Extraktion**: md, docx, epub Formate mit Qualitaetssignalen
2. **Qualitaetsbewertung**: Multi-dimensionales Scoring (Whitespace, Unicode, Struktur)
3. **Kapitel-Segmentierung**: 4 Strategien + Shingle-basiertes Cross-Source-Matching
4. **Quality-Aware Merge**: Union-Find Cliques, striktes Matching (content_sim >= 0.40)
5. **KB-Match**: Inverted Shingle Index (509.646 Shingles) -- EXACT/NEAR/NEW Klassifikation
6. **Integrations-Vorschlag**: 594 neue Kapitel in 4 Buckets mit YAML-Frontmatter

## Overnight-Scheduler

```bash
# Dry-Run (keine Aenderungen):
python scheduler/night_run.py --dry-run

# Live-Lauf (Bot muss im Container aktiv sein):
python scheduler/night_run.py
```

10-Schritt-Programm: 4x Gruebeln + 4x Monolog + 1x Identitaets-Scan + 1x Abschluss-Gruebel.

## Volumes (docker-compose.yml)

| Volume | Container-Pfad | Modus |
|--------|----------------|-------|
| ../knowledge | /app/library | ro |
| ../media | /app/media | ro |
| ./memory | /app/memory | rw |
| ./vectorstore | /app/vectorstore | rw |
| ./chroma_cache | /root/.cache/chroma | rw |
