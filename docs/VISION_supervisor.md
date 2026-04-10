# Supervisor-Rolle -- Multi-Modell-Projektsteuerung

**Status:** Konzept, nicht dringend
**Ursprung:** Phase 1 (Gemini 3 war als Supervisor eingesetzt, wurde seitdem sidelined)
**Kontext:** Diede arbeitet mit Claude + Gemini parallel an verschiedenen Aspekten

---

## Idee

Ein zweites KI-Modell (z.B. Gemini 3, oder ein anderes) uebernimmt die Rolle
eines **Projekt-Supervisors**, der:

1. **Code-Reviews** durchfuehrt (alternativ: CodeRabbit nach GitHub-Setup)
2. **Architektur-Entscheidungen** hinterfragt und validiert
3. **Fortschritt trackt** und auf offene Punkte hinweist
4. **Qualitaetssicherung** uebernimmt (Testabdeckung, Dokumentation)
5. **Gegenperspektive** bietet (vermeidet Tunnel-Vision eines einzelnen Modells)

---

## Warum ein Supervisor?

Claude (als Entwickler-Modell) neigt dazu:
- Loesungen sofort umzusetzen statt zurueckzutreten und das Gesamtbild zu pruefen
- Eigene frueheren Entscheidungen nicht kritisch zu hinterfragen
- Technische Schuld zu akkumulieren wenn kein Reviewer da ist

Ein Supervisor-Modell wuerde:
- Nach jedem groesseren Feature-Block eine Retrospektive machen
- Die BRIEFING-Datei als "Projektplan" pflegen
- Inkonsistenzen zwischen Doku und Code aufdecken
- Prioritaeten vorschlagen basierend auf Projektzielen

---

## Onboarding-Material fuer den Supervisor

Ein neuer Supervisor braucht:
1. **BRIEFING_PHASE2.md** -- Gesamtueberblick
2. **CHANGELOG.md** -- Was wurde wann gemacht
3. **docs/ROADMAP.md** -- Priorisierte naechste Schritte
4. **Zugang zum Repo** -- Code lesen koennen
5. **Kontext zum Projektinhaber** -- Diede's Arbeitsweise und Praeferenzen

### Praeferenzen des Projektinhabers (Diede)
- Kommuniziert auf Deutsch
- Bevorzugt pragmatische Loesungen gegenueber theoretischer Perfektion
- Arbeitet oft abends/nachts (daher Overnight-Scheduler)
- Erwartet Eigeninitiative aber keine uebermaessige Proaktivitaet
- Schaetzt wenn KI-Modelle ihre Grenzen eingestehen
- Nutzt Stdlib-only Ansatz (keine unnoetige Dependency-Last)

---

## Offene Fragen

- Welches Modell eignet sich am besten als Supervisor? (Gemini 3? Anderes?)
- Wie kommuniziert der Supervisor mit dem Entwickler-Modell? (Shared Docs? Chat?)
- Braucht der Supervisor eigene Tools oder reicht Dokumenten-Zugang?
- Wie oft soll die Supervision stattfinden? (Nach jedem Feature? Woechentlich?)
