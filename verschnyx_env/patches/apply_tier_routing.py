"""
3-Tier-Routing-Patch v1.1
=========================
Ersetzt das binaere Free/Claude-Routing durch eine 3-stufige Hierarchie:

  Tier 1 (Default): Mercury 2 via OpenRouter    -- Daily Driver, schnell, billig
  Tier 2 (Qualitaet): Claude Sonnet 4 direkt    -- Stil, Kreativitaet, Deutung
  Tier 3 (Exzellenz): Claude Opus 4.6 direkt    -- nur fuer besondere Momente

Hintergrund:
Der A/B-Test am 2026-04-08 hat ergeben, dass `openrouter/auto` (bisher als
"Free-Modell" genutzt) in Wahrheit auf Claude Opus 4.6 routet -- das teuerste
Modell. Dadurch verursachte der "Free"-Pfad ca. $0.025-0.035 pro Call.
Mercury 2 bietet 10x Speed und ~30x niedrigere Kosten bei soliden Routine-
Qualitaeten. Sonnet/Opus bleiben als bewusste Upgrades fuer Qualitaet bzw.
Exzellenz reserviert.

Aenderungen in logic_core.py:
  1. Modell-Konfiguration erweitert (MERCURY_MODEL, CLAUDE_OPUS_MODEL)
  2. FREE_MODEL_FALLBACKS von "openrouter/auto" auf "openrouter/free" gesetzt
  3. Neue Funktionen query_mercury() und query_claude_opus()
  4. TaskRouter komplett neu mit 3-Tier-Logik und neuen Keyword-Sets
  5. Direkte query_free()-Aufrufe migriert:
     - Stilistische Transformation -> query_claude (Sonnet)
     - Routine-Widerspruchs-Check -> query_mercury
     - Identitaets-Fallback        -> query_mercury

Anwendung:
    py patches/apply_tier_routing.py

Anschliessend: docker-compose down && docker-compose up -d --build
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
# Patch A: Modell-Konfiguration erweitern
# =============================================================================
PATCH_A_OLD = '''FREE_MODEL_FALLBACKS = [
    "openrouter/auto",
]

def _resolve_openrouter_model() -> str:
    env_model = os.getenv("OPENROUTER_MODEL", "").strip()
    return env_model if env_model else FREE_MODEL_FALLBACKS[0]

def _resolve_claude_model() -> str:
    env_model = os.getenv("CLAUDE_MODEL", "").strip()
    return env_model if env_model else "claude-sonnet-4-20250514"

OPENROUTER_MODEL = _resolve_openrouter_model()
CLAUDE_MODEL = _resolve_claude_model()'''

PATCH_A_NEW = '''# Patch v1.1: 3-Tier-Routing
# Tier 0 (Notfall-Fallback): openrouter/free routet nur zu kostenlosen Modellen
# (im Gegensatz zu openrouter/auto, das auch Paid-Modelle auswaehlt!)
FREE_MODEL_FALLBACKS = [
    "openrouter/free",
]

def _resolve_openrouter_model() -> str:
    env_model = os.getenv("OPENROUTER_MODEL", "").strip()
    return env_model if env_model else FREE_MODEL_FALLBACKS[0]

# Tier 1: Mercury 2 -- Daily Driver (Patch v1.1)
def _resolve_mercury_model() -> str:
    env_model = os.getenv("MERCURY_MODEL", "").strip()
    return env_model if env_model else "inception/mercury-2"

# Tier 2: Claude Sonnet -- Qualitaet
def _resolve_claude_model() -> str:
    env_model = os.getenv("CLAUDE_MODEL", "").strip()
    return env_model if env_model else "claude-sonnet-4-20250514"

# Tier 3: Claude Opus -- Exzellenz (Patch v1.1)
def _resolve_claude_opus_model() -> str:
    env_model = os.getenv("CLAUDE_OPUS_MODEL", "").strip()
    return env_model if env_model else "claude-opus-4-6"

OPENROUTER_MODEL = _resolve_openrouter_model()
MERCURY_MODEL = _resolve_mercury_model()
CLAUDE_MODEL = _resolve_claude_model()
CLAUDE_OPUS_MODEL = _resolve_claude_opus_model()'''


# =============================================================================
# Patch B: init_clients() -- Print fuer Mercury
# =============================================================================
PATCH_B_OLD = '''        print(f"[init] OpenRouter-Client bereit  (Modell: {OPENROUTER_MODEL})")'''

PATCH_B_NEW = '''        print(f"[init] OpenRouter-Client bereit  (Mercury: {MERCURY_MODEL}, Fallback: {OPENROUTER_MODEL})")'''


# =============================================================================
# Patch C: Neue Funktionen query_mercury + query_claude_opus
# =============================================================================
PATCH_C_OLD = '''    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system or load_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


class TaskRouter:
    CLAUDE_KEYWORDS = [
        "analyse", "kreativ", "schreib", "dicht", "essay",
        "tiefgehend", "komplex", "zusammenfass", "identitaet",
        "reflekti", "interpret",
    ]'''

PATCH_C_NEW = '''    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system or load_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def query_mercury(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    """
    Patch v1.1: Tier 1 -- Mercury 2 als Daily Driver.
    Ruft inception/mercury-2 via OpenRouter auf. Schnell und guenstig
    fuer Routine-Aufgaben (Chat, Widerspruchs-Check, Tagebuch).
    Fallback-Kette: Mercury -> Sonnet -> Free.
    """
    if not openrouter_client:
        raise RuntimeError("OpenRouter-Client nicht initialisiert")

    prompt = _sanitize_text(prompt)
    system = _sanitize_text(system)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = openrouter_client.chat.completions.create(
            model=MERCURY_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.8,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[warn] Mercury-Fehler: {e}")
        if claude_client:
            print("[route] Fallback: Mercury -> Sonnet")
            return query_claude(prompt, system, max_tokens)
        print("[route] Notfall-Fallback: Mercury -> Free")
        return query_free(prompt, system, max_tokens)


def query_claude_opus(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    """
    Patch v1.1: Tier 3 -- Claude Opus fuer Exzellenz-Aufgaben.
    Nur fuer wirklich besondere Momente (tief-kreative Synthesen, grosse
    Identitaets-Updates, Abschluss-Reflexionen). Teuer, langsam, aber
    unvergleichlich fuer komplexe kreative Arbeit.
    """
    if not claude_client:
        raise RuntimeError("Claude-Client nicht initialisiert")

    prompt = _sanitize_text(prompt)
    system = _sanitize_text(system) if system else ""

    response = claude_client.messages.create(
        model=CLAUDE_OPUS_MODEL,
        max_tokens=max_tokens,
        system=system or load_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


class TaskRouter:
    # Patch v1.1: 3-Tier-Routing statt binaer
    # Tier 3: Exzellenz -- nur fuer besondere Gelegenheiten
    OPUS_KEYWORDS = [
        "essenz", "gesamtwerk", "identitaets-update",
        "grosse synthese", "abschluss-reflexion", "tief kreativ",
    ]
    # Tier 2: Qualitaet -- fuer Stil, Reflexion, Kreatives, Deutung
    SONNET_KEYWORDS = [
        "analyse", "essay", "reflekti", "interpret", "deute",
        "philosoph", "identitaet", "kreativ", "dicht", "schreib",
        "widerspruch", "korrektur", "kommentier", "zusammenfass",
        "verschnyxifizier", "tiefgehend", "komplex",
    ]
    # Tier 1 (Default): Mercury 2 -- alles andere

    # Legacy-Alias fuer Rueckwaertskompatibilitaet
    CLAUDE_KEYWORDS = SONNET_KEYWORDS'''


# =============================================================================
# Patch D: TaskRouter.route() -- 3-Tier-Logik
# =============================================================================
PATCH_D_OLD = '''    @staticmethod
    def route(prompt: str, force_model: str = None) -> str:
        system = load_system_prompt()

        if force_model == "claude":
            return query_claude(prompt, system)
        if force_model == "free":
            return query_free(prompt, system)

        prompt_lower = prompt.lower()
        use_claude = any(kw in prompt_lower for kw in TaskRouter.CLAUDE_KEYWORDS)

        if use_claude and claude_client:
            print("[route] -> Claude (komplexe Aufgabe)")
            return query_claude(prompt, system)
        elif openrouter_client:
            print("[route] -> Free-Modell (Recherche/Standard)")
            return query_free(prompt, system)
        elif claude_client:
            print("[route] -> Claude (Fallback)")
            return query_claude(prompt, system)
        else:
            raise RuntimeError("Kein Modell verfuegbar -- API-Keys pruefen")'''

PATCH_D_NEW = '''    @staticmethod
    def route(prompt: str, force_model: str = None) -> str:
        system = load_system_prompt()

        # Patch v1.1: erweiterte force_model-Optionen
        if force_model == "opus":
            return query_claude_opus(prompt, system)
        if force_model in ("claude", "sonnet"):
            return query_claude(prompt, system)
        if force_model == "mercury":
            return query_mercury(prompt, system)
        if force_model == "free":
            return query_free(prompt, system)

        prompt_lower = prompt.lower()
        use_opus = any(kw in prompt_lower for kw in TaskRouter.OPUS_KEYWORDS)
        use_sonnet = any(kw in prompt_lower for kw in TaskRouter.SONNET_KEYWORDS)

        if use_opus and claude_client:
            print("[route] -> Opus 4.6 (Exzellenz)")
            return query_claude_opus(prompt, system)
        elif use_sonnet and claude_client:
            print("[route] -> Sonnet 4 (Qualitaet)")
            return query_claude(prompt, system)
        elif openrouter_client:
            print("[route] -> Mercury 2 (Standard)")
            return query_mercury(prompt, system)
        elif claude_client:
            print("[route] -> Sonnet 4 (Fallback)")
            return query_claude(prompt, system)
        else:
            raise RuntimeError("Kein Modell verfuegbar -- API-Keys pruefen")'''


# =============================================================================
# Patch E: Direkte Aufrufe migrieren
# =============================================================================
# E1: _verschnyxify (Zeile ~467) -- stilistische Transformation -> Sonnet
PATCH_E1_OLD = '''    try:
        return query_free(prompt, max_tokens=1500)
    except Exception:
        # Fallback: Text so lassen
        return text'''

PATCH_E1_NEW = '''    try:
        # Patch v1.1: stilistische Transformation -> Sonnet (Tier 2)
        if claude_client:
            return query_claude(prompt, max_tokens=1500)
        return query_mercury(prompt, max_tokens=1500)
    except Exception:
        # Fallback: Text so lassen
        return text'''

# E2: recherche_und_verschnyxifiziere (Zeile ~540)
PATCH_E2_OLD = '''    try:
        note = query_free(prompt, max_tokens=800)
    except Exception:
        note = f"[Recherche-Fragment] {query} -- {raw_text[:200]}"'''

PATCH_E2_NEW = '''    try:
        # Patch v1.1: Verschnyxifizierung -> Sonnet (Tier 2)
        if claude_client:
            note = query_claude(prompt, max_tokens=800)
        else:
            note = query_mercury(prompt, max_tokens=800)
    except Exception:
        note = f"[Recherche-Fragment] {query} -- {raw_text[:200]}"'''

# E3: Identitaets-Synthese (Zeile ~651) -- Notfall-Fallback auf Mercury statt Free
PATCH_E3_OLD = '''    try:
        if claude_client:
            result = query_claude(synthesis_prompt, max_tokens=1500)
        elif openrouter_client:
            result = query_free(synthesis_prompt, max_tokens=1500)
        else:
            print("[identity] Kein Modell verfuegbar")
            return'''

PATCH_E3_NEW = '''    try:
        if claude_client:
            # Patch v1.1: Identitaets-Synthese -> Sonnet (Tier 2)
            result = query_claude(synthesis_prompt, max_tokens=1500)
        elif openrouter_client:
            # Patch v1.1: Notfall-Fallback -> Mercury statt Free
            result = query_mercury(synthesis_prompt, max_tokens=1500)
        else:
            print("[identity] Kein Modell verfuegbar")
            return'''

# E4: _gruebel_widerspruch_check (Zeile ~785)
PATCH_E4_OLD = '''    try:
        result = query_free(prompt, max_tokens=500)
        if "KEINE WIDERSPRUECHE" not in result.upper():
            print(f"[gruebeln] Widerspruch gefunden!")
            _write_correction(result)
    except Exception as e:
        print(f"[gruebeln] Widerspruchs-Check Fehler: {e}")'''

PATCH_E4_NEW = '''    try:
        # Patch v1.1: Widerspruchs-Check -> Mercury (Tier 1, Routine)
        result = query_mercury(prompt, max_tokens=500)
        if "KEINE WIDERSPRUECHE" not in result.upper():
            print(f"[gruebeln] Widerspruch gefunden!")
            _write_correction(result)
    except Exception as e:
        print(f"[gruebeln] Widerspruchs-Check Fehler: {e}")'''


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
    if "Patch v1.1" in content:
        print("[!] Patch v1.1 scheint bereits angewendet zu sein. Abbruch.")
        sys.exit(0)

    patches = [
        ("A: Modell-Konfiguration (Mercury + Opus)", PATCH_A_OLD, PATCH_A_NEW),
        ("B: init_clients Mercury-Print", PATCH_B_OLD, PATCH_B_NEW),
        ("C: query_mercury + query_claude_opus + Keyword-Sets", PATCH_C_OLD, PATCH_C_NEW),
        ("D: TaskRouter.route 3-Tier-Logik", PATCH_D_OLD, PATCH_D_NEW),
        ("E1: _verschnyxify -> Sonnet", PATCH_E1_OLD, PATCH_E1_NEW),
        ("E2: recherche -> Sonnet", PATCH_E2_OLD, PATCH_E2_NEW),
        ("E3: Identitaets-Fallback -> Mercury", PATCH_E3_OLD, PATCH_E3_NEW),
        ("E4: Widerspruchs-Check -> Mercury", PATCH_E4_OLD, PATCH_E4_NEW),
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
    print("Patch v1.1 erfolgreich angewendet.")
    print(f"Backup: {backup_path}")
    print("=" * 60)
    print()
    print("Neue Tier-Struktur:")
    print("  Tier 1 (Default): Mercury 2        -> inception/mercury-2")
    print("  Tier 2 (Qualitaet): Claude Sonnet  -> claude-sonnet-4-20250514")
    print("  Tier 3 (Exzellenz): Claude Opus    -> claude-opus-4-6")
    print("  Notfall: Free-Tier                 -> openrouter/free")
    print()
    print("Optional: MERCURY_MODEL und CLAUDE_OPUS_MODEL in .env ueberschreiben.")
    print()
    print("Naechste Schritte:")
    print("  1. docker-compose down")
    print("  2. docker-compose up -d --build")
    print("  3. Verschnyx-Chat starten und /gruebeln 5 testen")


if __name__ == "__main__":
    apply()
