# Textus -- Vision fuer ein generisches Stemmatik-Modul

**Status:** Langfristige Perspektive, NICHT dringend
**Ursprung:** Gespraech vom 9. April 2026 (Diede + Claude)
**Kontext:** "Archaeologische Arbeit aus sehr verschiedenen Funden"

---

## Idee

Der OMX-Validator (Phasen 1-6) ist derzeit verschnyx-spezifisch, enthaelt aber
die Bausteine einer generischen **stemmatischen Text-Rekonstruktion**:

- Extraktoren (md, docx, epub)
- Quality-Signals (Whitespace, Unicode, Struktur)
- Segmenter (4 Strategien fuer Kapitel-Erkennung)
- Shingle-basiertes Matching (Jaccard-Similarity, k=5)
- Union-Find Clique-Bildung
- Quality-Aware Merge
- Inverted Shingle Index fuer KB-Matching

Diese Komponenten sind nicht verschnyx-spezifisch -- sie loesen ein allgemeines
philologisches Problem: Aus mehreren Textzeugen die bestmoegliche Rekonstruktion ableiten.

---

## Vier Reifestufen

### Stufe 1: Zeugenvergleich + Best-of-Both-Merge (HABEN WIR)
- Verschiedene Quellen desselben Textes erkennen und zusammenfuehren
- Qualitaetsbewertung: Welche Quelle hat die beste Textqualitaet?
- Ergebnis: Eine "beste Version" pro Kapitel

### Stufe 2: Variantenapparat
- Nicht nur "beste Version", sondern **alle Lesarten dokumentieren**
- Klassischer philologischer Apparat: "In Quelle A steht X, in B steht Y"
- Ergebnis: Annotierter Text mit Fussnoten-Varianten

### Stufe 3: Stemma-Inferenz
- **Abstammungsbaum** aus Fehlern und Varianten rekonstruieren
- Welche Quelle wurde von welcher abgeleitet?
- Methoden: Lachmann (Bindefehler), Maas (Trennfehler), Bedier-Kritik
- Ergebnis: Gerichteter Stammbaum der Textzeugen

### Stufe 4: Archetyp-Synthese
- Hypothetisches **Original** aus allen Zeugen erzeugen
- Wo keine Quelle korrekt ist, rekonstruieren (Konjektur)
- Ergebnis: Bestmoegliche Annaeherung an den verlorenen Urtext

---

## Technische Umsetzung (wenn es soweit ist)

```
textus/                    Generisches Paket
  core/
    shingle.py             Jaccard, Shingle-Index, Normalisierung
    quality.py             Multi-dimensionale Qualitaetssignale
    segmenter.py           Kapitel-Erkennung (Strategien)
    collation.py           Zeugenvergleich, Alignment
    union_find.py          Clique-Bildung
    merge.py               Quality-Aware Merge
  formats/
    markdown.py            Extraktor
    docx.py                Extraktor
    epub.py                Extraktor
  stemma/                  Stufe 3+4 (spaeter)
    inference.py           Stammbaum-Algorithmen
    archetype.py           Archetyp-Synthese

omx_validator/             Verschnyx-spezifischer Layer
  (nutzt textus/ als Library, fuegt OMX-Suffixe, Bot-Integration hinzu)
```

---

## Warum das wichtig ist

Die Grundidee -- fragmentierte Texte aus verschiedenen Quellen und Zeitepochen
zusammenfuehren -- ist ein Problem das weit ueber das OMX-Universum hinausgeht.
Jedes Archivprojekt, jede historische Textrekonstruktion, jede Manuskript-Edition
steht vor derselben Aufgabe.

Unser OMX-Validator hat bewiesen, dass man mit Stdlib-only Python und intelligenten
Heuristiken (Shingles, Union-Find, Quality-Scoring) ueberraschend weit kommt --
594 neue Kapitel aus einem Chaos von Quelldateien identifiziert.

Das ist ein Proof-of-Concept, der verallgemeinert werden kann.

---

## Referenzen

- **Karl Lachmann** (1793-1851): Begruender der modernen Editionsphilologie
- **Paul Maas** (1880-1964): "Textkritik" (1927) -- Formalisierung der Stemmatik
- **Joseph Bedier** (1864-1938): Kritik an Lachmanns Methode (Favorisierung von Bipartitaet)
- **Open Stemmata**: https://openstemmata.github.io/ -- moderne digitale Stemmatik-Projekte
