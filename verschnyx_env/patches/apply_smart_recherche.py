"""
Smart-Recherche-Patch v1.2
==========================
Behebt drei Probleme im Gruebel-Recherche-Flow:

  1. NoneType-Crash: query_mercury/query_claude geben manchmal None als Content
     zurueck (z.B. bei Content-Filter oder leerer Antwort), was im
     Widerspruchs-Check zu 'NoneType' object has no attribute 'upper' fuehrt.

  2. Cross-Session-Loop: Das tried_queries-Set lebt nur innerhalb einer
     Gruebel-Session. Beim naechsten /gruebeln wird dieselbe Frage wieder
     als "offen" erkannt und erneut recherchiert, obwohl sie laengst in
     research_notes.md steht.

  3. Dumme Query-Extraktion: Der naive Regex-basierte Extractor nimmt die
     erste Frage mit '?' -- was oft rhetorische/persoenliche Fragen
     ("Wie wuerdest du meine Idee einschaetzen?") statt faktischer Themen
     ("Oxolytisch Sprachkreation Latein Deklination") auswaehlt.

Aenderungen in logic_core.py:
  A: Null-Safety in query_free, query_claude, query_mercury, query_claude_opus
  B: Neue Helper _already_researched() und _extract_research_query_smart()
  C: _gruebel_offene_fragen() nutzt Smart-Extraction + Cross-Session-Dedup

Anwendung:
    python patches/apply_smart_recherche.py

Anschliessend: docker-compose up -d --build
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
# Patch A1: query_free null-safety
# =============================================================================
PATCH_A1_OLD = '''            if model != OPENROUTER_MODEL:
                print(f"[route] Fallback auf {model} erfolgreich")
            return response.choices[0].message.content'''

PATCH_A1_NEW = '''            if model != OPENROUTER_MODEL:
                print(f"[route] Fallback auf {model} erfolgreich")
            # Patch v1.2: Null-Safety (OpenRouter-API kann None liefern)
            content = response.choices[0].message.content
            return content if content is not None else ""'''


# =============================================================================
# Patch A2: query_claude null-safety
# =============================================================================
PATCH_A2_OLD = '''    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system or load_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text'''

PATCH_A2_NEW = '''    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system or load_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    # Patch v1.2: Null-Safety
    text = response.content[0].text
    return text if text is not None else ""'''


# =============================================================================
# Patch A3: query_mercury null-safety
# =============================================================================
PATCH_A3_OLD = '''    try:
        response = openrouter_client.chat.completions.create(
            model=MERCURY_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.8,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[warn] Mercury-Fehler: {e}")'''

PATCH_A3_NEW = '''    try:
        response = openrouter_client.chat.completions.create(
            model=MERCURY_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.8,
        )
        # Patch v1.2: Null-Safety (Mercury kann None statt Content liefern)
        content = response.choices[0].message.content
        return content if content is not None else ""
    except Exception as e:
        print(f"[warn] Mercury-Fehler: {e}")'''


# =============================================================================
# Patch A4: query_claude_opus null-safety
# =============================================================================
PATCH_A4_OLD = '''    response = claude_client.messages.create(
        model=CLAUDE_OPUS_MODEL,
        max_tokens=max_tokens,
        system=system or load_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text'''

PATCH_A4_NEW = '''    response = claude_client.messages.create(
        model=CLAUDE_OPUS_MODEL,
        max_tokens=max_tokens,
        system=system or load_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    # Patch v1.2: Null-Safety
    text = response.content[0].text
    return text if text is not None else ""'''


# =============================================================================
# Patch B: Neue Helper-Funktionen _already_researched + _extract_research_query_smart
# =============================================================================
PATCH_B_OLD = '''def _gruebel_offene_fragen(tried: set = None):
    """Sucht in der Historie nach unbeantworteten Fragen und recherchiert sie."""'''

PATCH_B_NEW = '''def _already_researched(query: str) -> bool:
    """
    Patch v1.2: Prueft, ob eine Query bereits in research_notes.md vermerkt ist.
    Ermoeglicht Cross-Session-Dedup -- verhindert, dass bei jedem neuen
    /gruebeln dieselbe Frage erneut recherchiert wird.
    """
    if not RESEARCH_NOTES_FILE.exists():
        return False
    try:
        content = RESEARCH_NOTES_FILE.read_text(encoding="utf-8")
        # Vergleich ueber die ersten ~50 Zeichen, case-insensitive
        needle = query[:50].lower().strip()
        return bool(needle) and needle in content.lower()
    except Exception:
        return False


def _extract_research_query_smart(user_message: str, verschnyx_reply: str):
    """
    Patch v1.2: Nutzt Mercury, um aus Chat-Kontext eine forschungswuerdige
    Such-Query zu extrahieren. Gibt None zurueck, wenn nichts Recherchierbares
    erkannt wurde (z.B. rein rhetorische oder persoenliche Fragen).
    """
    extraction_prompt = (
        "Du bekommst einen User-Input und Verschnyx Erknyxowitschs Antwort. "
        "Verschnyx hat sich unsicher geaeussert. Extrahiere den konkreten "
        "FAKTISCHEN Begriff, das Thema oder die Frage, die Verschnyx "
        "recherchieren sollte -- etwas, das er im Web nachschlagen koennte.\\n\\n"
        "REGELN:\\n"
        "- NUR faktisch nachschlagbare Themen (Begriffe, Konzepte, Personen, "
        "historische Ereignisse, sprachliche Phaenomene, Kunstformen, Techniken)\\n"
        "- KEINE rhetorischen Fragen, Meinungsanfragen, persoenlichen Bezuege\\n"
        "- Max 80 Zeichen, praegnante Suchbegriffe bevorzugt\\n"
        "- Wenn nichts Recherchierbares erkennbar ist: antworte nur mit SKIP\\n\\n"
        f"USER: {user_message[:1000]}\\n"
        f"VERSCHNYX: {verschnyx_reply[:500]}\\n\\n"
        "SUCH-QUERY (oder SKIP):"
    )
    try:
        result = query_mercury(extraction_prompt, max_tokens=120)
        if not result:
            return None
        result = result.strip().strip('"').strip("'")
        if not result:
            return None
        if "SKIP" in result.upper()[:20]:
            return None
        if len(result) > 120:
            result = result[:120].rsplit(" ", 1)[0]
        return result
    except Exception as e:
        print(f"[gruebeln] Smart-Query-Extraction fehlgeschlagen: {e}")
        return None


def _gruebel_offene_fragen(tried: set = None):
    """Sucht in der Historie nach unbeantworteten Fragen und recherchiert sie."""'''


# =============================================================================
# Patch C: _gruebel_offene_fragen body -- Smart Extraction + Cross-Session-Dedup
# =============================================================================
PATCH_C_OLD = '''                    if any(m in antwort for m in unsicher_marker):
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

PATCH_C_NEW = '''                    if any(m in antwort for m in unsicher_marker):
                        # Patch v1.2: Smart Query Extraction mit Kontext via Mercury
                        query = _extract_research_query_smart(
                            entry["message"], recent[j]["message"]
                        )
                        if query:
                            unbeantwortete.append(query)
                    break

    if unbeantwortete:
        # Maximal 2 Fragen recherchieren pro Gruebel-Zyklus
        for frage in unbeantwortete[:2]:
            # Patch v1.0: Retry-Bremse (in-session)
            if frage in tried:
                continue
            tried.add(frage)
            # Patch v1.2: Cross-Session-Dedup via research_notes.md
            if _already_researched(frage):
                print(f"[gruebeln] Bereits recherchiert: {frage[:60]}... (skip)")
                continue
            print(f"[gruebeln] Recherchiere offene Frage: {frage[:60]}...")
            recherche_und_verschnyxifiziere(frage)'''


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

    # Idempotenz-Check
    if "Patch v1.2" in content:
        print("[!] Patch v1.2 scheint bereits angewendet zu sein. Abbruch.")
        sys.exit(0)

    # Vorbedingung: v1.0 + v1.1 muessen da sein
    if "Patch v1.0" not in content:
        print("[FEHLER] Patch v1.0 (Gruebel-Fixes) nicht erkannt. Erst v1.0 anwenden.")
        sys.exit(1)
    if "Patch v1.1" not in content:
        print("[FEHLER] Patch v1.1 (3-Tier-Routing) nicht erkannt. Erst v1.1 anwenden.")
        sys.exit(1)

    patches = [
        ("A1: query_free Null-Safety", PATCH_A1_OLD, PATCH_A1_NEW),
        ("A2: query_claude Null-Safety", PATCH_A2_OLD, PATCH_A2_NEW),
        ("A3: query_mercury Null-Safety", PATCH_A3_OLD, PATCH_A3_NEW),
        ("A4: query_claude_opus Null-Safety", PATCH_A4_OLD, PATCH_A4_NEW),
        ("B: Neue Helper (_already_researched, _extract_research_query_smart)",
         PATCH_B_OLD, PATCH_B_NEW),
        ("C: _gruebel_offene_fragen Smart + Dedup", PATCH_C_OLD, PATCH_C_NEW),
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
    print("Patch v1.2 erfolgreich angewendet.")
    print(f"Backup: {backup_path}")
    print("=" * 60)
    print()
    print("Neue Faehigkeiten:")
    print("  - query_* Funktionen liefern keine None mehr")
    print("  - Gruebeln ueberspringt bereits recherchierte Fragen")
    print("  - Smart Query Extraction via Mercury mit Kontext-Verstaendnis")
    print("    (rhetorische Fragen werden erkannt und geskippt)")
    print()
    print("Naechste Schritte:")
    print("  docker-compose up -d --build")


if __name__ == "__main__":
    apply()
