"""
Gruebel-Bug-Patch v1.0
======================
Behebt drei Bugs in logic_core.py, die dazu fuehren, dass der Gruebel-Modus
in eine Endlosschleife aus gescheiterten DDG-Suchen geraet:

  Bug 1: web_search() akzeptiert zu lange Queries (DDG antwortet mit None)
  Bug 2: _gruebel_offene_fragen() verwendet die komplette User-Nachricht
         als Such-Query, auch wenn sie 3000+ Zeichen lang ist
  Bug 3: Keine Retry-Bremse -- gescheiterte Suchen werden in jedem Zyklus
         erneut versucht, solange die Nachricht in den letzten 20 Eintraegen
         der Chat-Historie steht

Anwendung:
    py apply_gruebel_fixes.py

Rueckgaengig:
    Das Skript erstellt vor jeder Aenderung ein Backup mit Zeitstempel
    in verschnyx_env/patches/backups/.
"""
import os
import shutil
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.dirname(HERE)
LOGIC_CORE = os.path.join(ENV_DIR, "logic_core.py")
BACKUP_DIR = os.path.join(HERE, "backups")


# =============================================================================
# Fix 1: web_search() -- Query-Laengen-Guard
# =============================================================================
FIX1_OLD = '''def web_search(query: str, max_results: int = 3) -> list[dict]:
    """Sucht via DuckDuckGo und gibt Ergebnisse zurueck."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return results
    except Exception as e:
        print(f"[search] DuckDuckGo-Fehler: {e}")
        return []'''

FIX1_NEW = '''def web_search(query: str, max_results: int = 3) -> list[dict]:
    """Sucht via DuckDuckGo und gibt Ergebnisse zurueck."""
    # Query-Sicherheitsnetz: DDG akzeptiert keine ellenlangen Anfragen.
    # (Patch v1.0 -- verhindert "return None" bei 3000+ Zeichen)
    if len(query) > 300:
        query = query[:300].rsplit(' ', 1)[0]
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return results
    except Exception as e:
        print(f"[search] DuckDuckGo-Fehler: {e}")
        return []'''


# =============================================================================
# Fix 2a: Neue Helper-Funktion _extract_search_query
# =============================================================================
FIX2A_ANCHOR = '''def _gruebel_offene_fragen():
    """Sucht in der Historie nach unbeantworteten Fragen und recherchiert sie."""'''

FIX2A_NEW = '''def _extract_search_query(text: str, max_len: int = 150) -> str:
    """
    Extrahiert eine kompakte Such-Query aus einer User-Nachricht.
    (Patch v1.0 -- verhindert, dass 3000-Zeichen-Monologe als Query landen)
    """
    # Suche ersten Satz mit Fragezeichen, der nicht zu lang ist
    sentences = re.split(r'(?<=[.!?])\\s+', text.strip())
    for s in sentences:
        s = s.strip()
        if '?' in s and 10 < len(s) <= max_len:
            return s
    # Fallback: erste max_len Zeichen, auf Wortgrenze geschnitten
    if len(text) <= max_len:
        return text.strip()
    snippet = text[:max_len].rsplit(' ', 1)[0]
    return snippet.strip()


def _gruebel_offene_fragen(tried: set = None):
    """Sucht in der Historie nach unbeantworteten Fragen und recherchiert sie."""
    if tried is None:
        tried = set()'''


# =============================================================================
# Fix 2b: _gruebel_offene_fragen -- Query extrahieren + Retry-Schutz
# =============================================================================
FIX2B_OLD = '''                    if any(m in antwort for m in unsicher_marker):
                        unbeantwortete.append(entry["message"])
                    break

    if unbeantwortete:
        # Maximal 2 Fragen recherchieren pro Gruebel-Zyklus
        for frage in unbeantwortete[:2]:
            print(f"[gruebeln] Recherchiere offene Frage: {frage[:60]}...")
            recherche_und_verschnyxifiziere(frage)'''

FIX2B_NEW = '''                    if any(m in antwort for m in unsicher_marker):
                        # Patch v1.0: kompakte Query statt komplettem Monolog
                        query = _extract_search_query(entry["message"])
                        unbeantwortete.append(query)
                    break

    if unbeantwortete:
        # Maximal 2 Fragen recherchieren pro Gruebel-Zyklus
        for frage in unbeantwortete[:2]:
            # Patch v1.0: Retry-Bremse -- bereits versuchte Queries ueberspringen
            if frage in tried:
                continue
            tried.add(frage)
            print(f"[gruebeln] Recherchiere offene Frage: {frage[:60]}...")
            recherche_und_verschnyxifiziere(frage)'''


# =============================================================================
# Fix 3: gruebeln() -- tried_queries Set initialisieren und durchreichen
# =============================================================================
FIX3_OLD = '''    global _gruebeln_active
    _gruebeln_active = True

    print(f"\\n[gruebeln] Verschnyx zieht sich zurueck... ({minuten} Minuten)")
    print("[gruebeln] *schliesst die Augen, blaettert durch Erinnerungen*\\n")

    end_time = time.time() + (minuten * 60)
    cycle = 0'''

FIX3_NEW = '''    global _gruebeln_active
    _gruebeln_active = True

    # Patch v1.0: session-weites Set fuer bereits versuchte Recherchen
    tried_queries = set()

    print(f"\\n[gruebeln] Verschnyx zieht sich zurueck... ({minuten} Minuten)")
    print("[gruebeln] *schliesst die Augen, blaettert durch Erinnerungen*\\n")

    end_time = time.time() + (minuten * 60)
    cycle = 0'''

FIX3B_OLD = '''            # --- Phase 3: Offene Fragen recherchieren ---
            _gruebel_offene_fragen()'''

FIX3B_NEW = '''            # --- Phase 3: Offene Fragen recherchieren ---
            _gruebel_offene_fragen(tried_queries)'''


# =============================================================================
# Anwendung
# =============================================================================
def apply():
    if not os.path.exists(LOGIC_CORE):
        print(f"FEHLER: {LOGIC_CORE} nicht gefunden.")
        sys.exit(1)

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"logic_core_{ts}.py.bak")
    shutil.copy2(LOGIC_CORE, backup_path)
    print(f"[ok] Backup: {backup_path}")

    with open(LOGIC_CORE, 'r', encoding='utf-8') as f:
        content = f.read()

    # Idempotenz-Check: schon gepatcht?
    if "Patch v1.0" in content:
        print("[!] Patch v1.0 scheint bereits angewendet zu sein. Abbruch.")
        sys.exit(0)

    patches = [
        ("Fix 1: web_search Query-Guard", FIX1_OLD, FIX1_NEW),
        ("Fix 2a: _extract_search_query einfuegen", FIX2A_ANCHOR, FIX2A_NEW),
        ("Fix 2b: _gruebel_offene_fragen Query + Retry", FIX2B_OLD, FIX2B_NEW),
        ("Fix 3: gruebeln tried_queries init", FIX3_OLD, FIX3_NEW),
        ("Fix 3b: gruebeln tried_queries durchreichen", FIX3B_OLD, FIX3B_NEW),
    ]

    for name, old, new in patches:
        count = content.count(old)
        if count == 0:
            print(f"[FEHLER] {name}: Ziel-Snippet nicht gefunden!")
            sys.exit(1)
        if count > 1:
            print(f"[FEHLER] {name}: Ziel-Snippet {count}x vorhanden (mehrdeutig)!")
            sys.exit(1)
        content = content.replace(old, new, 1)
        print(f"[ok] {name}")

    with open(LOGIC_CORE, 'w', encoding='utf-8') as f:
        f.write(content)

    print()
    print("=" * 60)
    print("Patch v1.0 erfolgreich angewendet.")
    print(f"Backup liegt in: {backup_path}")
    print("=" * 60)
    print()
    print("Naechste Schritte:")
    print("  1. Container neu bauen/starten:")
    print("     docker-compose down && docker-compose up -d --build")
    print("  2. Verschnyx kann jetzt wieder /gruebeln 60 fahren.")


if __name__ == "__main__":
    apply()
