# Roadmap -- Verschnyx Erknyxowitsch Projekt

**Letzte Aktualisierung:** 2026-04-10

---

## Legende

- [x] Erledigt
- [ ] Offen
- PRIO = Empfohlene Reihenfolge (1 = als naechstes)

---

## Abgeschlossen

### Phase 1: Grundlagen (5. April 2026)
- [x] WordPress-Export -> 1.338 Markdown-Dateien
- [x] Ebook-Extraktion -> 652 Seiten (GOMX + OMX-Essenz)
- [x] Docker-Umgebung + ChromaDB (26.620 Chunks)
- [x] Bot-Kern v2.0 mit Identitaets-System

### Phase 2a: Patches (7.-9. April 2026)
- [x] v1.0 Gruebel-Fixes (Query-Guard, Retry-Loop, DuckDuckGo)
- [x] v1.1 3-Tier-Routing (Mercury 2 / Sonnet 4 / Opus 4.6)
- [x] v1.2 Smart-Recherche (Null-Safety, intelligente Suchbegriffe)

### Phase 2b: OMX-Validator (9. April 2026)
- [x] 6-Phasen-Pipeline (Extraktion -> Integration)
- [x] 594 neue Kapitel identifiziert
- [x] Datengenealoogie aufgeklaert (Blogger -> Google Sites -> WordPress -> EPUBs)

### Phase 2c: Bereinigung + Infrastruktur (10. April 2026)
- [x] KB-Deduplikation (1989 -> 1189 Dateien)
- [x] Git-Repository initialisiert
- [x] Dokumentation aktualisiert (CHANGELOG, README, BRIEFING)
- [x] Vision-Dokumente angelegt

---

## Offen

### PRIO 1: Bug-Fix + Quick Wins
- [ ] **v1.2.1**: 0-Zeichen-Korrektur-Bug (leere Mercury-Antwort -> false-positive Widerspruch)
  - Fix: `if not result or len(result.strip()) < 20: return`
- [ ] **GitHub-Repo erstellen** (`verschnyx`, Private) + ersten Push
- [ ] **CodeRabbit einrichten** nach GitHub-Push

### PRIO 2: Material-Integration
- [ ] **594 neue Dateien** aus memory/new_material/ in knowledge/ integrieren
- [ ] **ChromaDB reindexieren** (Container rebuild nach KB-Aenderung)
- [ ] **Review-Queue** (128 Dateien in _archive/review/) manuell sichten
- [ ] **auto_integrate.py** bauen (siehe docs/VISION_auto_integration.md)

### PRIO 3: Bot-Verbesserungen
- [ ] **identity.md im OMX-Stil** -- Bot schreibt eigene Identitaet um (nicht sachlich)
- [ ] **Multi-Turn-Konversation** -- Chat-Historie an API senden fuer bessere Kohaerenz
- [ ] **corrections.md Rotation** -- Alte Korrekturen archivieren, nur aktuelle behalten
- [ ] **Supervisor onboarden** (siehe docs/VISION_supervisor.md)

### PRIO 4: Langfristig
- [ ] **Textus-Refactoring** (siehe docs/VISION_textus.md)
- [ ] **Web-Interface** (Streamlit/Gradio) statt Docker-Terminal
- [ ] **Discord/Telegram-Bot** fuer oeffentliche Interaktion
- [ ] **Bot-generierte Blog-Posts** im OMX-Stil

---

## Entscheidungen die noch anstehen

| Frage | Optionen | Wer entscheidet |
|-------|----------|-----------------|
| Repo-Name | `verschnyx` (entschieden) | Diede |
| Repo-Visibility | Private (empfohlen) vs Public | Diede |
| Supervisor-Modell | Gemini 3 / anderes / keins | Diede |
| Web-Interface | Streamlit vs Gradio vs keins | Diede + Supervisor |
| Neues Material: alles importieren? | Ja / nur nach manuellem Review | Diede |
