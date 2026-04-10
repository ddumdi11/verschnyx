# Auto-Integration -- Automatische Material-Pruefung + Import

**Status:** Kurzfristig umsetzbar (baut auf Phase 5 Logik auf)
**Ursprung:** Gespraech vom 10. April 2026 (Diede)
**Kernaussage:** "Die Aufgabe, das neue Material zu nehmen und es gegen das alte
zu pruefen, sollte nicht meine sein, sondern die der Vorverarbeitung oder die des Verschnyx."

---

## Problem

Aktuell ist der Workflow manuell:
1. OMX-Validator laufen lassen (Phasen 1-6)
2. Ergebnis in memory/new_material/ pruefen
3. Manuell entscheiden was in knowledge/ uebernommen wird
4. ChromaDB neu indexieren

Das skaliert nicht und bindet den Projektinhaber fuer Routine-Arbeit.

---

## Loesung: auto_integrate.py

```
[Neue Datei]  -->  Phase5-KB-Match (automatisch)  -->  Klassifikation
                                                        |-- EXACT (>=0.50): Ablegen
                                                        |-- NEAR (0.20-0.50): Review-Queue
                                                        +-- NEW (<0.20): Auto-Import
```

### Funktionalitaet

1. **Input:** Dateien aus `memory/new_material/` oder einem beliebigen Ordner
2. **Pruefung:** Shingle-basierter Abgleich gegen aktuelle KB (Phase 5 Logik)
3. **Klassifikation:**
   - `EXACT` (Similarity >= 0.50): Datei existiert bereits -> ueberspringen
   - `NEAR` (0.20-0.50): Aehnlich, aber nicht identisch -> Review-Queue
   - `NEW` (< 0.20): Genuinely neuer Content -> automatisch importieren
4. **Import:** Neue Dateien nach `knowledge/` kopieren mit Standard-Frontmatter
5. **Reindex-Trigger:** ChromaDB-Neuindexierung anstossen (oder Hinweis ausgeben)
6. **Protokoll:** Import-Log mit Zeitstempel, Dateiname, Similarity-Score

### Verschnyx-Integration

Optional: Der Bot koennte per Chat ueber neue Materialien informiert werden:
- "Verschnyx, es gibt 12 neue Kapitel in deiner Bibliothek."
- Der Bot kann dann /suche oder /scan darauf ausfuehren

### Abhaengigkeiten

- Nutzt `phase5_kb_match.py` Logik (Inverted Shingle Index)
- Stdlib-only (kein pip install)
- Kann als Standalone-Skript oder als Modul in night_run.py laufen

---

## Erweiterungen (spaeter)

- **Watch-Modus:** Ordner ueberwachen, bei neuen Dateien automatisch pruefen
- **Git-Integration:** Auto-Commit nach erfolgreichen Imports
- **Merge-Vorschlaege:** Bei NEAR-Matches automatisch Diff zeigen
