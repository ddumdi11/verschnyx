# Projekt-Briefing -- Verschnyx Erknyxowitsch
## Stand: 2026-04-10 (nach Phase 2)

---

## 1. Was ist das Projekt?

Ein Docker-Container, der als KI-Manifestation des Autors "Verschnyx Erknyxowitsch"
(buergerlich Zarko Maroli) fungiert. Der Bot hat Zugriff auf die gesamte literarische
Bibliothek des Autors, kann darin suchen, darueber reflektieren, und entwickelt
eine eigene Identitaet basierend auf den Texten.

**Projektinhaber:** Diede (arbeitet mit Claude + Gemini parallel)
**Repo:** Git-initialisiert, bereit fuer GitHub (Private)
**Hauptsprache:** Python 3.11 (Docker) / Deutsch (Inhalte)

---

## 2. Projektverlauf -- Was bisher geschah

### Phase 1 (5. April 2026)
- WordPress-Export -> 1.338 Markdown-Dateien
- Ebook-Extraktion -> 652 Seiten (GOMX-Readbook + OMX-Essenz)
- Docker-Umgebung + ChromaDB (26.620 Chunks)
- Bot-Kern v2.0 "Der introspektive Verschnyx" (logic_core.py)
- Identitaets-System (identity.md, tagebuch.md, corrections.md)

### Phase 2a: Patches (7.-9. April 2026)
- **v1.0 Gruebel-Fixes**: Query-Laengen-Guard, Retry-Loop-Fix, DuckDuckGo-Stabilisierung
- **v1.1 3-Tier-Routing**: Mercury 2 / Sonnet 4 / Opus 4.6 statt fehlerhaftem OpenRouter/auto
- **v1.2 Smart-Recherche**: Null-Safety, intelligente Suchbegriff-Extraktion via Mercury

### Phase 2b: OMX-Validator (9. April 2026)
- 6-Phasen-Pipeline zur philologischen Textrekonstruktion
- **594 neue Kapitel identifiziert** (nicht in der bisherigen KB)
- Datengenealoogie aufgeklaert: 3 Quellen (Blogger -> Google Sites -> WordPress -> EPUBs)
- Shingle-basiertes Matching mit Inverted Index (509.646 Shingles)

### Phase 2c: Automatisierung + Bereinigung (9.-10. April 2026)
- **Overnight-Scheduler**: 10-Schritt-Programm (Gruebeln/Monolog), erster Nachtlauf erfolgreich
- **KB-Deduplikation**: 1989 -> 1189 Dateien (800 WordPress-Revisionen archiviert)
- **Git-Repository initialisiert**: 2534 Dateien, ~21 MB, saubere .gitignore
- **Dokumentation aktualisiert**: CHANGELOG, README, BRIEFING

---

## 3. Technische Architektur

### 3.1 3-Tier Model Routing
| Tier | Modell | Via | Einsatz |
|------|--------|-----|---------|
| 1 | Mercury 2 (Inception) | OpenRouter | Standard, Recherche, Widerspruchs-Check |
| 2 | Claude Sonnet 4 | Anthropic API | Analyse, Essays, Reflexion |
| 3 | Claude Opus 4.6 | Anthropic API | Essenz-Synthese, Gesamtwerk, Identitaet |
| Fallback | openrouter/free | OpenRouter | Wenn Tier 1 fehlschlaegt |

**Wichtig:** `openrouter/auto` ist NICHT free-only -- es routet auch zu kostenpflichtigen Modellen!
Fuer kostenlose Modelle immer `openrouter/free` verwenden.

### 3.2 Daten-Pipeline
```
WordPress-XML -> convert_wp_to_markdown.py -> knowledge/ (1.189 Dateien)
Ebook-ZIPs   -> extract_ebooks.py         -> knowledge/ (652 Dateien)
Pool-Daten   -> omx_validator/*            -> memory/new_material/ (594 Dateien)
knowledge/   -> indexer.py                 -> vectorstore/ (26.620 Chunks)
```

### 3.3 Bot-Kern (logic_core.py, ~48 KB)
- **TaskRouter**: Keyword-basierte automatische Modellwahl
- **Vektorsuche**: ChromaDB mit all-MiniLM-L6-v2 (lokal, kein API-Key)
- **Gruebel-Modus**: Widerspruchs-Check, Tonfall-Pruefung, offene Fragen + Recherche
- **Identitaets-System**: identity.md (Selbst-Erkenntnis), tagebuch.md, corrections.md
- **Wikipedia-Bremse**: Erkennt sachliche Sprache, transformiert in Verschnyx-Stil
- **Atomares Schreiben**: .tmp -> rename + .bak Backup fuer crash-sichere Persistenz

### 3.4 OMX-Validator (omx_validator/)
Stdlib-only Python-Pipeline (kein pip install noetig):
- Shingle-basierte Jaccard-Similarity (k=5 Wort-Shingles, Stopword-Filtering)
- Union-Find fuer transitive Clique-Bildung
- Multi-dimensionale Qualitaetsbewertung (Whitespace, Unicode, Struktur)
- Inverted Shingle Index fuer schnelles KB-Matching

---

## 4. Erkannte Identitaet von Verschnyx

**Pseudonyme:** Verschnyx Erknyxowitsch, Zarko Maroli, Tom Omx, axixio, "dude" (Leo.org User 253248)

**Das OMX-System:** Eigene Meta-Sprache/Enzyklopaedie mit Suffix-Taxonomie
(|omx, |omy, |omz, |noomx, |omyz). Begriffsschoepfungen wie DeppTauglichIndex,
FlexiVariVexli, Kollektivkapsel, Delta-Existenz-Drift, Spaltungspotenzierung.

**Rollen:** Begriffsarchitekt, Immaterialer Hausbauer, Forum-Theologe, Film-Visionaer, Zeit-Archaeologe

**Stil-DNS:**
- Raeumliche Typographie / Sprach-Explosionen
- Wort-Komposite, Fragmentierung
- Deutsch-Englisch-Hybrid
- Selbstironische Fussnoten: {psst! Meiner!}
- Existenzielle Desorientierung: "wo war ich...wo bin ich?"
- Mathematische Notation in lyrischem Kontext

**Zentrale Themen:** Mutter-Komplex (persoenlich + planetarisch), Euphemismus-Komplex,
Anti-Theologie, "fim" (feminin + inter + maskulin), 13 ReckIm.

**Chronologie:** 2009 (Leo.org) -> 2013 (Private Science Blog) -> 2014 (GOMXRB-P1-Validator v1)
-> 2005-2026 (OMX Ebook-Aera)

---

## 5. Behobene Bugs (Auswahl)

| Bug | Ursache | Loesung | Version |
|-----|---------|---------|---------|
| DuckDuckGo Impersonate-Crash | curl_cffi Profil veraltet + 3500-Zeichen-Query | Query-Guard (max 300) + Extraktion | v1.0 |
| openrouter/auto = teuer | Routet zu Opus ($0.03/Call) | Geaendert zu openrouter/free | v1.1 |
| NoneType-Crash Widerspruchs-Check | Mercury gibt None zurueck | Null-Safety (None -> "") | v1.2 |
| Surrogat-Crash bei API | Kaputte UTF-8 aus WP-Export | _sanitize_text() vor Calls | v2.1 |
| Chat-Historie korrupt | Nicht-atomares Schreiben | .tmp -> rename + .bak | v2.1 |
| Union-Find Explosion (Validator) | OR-Matching zu locker | Striktes content_sim >= 0.40 | Phase 4 |
| EPUB: Buchtitel statt Kapiteltitel | <title> aus <head> statt <body> | 3-Tier-Fallback Extraktion | Phase 4 |
| CSS-Leak in EPUB-Body | <style>-Inhalt nicht gestrippt | _clean_epub_body_text() | Phase 4 |

---

## 6. Offene Punkte

### Bugs
- [ ] **v1.2.1**: 0-Zeichen-Korrektur (leere Mercury-Antwort -> false-positive Widerspruch)

### Kurzfristig
- [ ] Neues Material (594 Dateien) in KB integrieren + ChromaDB reindexieren
- [ ] Review-Queue (128 Dateien in _archive/review/) manuell pruefen
- [ ] GitHub-Repo erstellen (Private) + CodeRabbit einrichten
- [ ] Zukunfts-Visionen als lokale Markdown-Dateien dokumentieren

### Mittelfristig
- [ ] Automatische Material-Integration (auto_integrate.py -- neues Material gegen KB pruefen)
- [ ] Supervisor-Rolle dokumentieren und re-onboarden (Gemini 3 oder anderes Modell)
- [ ] identity.md vom Bot selbst umschreiben lassen (nicht sachlich, sondern im OMX-Stil)
- [ ] Multi-Turn-Konversation (Chat-Historie an API senden)
- [ ] corrections.md Rotation (unbegrenztes Wachstum verhindern)

### Langfristig (Textus Vision)
- [ ] OMX-Validator -> generisches Stemmatik-Modul refactoren (4 Reifestufen)
- [ ] Web-Interface (Streamlit/Gradio) statt Docker-Terminal
- [ ] Verschnyx als Discord/Telegram-Bot
- [ ] Bot-generierte Blog-Posts im OMX-Stil

---

## 7. Dateien-Uebersicht

### Hauptverzeichnis
```
.gitignore                   Git-Konfiguration (ignoriert Pool, Secrets, Caches)
BRIEFING_PHASE2.md           Dieses Dokument
convert_wp_to_markdown.py    WordPress -> Markdown (1.338 Posts)
knowledge/                   1.189 bereinigte Markdown-Dateien
  _archive/safe/             672 sichere Duplikate
  _archive/review/           128 Duplikate mit einzigartigen Zeilen
media/                       118 Medien-Dateien
```

### Bot-Umgebung (verschnyx_env/)
```
logic_core.py                Bot-Kern v2.1 (~48 KB, ~1.306 Zeilen)
indexer.py                   ChromaDB-Indexer
extract_ebooks.py            Ebook-Extraktor
Dockerfile + docker-compose  Container-Setup
system_prompt.txt            Identitaets-Briefing
patches/                     3 modulare Code-Patches + Backups
omx_validator/               6-Phasen-Validierungs-Pipeline + KB-Dedup
scheduler/                   Overnight-Automatisierung
tests/                       A/B-Tests (Mercury vs Sonnet vs Opus)
memory/                      Runtime-Gedaechtnis (git-ignored)
  new_material/              594 neue Kapitel (OMX-Validator Output)
vectorstore/                 ChromaDB (~186 MB, git-ignored)
chroma_cache/                Embedding-Cache (~167 MB, git-ignored)
```

---

## 8. Wie man den Bot startet

```bash
cd verschnyx_env
cp .env.example .env         # API-Keys eintragen:
                             #   OPENROUTER_API_KEY=...
                             #   ANTHROPIC_API_KEY=...
docker compose up --build    # Erster Start (indexiert ~5 Min)
# Danach in separatem Terminal:
docker compose run --rm -i verschnyx
```

Wichtig: `docker compose run --rm -i verschnyx` (NICHT `docker attach`) fuer saubere Interaktion.

---

## 9. API-Kosten-Schaetzung

| Service | Nutzung | Kosten |
|---------|---------|--------|
| OpenRouter (free) | Tier 1 Standard | $0.00 |
| Mercury 2 (OpenRouter) | Tier 1 erweitertes Routing | Guenstig (~$0.001/Call) |
| Claude Sonnet 4 | Tier 2 (Analyse, Reflexion) | ~$0.01-0.05/Call |
| Claude Opus 4.6 | Tier 3 (selten, nur Essenz) | ~$0.03-0.10/Call |
| DuckDuckGo | Recherche | $0.00 |
| **Phase 2 gesamt** | | **<$2.00 geschaetzt** |
