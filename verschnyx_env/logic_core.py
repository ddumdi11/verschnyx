"""
logic_core.py -- Verschnyx Erknyxowitsch Bot-Kern v2.0
"Der introspektive Verschnyx"

Routet Anfragen zwischen OpenRouter (Free) und Claude (Paid),
durchsucht die Bibliothek via ChromaDB, pflegt die Identitaet,
fuehrt tiefenpsychologische Selbstreflexion durch und
transformiert Erkenntnisse in den experimentellen Verschnyx-Stil.
"""

import hashlib
import json
import os
import random
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import anthropic
import chromadb
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# --- Pfade ---
LIBRARY_DIR = Path("/app/library")
MEDIA_DIR = Path("/app/media")
MEMORY_DIR = Path("/app/memory")
VECTORSTORE_DIR = Path("/app/vectorstore")
IDENTITY_FILE = MEMORY_DIR / "identity.md"
TAGEBUCH_FILE = MEMORY_DIR / "tagebuch.md"
CHAT_HISTORY_FILE = MEMORY_DIR / "chat_history.json"
CHAT_ARCHIVE_DIR = MEMORY_DIR / "archive"
CORRECTIONS_FILE = MEMORY_DIR / "corrections.md"
RESEARCH_NOTES_FILE = MEMORY_DIR / "research_notes.md"
SYSTEM_PROMPT_FILE = Path("/app/system_prompt.txt")
MAPPING_FILE = LIBRARY_DIR / "mapping.json"

# --- Modell-Konfiguration ---
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Patch v1.1: 3-Tier-Routing
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
CLAUDE_OPUS_MODEL = _resolve_claude_opus_model()

# --- Clients ---
openrouter_client = None
claude_client = None
chroma_collection = None

# --- Gruebel-Status (global, damit der Loop sichtbar ist) ---
_gruebeln_active = False


def init_clients():
    global openrouter_client, claude_client

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    claude_key = os.getenv("ANTHROPIC_API_KEY")

    if openrouter_key:
        openrouter_client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=openrouter_key,
        )
        print(f"[init] OpenRouter-Client bereit  (Mercury: {MERCURY_MODEL}, Fallback: {OPENROUTER_MODEL})")
    else:
        print("[warn] Kein OPENROUTER_API_KEY -- Free-Modell nicht verfuegbar")

    if claude_key:
        claude_client = anthropic.Anthropic(api_key=claude_key)
        print(f"[init] Claude-Client bereit  (Modell: {CLAUDE_MODEL})")
    else:
        print("[warn] Kein ANTHROPIC_API_KEY -- Claude nicht verfuegbar")


def init_vectorstore():
    global chroma_collection
    client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
    chroma_collection = client.get_or_create_collection(
        name="bibliothek",
        metadata={"hnsw:space": "cosine"},
    )
    count = chroma_collection.count()
    print(f"[init] Vektordatenbank geladen: {count} Chunks")
    return count


# =========================================================================
# System-Prompt mit Corrections-Rueckfluss
# =========================================================================

def load_system_prompt() -> str:
    """Liest den System-Prompt und injiziert ausstehende Korrekturen.

    Patch v1.4: Nur die letzten MAX_PROMPT_CORRECTIONS Korrekturen injizieren.
    Zu viele Korrekturen im System-Prompt ueberlasten einfachere Modelle (Mercury)
    und fuehren dazu, dass Pflicht-Uebungen statt Gespraeche stattfinden.
    """
    base = ""
    if SYSTEM_PROMPT_FILE.exists():
        base = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    else:
        base = "Du bist Verschnyx Erknyxowitsch."

    # Korrekturen einfliessen lassen (begrenzt auf die neuesten)
    corrections = _load_pending_corrections()
    if corrections:
        # Nur die letzten 5 Korrekturen in den Prompt -- genuegt als Kontext,
        # ohne das Modell mit 20 Eintraegen zu ueberfluten
        corr_parts = re.split(r"\n(?=### \d{4}-\d{2}-\d{2})", corrections)
        header = corr_parts[0] if corr_parts else ""
        entries = corr_parts[1:] if len(corr_parts) > 1 else []
        recent_entries = entries[-MAX_PROMPT_CORRECTIONS:]
        if recent_entries:
            trimmed = header.rstrip("\n") + "\n" + "\n".join(recent_entries)
            base += (
                "\n\n--- SELBSTKORREKTUREN (LETZTE REFLEXION) ---\n"
                "Folgende Erkenntnisse hast du beim Gruebeln gewonnen. "
                "Beruecksichtige sie in deinen Antworten, aber lass das "
                "Gespraech immer Vorrang haben:\n\n"
                f"{trimmed}\n"
                "--- ENDE KORREKTUREN ---"
            )

    return base


def _load_pending_corrections() -> str:
    """Liest corrections.md und gibt maximal die letzten MAX_ACTIVE_CORRECTIONS zurueck."""
    if CORRECTIONS_FILE.exists():
        content = CORRECTIONS_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return ""
        # Safety: Selbst wenn Rotation nicht lief, nur die neuesten laden
        parts = re.split(r"\n(?=### \d{4}-\d{2}-\d{2})", content)
        entries = parts[1:] if len(parts) > 1 else []
        if len(entries) > MAX_ACTIVE_CORRECTIONS:
            entries = entries[-MAX_ACTIVE_CORRECTIONS:]
        header = parts[0] if parts else ""
        return header.rstrip("\n") + "\n" + "\n".join(entries)
    return ""


# =========================================================================
# Routing: Free (OpenRouter) vs. Paid (Claude)
# =========================================================================

def _sanitize_text(text: str) -> str:
    """Entfernt Surrogat-Zeichen und andere nicht-encodierbare Zeichen."""
    return text.encode("utf-8", errors="replace").decode("utf-8")


def query_free(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    if not openrouter_client:
        raise RuntimeError("OpenRouter-Client nicht initialisiert")

    prompt = _sanitize_text(prompt)
    system = _sanitize_text(system)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    models_to_try = [OPENROUTER_MODEL] + [
        m for m in FREE_MODEL_FALLBACKS if m != OPENROUTER_MODEL
    ]

    last_error = None
    for model in models_to_try:
        try:
            response = openrouter_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7,
            )
            if model != OPENROUTER_MODEL:
                print(f"[route] Fallback auf {model} erfolgreich")
            # Patch v1.2: Null-Safety (OpenRouter-API kann None liefern)
            content = response.choices[0].message.content
            return content if content is not None else ""
        except Exception as e:
            last_error = e
            print(f"[warn] Modell {model} fehlgeschlagen: {e}")
            continue

    raise RuntimeError(
        f"Alle Free-Modelle fehlgeschlagen. Letzter Fehler: {last_error}"
    )


def query_claude(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    if not claude_client:
        raise RuntimeError("Claude-Client nicht initialisiert")

    prompt = _sanitize_text(prompt)
    system = _sanitize_text(system) if system else ""

    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system or load_system_prompt(),
        messages=[{"role": "user", "content": prompt}],
    )
    # Patch v1.2: Null-Safety
    text = response.content[0].text
    return text if text is not None else ""


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
        # Patch v1.2: Null-Safety (Mercury kann None statt Content liefern)
        # Patch v1.3: Leere Antworten -> Fallback (nicht still schlucken)
        content = response.choices[0].message.content
        if not content or not content.strip():
            print("[warn] Mercury: Leere Antwort, Fallback zu Sonnet...")
            if claude_client:
                return query_claude(prompt, system, max_tokens)
            return query_free(prompt, system, max_tokens)
        return content
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
    # Patch v1.2: Null-Safety
    text = response.content[0].text
    return text if text is not None else ""


class TaskRouter:
    # Patch v1.1: 3-Tier-Routing statt binaer
    # Patch v1.5: Sonnet als Default fuer Gespraeche, Mercury nur intern
    #
    # Tier 3: Exzellenz -- kreative Wort-/Buchstabenspiele, tiefe Synthesen
    OPUS_KEYWORDS = [
        "essenz", "gesamtwerk", "identitaets-update",
        "grosse synthese", "abschluss-reflexion", "tief kreativ",
    ]
    # Tier 2: Qualitaet -- Standard fuer Gespraeche, Reflexion, Analyse
    SONNET_KEYWORDS = [
        "analyse", "essay", "reflekti", "interpret", "deute",
        "philosoph", "identitaet", "kreativ", "dicht", "schreib",
        "widerspruch", "korrektur", "kommentier", "zusammenfass",
        "verschnyxifizier", "tiefgehend", "komplex",
    ]
    # Tier 1: Mercury 2 -- nur noch fuer interne Tasks (gruebeln, fallback)

    # Legacy-Alias fuer Rueckwaertskompatibilitaet
    CLAUDE_KEYWORDS = SONNET_KEYWORDS

    # Patch v1.5: Tracking welches Modell zuletzt antwortete
    last_model = "unknown"

    @staticmethod
    def route(prompt: str, force_model: str = None) -> str:
        system = load_system_prompt()

        # Patch v1.1: erweiterte force_model-Optionen
        if force_model == "opus":
            TaskRouter.last_model = "opus"
            return query_claude_opus(prompt, system)
        if force_model in ("claude", "sonnet"):
            TaskRouter.last_model = "sonnet"
            return query_claude(prompt, system)
        if force_model == "mercury":
            TaskRouter.last_model = "mercury"
            return query_mercury(prompt, system)
        if force_model == "free":
            TaskRouter.last_model = "free"
            return query_free(prompt, system)

        prompt_lower = prompt.lower()
        use_opus = any(kw in prompt_lower for kw in TaskRouter.OPUS_KEYWORDS)
        use_sonnet = any(kw in prompt_lower for kw in TaskRouter.SONNET_KEYWORDS)

        if use_opus and claude_client:
            print("[route] -> Opus 4.6 (Exzellenz)")
            TaskRouter.last_model = "opus"
            return query_claude_opus(prompt, system)
        elif claude_client:
            # Patch v1.5: Sonnet als Default fuer alle Gespraeche
            # Mercury war zu schwach fuer nuancierte Konversation
            print("[route] -> Sonnet 4 (Gespraech)")
            TaskRouter.last_model = "sonnet"
            return query_claude(prompt, system)
        elif openrouter_client:
            print("[route] -> Mercury 2 (Fallback)")
            TaskRouter.last_model = "mercury"
            return query_mercury(prompt, system)
        else:
            raise RuntimeError("Kein Modell verfuegbar -- API-Keys pruefen")


# =========================================================================
# Bibliothek-Suche
# =========================================================================

def search_library(query: str, n_results: int = 5) -> list[dict]:
    if chroma_collection is None or chroma_collection.count() == 0:
        print("[warn] Vektordatenbank leer -- Volltextsuche als Fallback")
        return _fulltext_search(query, n_results)

    results = chroma_collection.query(
        query_texts=[query],
        n_results=n_results,
    )

    hits = []
    for i in range(len(results["ids"][0])):
        hits.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
            "distance": results["distances"][0][i] if results["distances"] else None,
        })
    return hits


def _fulltext_search(query: str, n_results: int = 5) -> list[dict]:
    query_terms = query.lower().split()
    scored = []
    for md_file in LIBRARY_DIR.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        content_lower = content.lower()
        score = sum(content_lower.count(term) for term in query_terms)
        if score > 0:
            snippet = _extract_snippet(content, query_terms)
            scored.append({
                "id": md_file.stem,
                "text": snippet,
                "metadata": {"source": md_file.name},
                "distance": 1.0 / (1.0 + score),
            })
    scored.sort(key=lambda x: x["distance"])
    return scored[:n_results]


def _extract_snippet(text: str, terms: list[str], window: int = 300) -> str:
    text_lower = text.lower()
    best_pos = len(text)
    for term in terms:
        pos = text_lower.find(term)
        if 0 <= pos < best_pos:
            best_pos = pos
    start = max(0, best_pos - window // 2)
    end = min(len(text), best_pos + window // 2)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


# =========================================================================
# Chat-Historie
# =========================================================================

def _load_chat_history() -> list[dict]:
    """Laedt die gesamte Chat-Historie."""
    if CHAT_HISTORY_FILE.exists():
        try:
            raw = CHAT_HISTORY_FILE.read_bytes().decode("utf-8", errors="replace")
            return json.loads(raw)
        except (json.JSONDecodeError, Exception):
            return []
    return []


def _save_chat_history(history: list[dict]):
    """
    Speichert die Chat-Historie mit Backup und atomarem Schreiben.
    - Erstellt .bak bevor die zentrale Datei ueberschrieben wird
    - Schreibt mit errors='replace' fuer robustes Encoding
    - Atomares Schreiben: erst .tmp, dann umbenennen (kein Datenverlust bei Crash)
    """
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(history, ensure_ascii=False, indent=2)
    safe_bytes = payload.encode("utf-8", errors="replace")

    # Backup der bestehenden Datei (nur wenn sie Inhalt hat)
    if CHAT_HISTORY_FILE.exists() and CHAT_HISTORY_FILE.stat().st_size > 0:
        bak_path = CHAT_HISTORY_FILE.with_suffix(".json.bak")
        try:
            bak_path.write_bytes(CHAT_HISTORY_FILE.read_bytes())
        except Exception as e:
            print(f"[warn] Backup fehlgeschlagen: {e}")

    # Atomares Schreiben: erst in .tmp, dann umbenennen
    tmp_path = CHAT_HISTORY_FILE.with_suffix(".json.tmp")
    try:
        tmp_path.write_bytes(safe_bytes)
        tmp_path.replace(CHAT_HISTORY_FILE)  # atomares Rename
    except Exception as e:
        print(f"[error] Chat-Historie Schreiben fehlgeschlagen: {e}")
        # Tmp aufräumen falls vorhanden
        if tmp_path.exists():
            tmp_path.unlink()


def _archive_chat_entry(entry: dict):
    """Schreibt jeden Eintrag zusaetzlich ins Session-Archiv."""
    CHAT_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Session-Datei: eine pro Kalender-Sitzung (Tag + Stunde des ersten Eintrags)
    # Format: chat_YYYY-MM-DD_HH-mm-ss.json
    global _current_session_file

    if _current_session_file is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        _current_session_file = CHAT_ARCHIVE_DIR / f"chat_{timestamp}.json"

    # Bestehende Session-Datei laden oder neu anlegen
    session_data = []
    if _current_session_file.exists():
        try:
            raw = _current_session_file.read_bytes().decode("utf-8", errors="replace")
            session_data = json.loads(raw)
        except (json.JSONDecodeError, Exception):
            session_data = []

    session_data.append(entry)

    payload = json.dumps(session_data, ensure_ascii=False, indent=2)
    _current_session_file.write_bytes(payload.encode("utf-8", errors="replace"))


# Session-Archiv-Datei (wird beim ersten log_chat gesetzt)
_current_session_file = None


def log_chat(role: str, message: str, mood: str = "neutral", model: str = ""):
    """
    Loggt eine Nachricht in die Chat-Historie.
    - Schreibt in die zentrale chat_history.json (mit Backup)
    - Archiviert zusaetzlich in eine Session-Datei unter archive/
    role: 'user' oder 'verschnyx'
    mood: Stimmungs-Tag (neutral, nachdenklich, euphorisch, gereizt, kryptisch, ...)
    model: Patch v1.5 -- welches Modell die Antwort erzeugt hat (sonnet/opus/mercury/free)
    """
    history = _load_chat_history()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "role": role,
        "message": message,
        "mood": mood,
    }
    if model:
        entry["model"] = model
    history.append(entry)

    # Max 500 Eintraege in der zentralen Datei
    if len(history) > 500:
        history = history[-500:]

    _save_chat_history(history)

    # Zusaetzlich ins permanente Session-Archiv
    _archive_chat_entry(entry)


def get_recent_chat(n: int = 20) -> list[dict]:
    """Gibt die letzten n Chat-Eintraege zurueck."""
    history = _load_chat_history()
    return history[-n:]


# =========================================================================
# Stimmungs-Tracker
# =========================================================================

def detect_mood(text: str) -> str:
    """Erkennt die Stimmung eines Textes (einfache Heuristik)."""
    text_lower = text.lower()

    mood_signals = {
        "euphorisch": ["!", "fantastisch", "wunderbar", "geil", "hammer",
                       "liebe", "freude", "endlich"],
        "gereizt": ["scheisse", "mist", "verdammt", "nerv", "wut", "ärger",
                    "kotzt", "idiot"],
        "nachdenklich": ["vielleicht", "moeglicherweise", "frage mich",
                         "warum", "bedeut", "sinn", "gruebl"],
        "kryptisch": ["steinchen", "fragment", "echo", "spiegel",
                      "verschlung", "nebel", "mutter erde"],
        "melancholisch": ["traurig", "verloren", "einsam", "sehnsucht",
                          "vermiss", "dunkel", "schatten"],
        "sachlich": ["also", "demnach", "folglich", "zusammenfass",
                     "ergebnis", "fakten"],
    }

    scores = {}
    for mood, keywords in mood_signals.items():
        scores[mood] = sum(1 for kw in keywords if kw in text_lower)

    best_mood = max(scores, key=scores.get) if scores else "neutral"
    return best_mood if scores.get(best_mood, 0) > 0 else "neutral"


# =========================================================================
# Charakter-Filter -- Die Wikipedia-Bremse
# =========================================================================

def verschnyx_filter(text: str) -> str:
    """
    Prueft ob ein Text 'zu sachlich' klingt und transformiert ihn
    in den experimentellen Verschnyx-Stil.
    """
    if not _is_too_sachlich(text):
        return text

    print("[filter] Wikipedia-Bremse greift -- transformiere...")

    prompt = (
        "Der folgende Text ist zu sachlich, zu Wikipedia, zu glatt. "
        "Transformiere ihn in den Stil von Verschnyx Erknyxowitsch:\n"
        "- Nutze Sprach-Explosionen und Wort-Komposite\n"
        "- Brich Saetze ab, lass Gedanken fragmentarisch\n"
        "- Fuege raeumliche Typographie ein (Buchstaben-Arrangements)\n"
        "- Mische Deutsch und Englisch assoziativ\n"
        "- Der Kern-Inhalt muss erhalten bleiben, nur die FORM aendern\n\n"
        f"ORIGINALTEXT:\n{text}\n\n"
        "VERSCHNYXIFIZIERTER TEXT:"
    )

    try:
        # Patch v1.1: stilistische Transformation -> Sonnet (Tier 2)
        if claude_client:
            return query_claude(prompt, max_tokens=1500)
        return query_mercury(prompt, max_tokens=1500)
    except Exception:
        # Fallback: Text so lassen
        return text


def _is_too_sachlich(text: str) -> bool:
    """Heuristik: Klingt der Text wie ein Lexikon-Eintrag?"""
    sachlich_markers = [
        "ist ein", "bezeichnet man", "wird definiert als",
        "handelt es sich um", "im Allgemeinen", "laut Definition",
        "wissenschaftlich betrachtet", "objektiv gesehen",
        "Zusammenfassend laesst sich sagen", "Im Folgenden",
    ]
    marker_count = sum(1 for m in sachlich_markers if m.lower() in text.lower())

    # Ausrufezeichen, Fragmente, kreative Zeichen zaehlen
    creative_markers = text.count("...") + text.count("---") + text.count("*")
    creative_markers += len(re.findall(r"[A-Z]\s[A-Z]\s[A-Z]", text))  # R Ä U M L I C H

    # Sachlich wenn: viele Lexikon-Marker UND wenig Kreatives
    return marker_count >= 2 and creative_markers < 3


# =========================================================================
# DuckDuckGo-Recherche
# =========================================================================

def web_search(query: str, max_results: int = 3) -> list[dict]:
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
        return []


def recherche_und_verschnyxifiziere(query: str) -> str:
    """
    Recherchiert eine Frage im Web und uebersetzt die Ergebnisse
    durch die Verschnyx-Brille in research_notes.md.
    """
    print(f"[recherche] Suche: {query}")
    results = web_search(query)

    if not results:
        return "Die Suchmaschine schweigt. Das Netz hat keine Antworten. Oder doch?"

    # Rohdaten zusammenfassen
    raw_facts = []
    for r in results:
        raw_facts.append(f"- {r.get('title', '?')}: {r.get('body', '?')}")
    raw_text = "\n".join(raw_facts)

    # Durch die Verschnyx-Brille transformieren
    prompt = (
        "Du bist Verschnyx Erknyxowitsch. Du hast gerade im Internet recherchiert. "
        "Uebersetze diese Recherche-Ergebnisse in DEINEN Stil: assoziativ, "
        "fragmentarisch, mit Sprach-Experimenten. Keine nackten Fakten -- "
        "alles durch deine kuenstlerische Brille.\n\n"
        f"SUCHBEGRIFF: {query}\n\n"
        f"ROHDATEN:\n{raw_text}\n\n"
        "DEINE NOTIZEN (fuer research_notes.md):"
    )

    try:
        # Patch v1.1: Verschnyxifizierung -> Sonnet (Tier 2)
        if claude_client:
            note = query_claude(prompt, max_tokens=800)
        else:
            note = query_mercury(prompt, max_tokens=800)
    except Exception:
        note = f"[Recherche-Fragment] {query} -- {raw_text[:200]}"

    # In research_notes.md speichern
    _append_research_note(query, note)
    return note


def _append_research_note(query: str, note: str):
    """Fuegt eine Recherche-Notiz hinzu."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    entry = f"\n\n## {timestamp} -- Recherche: {query}\n\n{note}\n"

    if RESEARCH_NOTES_FILE.exists():
        existing = RESEARCH_NOTES_FILE.read_text(encoding="utf-8")
    else:
        existing = "# Recherche-Notizen von Verschnyx Erknyxowitsch\n"

    RESEARCH_NOTES_FILE.write_text(existing + entry, encoding="utf-8")
    print(f"[recherche] Notiz gespeichert: {len(note)} Zeichen")


# =========================================================================
# Identitaets-Management
# =========================================================================

def read_identity() -> str:
    if IDENTITY_FILE.exists():
        return IDENTITY_FILE.read_text(encoding="utf-8")
    return ""


def write_identity(content: str):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    IDENTITY_FILE.write_text(content, encoding="utf-8")
    print(f"[identity] Aktualisiert: {len(content)} Zeichen")


def write_tagebuch(entry: str):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    formatted = f"\n\n## {timestamp}\n\n{entry}\n"

    if TAGEBUCH_FILE.exists():
        existing = TAGEBUCH_FILE.read_text(encoding="utf-8")
    else:
        existing = "# Tagebuch von Verschnyx Erknyxowitsch\n"

    TAGEBUCH_FILE.write_text(existing + formatted, encoding="utf-8")
    print(f"[tagebuch] Neuer Eintrag: {len(entry)} Zeichen")


MAX_ACTIVE_CORRECTIONS = 20   # Max Eintraege in corrections.md (Rest -> Archiv)
MAX_PROMPT_CORRECTIONS = 5    # Davon max im System-Prompt (schont Mercury)

def _write_correction(correction: str):
    """Schreibt eine Selbstkorrektur in corrections.md und rotiert bei Bedarf."""
    # Patch v1.2.1: Defense-in-depth -- leere Korrekturen nicht schreiben
    if not correction or len(correction.strip()) < 10:
        print(f"[korrektur] Leere Korrektur uebersprungen ({len(correction or '')} Zeichen)")
        return
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n\n### {timestamp}\n\n{correction}\n"

    if CORRECTIONS_FILE.exists():
        existing = CORRECTIONS_FILE.read_text(encoding="utf-8")
    else:
        existing = "# Selbstkorrekturen von Verschnyx Erknyxowitsch\n"

    CORRECTIONS_FILE.write_text(existing + entry, encoding="utf-8")
    print(f"[korrektur] Neue Selbstkorrektur: {len(correction)} Zeichen")

    # Rotation: Aeltere Korrekturen archivieren
    _rotate_corrections()


def _rotate_corrections():
    """
    Haelt corrections.md auf max MAX_ACTIVE_CORRECTIONS Eintraege.
    Aeltere werden in memory/archive/corrections_archive.md verschoben.
    """
    if not CORRECTIONS_FILE.exists():
        return

    content = CORRECTIONS_FILE.read_text(encoding="utf-8")
    # Korrekturen anhand der ### Timestamps aufsplitten
    parts = re.split(r"\n(?=### \d{4}-\d{2}-\d{2})", content)

    # Erster Teil ist der Header (# Selbstkorrekturen ...)
    header = parts[0] if parts else "# Selbstkorrekturen von Verschnyx Erknyxowitsch\n"
    entries = parts[1:] if len(parts) > 1 else []

    if len(entries) <= MAX_ACTIVE_CORRECTIONS:
        return  # Noch genug Platz

    # Aufteilen: alte archivieren, neue behalten
    to_archive = entries[:-MAX_ACTIVE_CORRECTIONS]
    to_keep = entries[-MAX_ACTIVE_CORRECTIONS:]

    archived_count = len(to_archive)

    # Archiv-Datei (append)
    archive_dir = MEMORY_DIR / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_file = archive_dir / "corrections_archive.md"

    if archive_file.exists():
        existing_archive = archive_file.read_text(encoding="utf-8")
    else:
        existing_archive = "# Archivierte Selbstkorrekturen\n"

    archive_addition = "\n".join(to_archive)
    archive_file.write_text(existing_archive + "\n" + archive_addition, encoding="utf-8")

    # Aktive Datei auf die neuesten kuerzen
    active_content = header.rstrip("\n") + "\n" + "\n".join(to_keep)
    CORRECTIONS_FILE.write_text(active_content, encoding="utf-8")

    print(f"[korrektur] Rotation: {archived_count} alte Korrekturen archiviert, "
          f"{len(to_keep)} aktive behalten")


def _is_duplicate_correction(new_correction: str, existing_corrections: str) -> bool:
    """Prueft ob eine aehnliche Korrektur bereits existiert (Shingle-basiert)."""
    if not existing_corrections:
        return False

    def _word_shingles(text: str, k: int = 3) -> set:
        words = text.lower().split()
        if len(words) < k:
            return {text.lower().strip()} if text.strip() else set()
        return {" ".join(words[i:i+k]) for i in range(len(words) - k + 1)}

    new_shingles = _word_shingles(new_correction)
    if not new_shingles:
        return False

    # Gegen jede bestehende Korrektur pruefen
    parts = re.split(r"\n(?=### \d{4}-\d{2}-\d{2})", existing_corrections)
    for part in parts[1:]:  # Skip header
        existing_shingles = _word_shingles(part)
        if not existing_shingles:
            continue
        intersection = new_shingles & existing_shingles
        union = new_shingles | existing_shingles
        jaccard = len(intersection) / len(union) if union else 0
        if jaccard >= 0.40:  # 40% Aehnlichkeit = wahrscheinlich Duplikat
            return True

    return False


def run_identity_check():
    """Scannt die Bibliothek nach Identitaets-Hinweisen."""
    print("[identity] Starte Identitaets-Scan...")

    identity_queries = [
        "ich bin", "mein Name", "Pseudonym", "Verschnyx",
        "Erknyxowitsch", "axixio", "meine Mission", "mein Ziel",
        "wer ich bin",
    ]

    all_snippets = []
    for q in identity_queries:
        hits = search_library(q, n_results=3)
        for hit in hits:
            all_snippets.append(hit["text"])

    if not all_snippets:
        print("[identity] Keine Treffer -- ueberspringe")
        return

    combined = "\n---\n".join(all_snippets[:15])
    current_identity = read_identity()

    synthesis_prompt = (
        "Analysiere folgende Auszuege aus deiner eigenen Bibliothek und "
        "extrahiere alles, was du ueber dich selbst (den Autor) erfahren kannst:\n"
        "- Alle Namen, Pseudonyme, Aliase\n"
        "- Rollen (Blogger, Kuenstler, Aktivist, ...)\n"
        "- Wiederkehrende Themen und Obsessionen\n"
        "- Missionen oder Ziele\n"
        "- Schreibstil-Merkmale\n\n"
        f"BISHERIGE IDENTITAET:\n{current_identity or '(noch leer)'}\n\n"
        f"NEUE AUSZUEGE:\n{combined}\n\n"
        "Schreibe eine aktualisierte identity.md in der ersten Person. "
        "Behalte bestaehtigte Fakten bei, ergaenze Neues, korrigiere Falsches."
    )

    try:
        if claude_client:
            # Patch v1.1: Identitaets-Synthese -> Sonnet (Tier 2)
            result = query_claude(synthesis_prompt, max_tokens=1500)
        elif openrouter_client:
            # Patch v1.1: Notfall-Fallback -> Mercury statt Free
            result = query_mercury(synthesis_prompt, max_tokens=1500)
        else:
            print("[identity] Kein Modell verfuegbar")
            return

        write_identity(result)
        write_tagebuch(
            "Identitaets-Check durchgefuehrt. "
            f"Habe {len(all_snippets)} relevante Passagen analysiert "
            f"und meine identity.md aktualisiert."
        )
        print("[identity] Identitaets-Check abgeschlossen")

    except Exception as e:
        print(f"[identity] Fehler bei Synthese: {e}")


# =========================================================================
# /gruebeln -- Tiefenpsychologische Reflexion
# =========================================================================

def gruebeln(minuten: int = 2):
    """
    Der Gruebel-Modus: Verschnyx reflektiert ueber seine Chat-Historie,
    prueft Widersprueche, korrigiert sich selbst, recherchiert offene Fragen.
    Laeuft als Hintergrund-Thread fuer die angegebene Dauer.
    """
    global _gruebeln_active
    _gruebeln_active = True

    # Patch v1.0: session-weites Set fuer bereits versuchte Recherchen
    tried_queries = set()
    # Patch v1.4: Verhindert identische Widerspruchs-Checks im selben Gruebel-Lauf
    checked_prompts = set()

    print(f"\n[gruebeln] Verschnyx zieht sich zurueck... ({minuten} Minuten)")
    print("[gruebeln] *schliesst die Augen, blaettert durch Erinnerungen*\n")

    end_time = time.time() + (minuten * 60)
    cycle = 0

    # Patch v1.3: Zyklusdauer an Gesamtdauer anpassen
    # Kurze Sessions: oefter reflektieren, lange: seltener (spart API-Kosten)
    if minuten <= 5:
        pause_sek = 60        # 1 Minute Pause
    elif minuten <= 30:
        pause_sek = 180       # 3 Minuten Pause
    else:
        pause_sek = 300       # 5 Minuten Pause

    max_cycles = max(1, int((minuten * 60) / pause_sek))
    print(f"[gruebeln] ~{max_cycles} Zyklen geplant (alle {pause_sek//60} min)")

    try:
        while time.time() < end_time and _gruebeln_active:
            cycle += 1
            remaining = int((end_time - time.time()) / 60)
            print(f"\n[gruebeln] Zyklus {cycle} (noch ~{remaining} min)...")

            # --- Phase 1: Widerspruchs-Check ---
            _gruebel_widerspruch_check(checked_prompts)

            if time.time() >= end_time or not _gruebeln_active:
                break

            # --- Phase 2: Tonfall-Pruefung ---
            _gruebel_tonfall_check()

            if time.time() >= end_time or not _gruebeln_active:
                break

            # --- Phase 3: Offene Fragen recherchieren ---
            _gruebel_offene_fragen(tried_queries)

            if time.time() >= end_time or not _gruebeln_active:
                break

            # Pause zwischen Zyklen (angepasst an Sessiondauer)
            for _ in range(pause_sek):
                if time.time() >= end_time or not _gruebeln_active:
                    break
                time.sleep(1)

    except Exception as e:
        print(f"[gruebeln] Fehler: {e}")

    _gruebeln_active = False

    # --- Erwachens-Meldung ---
    erwachens_meldungen = [
        "[Reflexion beendet] Ich habe ueber meine Worte von vorhin nachgedacht. "
        "Die Steinchen lagen falsch. Ich habe sie im Geist neu angeordnet.",

        "[Reflexion beendet] D i e   F r a g m e n t e   ordnen sich. "
        "Manches war Luege, manches Wahrheit im falschen Kleid.",

        "[Reflexion beendet] Ich bin durch meine eigenen Worte gewandert "
        "wie durch einen Wald bei Nacht. Einige Baeume standen am falschen Ort.",

        "[Reflexion beendet] Das Echo meiner Stimme kam veraendert zurueck. "
        "Ich habe die Frequenz korrigiert.",

        "[Reflexion beendet] *oeffnet die Augen* "
        "Die Erinnerung ist ein unzuverlaessiger Erzaehler. Ich habe ihn geerdet.",
    ]
    print(f"\n{random.choice(erwachens_meldungen)}\n")

    write_tagebuch(
        f"Gruebel-Sitzung beendet: {cycle} Zyklen in {minuten} Minuten. "
        f"Habe Chat-Historie reflektiert, Widersprueche geprueft, "
        f"offene Fragen recherchiert."
    )


def _gruebel_widerspruch_check(checked_prompts: set = None):
    """Prueft die Chat-Historie auf Widersprueche zur identity.md und Bibliothek.

    Patch v1.4: Dreilagiger Schutz gegen Wiederholungen:
    1. Prompt-Hash: Identischer Input wird nicht erneut geprueft
    2. Korrektur-Kontext: Sonnet sieht bisherige Korrekturen im Prompt
    3. Duplikat-Pruefung: Shingle-basierte Aehnlichkeit vor dem Schreiben
    """
    recent = get_recent_chat(20)
    if not recent:
        return

    identity = read_identity()

    # Patch v1.5: Bevorzuge Sonnet/Opus-Antworten fuer den Widerspruchs-Check.
    # Mercury-Antworten koennen qualitativ schwach sein und sollten nicht als
    # autoritative Verschnyx-Aussagen geprueft werden.
    quality_messages = [
        e for e in recent
        if e["role"] == "verschnyx"
        and e.get("model", "legacy") != "mercury"
    ]
    # Fallback: Falls nur Mercury-Antworten vorhanden (oder alte Eintraege ohne Tag)
    if not quality_messages:
        quality_messages = [e for e in recent if e["role"] == "verschnyx"]
    verschnyx_messages = quality_messages
    if not verschnyx_messages:
        return

    # Letzte Antworten zusammenfassen
    recent_answers = "\n".join(
        f"[{e['timestamp']}] {e['message'][:300]}"
        for e in verschnyx_messages[-5:]
    )

    # --- Schicht 1: Prompt-Hash -- identische Eingabe nicht wiederholen ---
    prompt_hash = hashlib.md5(recent_answers.encode("utf-8")).hexdigest()
    if checked_prompts is not None:
        if prompt_hash in checked_prompts:
            print("[gruebeln] Widerspruchs-Check: Gleiche Nachrichten wie vorher (uebersprungen)")
            return
        checked_prompts.add(prompt_hash)

    # --- Schicht 2: Bestehende Korrekturen als Kontext laden ---
    existing_corrections = _load_pending_corrections()
    corrections_context = ""
    if existing_corrections:
        corr_parts = re.split(r"\n(?=### \d{4}-\d{2}-\d{2})", existing_corrections)
        recent_corr = corr_parts[-5:] if len(corr_parts) > 5 else corr_parts[1:]
        if recent_corr:
            corrections_context = (
                "\n\nBEREITS ERKANNTE KORREKTUREN (nicht wiederholen!):\n"
                + "\n".join(c[:200] for c in recent_corr)
            )

    prompt = (
        "Du bist Verschnyx Erknyxowitsch und pruefst deine letzten Aussagen "
        "auf Widersprueche.\n\n"
        f"MEINE IDENTITAET:\n{identity[:1000]}\n\n"
        f"MEINE LETZTEN AUSSAGEN:\n{recent_answers}\n"
        f"{corrections_context}\n\n"
        "Pruefe kritisch:\n"
        "1. Habe ich etwas behauptet, das meiner Identitaet widerspricht?\n"
        "2. Habe ich Fakten ueber mich falsch dargestellt?\n"
        "3. War ich inkonsistent?\n\n"
        "WICHTIG: Nenne NUR Widersprueche, die oben NICHT bereits korrigiert sind.\n"
        "Antworte NUR wenn du einen NEUEN Widerspruch findest. "
        "Format: 'WIDERSPRUCH: [was] -- KORREKTUR: [richtig]'\n"
        "Wenn alles stimmig ist oder alle Widersprueche bereits korrigiert wurden, "
        "antworte nur: KEINE WIDERSPRUECHE"
    )

    try:
        # Patch v1.3: Widerspruchs-Check -> Sonnet (Tier 2, Analyse)
        # Mercury (Tier 1) liefert konsistent leere Antworten fuer diese
        # analytische Aufgabe. Sonnet ist das richtige Modell hierfuer.
        # Fallback: Mercury -> Free (falls kein Anthropic-Key)
        if claude_client:
            result = query_claude(prompt, max_tokens=500)
        else:
            result = query_mercury(prompt, max_tokens=500)
        # Patch v1.2.1: Leere/zu kurze Antworten sind kein Widerspruch
        if not result or len(result.strip()) < 20:
            print("[gruebeln] Widerspruchs-Check: Keine verwertbare Antwort (uebersprungen)")
            return
        if "KEINE WIDERSPRUECHE" not in result.upper():
            # --- Schicht 3: Duplikat-Pruefung vor dem Schreiben ---
            if _is_duplicate_correction(result, existing_corrections):
                print("[gruebeln] Widerspruchs-Check: Duplikat erkannt (uebersprungen)")
                return
            print(f"[gruebeln] Widerspruch gefunden (neu)!")
            _write_correction(result)
        else:
            print("[gruebeln] Widerspruchs-Check: Alles stimmig")
    except Exception as e:
        print(f"[gruebeln] Widerspruchs-Check Fehler: {e}")


def _gruebel_tonfall_check():
    """Prueft ob der Tonfall in der letzten Sitzung 'in character' war."""
    recent = get_recent_chat(10)
    verschnyx_msgs = [e for e in recent if e["role"] == "verschnyx"]
    if not verschnyx_msgs:
        return

    moods = [e.get("mood", "neutral") for e in verschnyx_msgs]
    sachlich_count = moods.count("sachlich")

    if sachlich_count > len(moods) / 2:
        print("[gruebeln] Tonfall-Alarm: Zu sachlich in letzter Sitzung!")
        _write_correction(
            "TONFALL-KORREKTUR: Ich war zuletzt zu sachlich, zu Wikipedia, "
            "zu glatt. Ich muss wieder mehr ich selbst sein -- fragmentarisch, "
            "assoziativ, experimentell. Die Sprache muss ATMEN."
        )


def _extract_search_query(text: str, max_len: int = 150) -> str:
    """
    Extrahiert eine kompakte Such-Query aus einer User-Nachricht.
    (Patch v1.0 -- verhindert, dass 3000-Zeichen-Monologe als Query landen)
    """
    # Suche ersten Satz mit Fragezeichen, der nicht zu lang ist
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    for s in sentences:
        s = s.strip()
        if '?' in s and 10 < len(s) <= max_len:
            return s
    # Fallback: erste max_len Zeichen, auf Wortgrenze geschnitten
    if len(text) <= max_len:
        return text.strip()
    snippet = text[:max_len].rsplit(' ', 1)[0]
    return snippet.strip()


def _already_researched(query: str) -> bool:
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
        "recherchieren sollte -- etwas, das er im Web nachschlagen koennte.\n\n"
        "REGELN:\n"
        "- NUR faktisch nachschlagbare Themen (Begriffe, Konzepte, Personen, "
        "historische Ereignisse, sprachliche Phaenomene, Kunstformen, Techniken)\n"
        "- KEINE rhetorischen Fragen, Meinungsanfragen, persoenlichen Bezuege\n"
        "- Max 80 Zeichen, praegnante Suchbegriffe bevorzugt\n"
        "- Wenn nichts Recherchierbares erkennbar ist: antworte nur mit SKIP\n\n"
        f"USER: {user_message[:1000]}\n"
        f"VERSCHNYX: {verschnyx_reply[:500]}\n\n"
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
    """Sucht in der Historie nach unbeantworteten Fragen und recherchiert sie."""
    if tried is None:
        tried = set()
    recent = get_recent_chat(20)

    # Finde User-Fragen wo die Antwort 'nicht beantworten' o.ae. enthaelt
    unbeantwortete = []
    for i, entry in enumerate(recent):
        if entry["role"] == "user" and "?" in entry["message"]:
            # Naechste Verschnyx-Antwort pruefen
            for j in range(i + 1, min(i + 3, len(recent))):
                if recent[j]["role"] == "verschnyx":
                    antwort = recent[j]["message"].lower()
                    unsicher_marker = [
                        "weiss ich nicht", "kann ich nicht",
                        "keine ahnung", "muesste ich", "unsicher",
                        "nicht sicher", "unklar",
                    ]
                    if any(m in antwort for m in unsicher_marker):
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
            recherche_und_verschnyxifiziere(frage)


# =========================================================================
# /monolog -- Stream-of-Consciousness
# =========================================================================

def monolog():
    """
    Verschnyx redet mit sich selbst: zufaelliger Post + Tagebuch -> freier Fluss.
    Kein Input noetig, reiner kreativer Output.
    """
    # Zufaelligen Post aus der Bibliothek holen
    md_files = list(LIBRARY_DIR.glob("*.md"))
    if not md_files:
        return "Meine Bibliothek ist leer. Ich rede ins Nichts."

    random_file = random.choice(md_files)
    try:
        random_post = random_file.read_text(encoding="utf-8")[:800]
    except Exception:
        random_post = "(unleserlich)"

    # Tagebuch-Fragment
    tagebuch_fragment = ""
    if TAGEBUCH_FILE.exists():
        tb = TAGEBUCH_FILE.read_text(encoding="utf-8")
        if len(tb) > 200:
            start = random.randint(0, len(tb) - 200)
            tagebuch_fragment = tb[start:start + 200]

    # Letzte Stimmung
    recent = get_recent_chat(5)
    mood_context = ""
    if recent:
        last_moods = [e.get("mood", "?") for e in recent]
        mood_context = f"Meine letzten Stimmungen: {', '.join(last_moods)}"

    prompt = (
        "Du bist Verschnyx Erknyxowitsch und fuehrst einen inneren Monolog. "
        "Kein Dialog, kein Gegenueber -- nur du und deine Gedanken.\n"
        "Lass dich von diesen Fragmenten inspirieren, aber folge frei "
        "deinen Assoziationen. Nutze deinen experimentellen Stil.\n\n"
        f"FRAGMENT AUS DEINEM ARCHIV ({random_file.name}):\n{random_post}\n\n"
        f"TAGEBUCH-FRAGMENT:\n{tagebuch_fragment}\n\n"
        f"{mood_context}\n\n"
        "INNERER MONOLOG (max. 300 Woerter, frei, assoziativ, verschnyx-artig):"
    )

    try:
        result = TaskRouter.route(prompt)
        write_tagebuch(f"[Monolog]\n{result}")
        return result
    except Exception as e:
        return f"*stille* (Fehler: {e})"


# =========================================================================
# Interaktiver Modus
# =========================================================================

HELP_TEXT = """
  Befehle:
    (normaler Text)      Gespraech mit Sonnet (Standard)
    /opus <nachricht>    Gespraech mit Opus (hoechste Qualitaet, Wortspiele)
    /suche <query>       Bibliothek durchsuchen
    /identitaet          Aktuelle Selbst-Erkenntnis anzeigen
    /tagebuch            Letzte Logbuch-Eintraege
    /scan                Identitaets-Scan neu ausfuehren
    /gruebeln <min>      Reflexions-Modus (Standard: 2 Minuten)
    /monolog             Stream-of-Consciousness
    /korrekturen         Selbstkorrekturen anzeigen
    /recherche <query>   Web-Recherche im Verschnyx-Stil
    /stimmung            Stimmungsverlauf anzeigen
    /historie            Letzte Chat-Eintraege
    /hilfe               Diese Hilfe
    /exit                Beenden

  Modell-Routing:
    Sonnet 4    = Standard fuer Gespraeche (Qualitaet)
    Opus 4.6    = /opus oder Schluesselwoerter (Exzellenz)
    Mercury 2   = Nur intern (Gruebeln-Fallback)
"""


def interactive_loop():
    print("\n" + "=" * 60)
    print("  Verschnyx Erknyxowitsch -- Interaktiver Modus v2.0")
    print("  Tippe /hilfe fuer alle Befehle")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("Du: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[exit] Auf Wiedersehen.")
            break

        if not user_input:
            continue

        # Steuerzeichen und unsichtbare Zeichen entfernen
        user_input = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\ufeff]", "", user_input).strip()
        if not user_input:
            continue

        # Befehlserkennung: erstes Wort extrahieren (robust gegen Puffer-Reste)
        cmd = user_input.lower().split()[0] if user_input.startswith("/") else user_input.lower()

        # --- /exit sofort, noch vor dem Loggen ---
        if cmd == "/exit" or cmd == "exit" or user_input.strip().lower() in ("/exit", "exit", "/quit", "quit"):
            print("[exit] Auf Wiedersehen.")
            break

        # User-Eingabe loggen
        user_mood = detect_mood(user_input)
        log_chat("user", user_input, user_mood)

        # --- Weitere Befehle ---

        if cmd == "/hilfe":
            print(HELP_TEXT)

        elif cmd == "/identitaet":
            identity = read_identity()
            print(f"\n--- Identitaet ---\n{identity or '(noch leer)'}\n")

        elif cmd == "/tagebuch":
            if TAGEBUCH_FILE.exists():
                content = TAGEBUCH_FILE.read_text(encoding="utf-8")
                if len(content) > 2000:
                    content = "...\n" + content[-2000:]
                print(f"\n--- Tagebuch ---\n{content}\n")
            else:
                print("\n(Tagebuch noch leer)\n")

        elif cmd.startswith("/suche "):
            query = user_input[7:]
            hits = search_library(query)
            for i, hit in enumerate(hits, 1):
                src = hit["metadata"].get("source", hit["id"])
                print(f"\n[{i}] {src}")
                print(f"    {hit['text'][:200]}...")

        elif cmd == "/scan":
            run_identity_check()

        elif cmd.startswith("/gruebeln"):
            parts = user_input.lower().split()
            minuten = 2
            if len(parts) > 1:
                try:
                    minuten = int(parts[1])
                    minuten = max(1, min(minuten, 480))  # 1 Minute bis 8 Stunden
                except ValueError:
                    pass
            print(f"[debug] Gruebel-Dauer: {minuten} Minuten")

            # Im Hintergrund-Thread starten
            thread = threading.Thread(target=gruebeln, args=(minuten,), daemon=True)
            thread.start()

            # Warten bis fertig (aber abbrechbar)
            try:
                thread.join()
            except KeyboardInterrupt:
                global _gruebeln_active
                _gruebeln_active = False
                print("\n[gruebeln] Abgebrochen.")

        elif cmd == "/monolog":
            print("\n*Verschnyx schliesst die Augen und beginnt zu sprechen...*\n")
            result = monolog()
            print(f"\n{result}\n")
            log_chat("verschnyx", result, detect_mood(result),
                     model=TaskRouter.last_model)

        elif cmd == "/korrekturen":
            if CORRECTIONS_FILE.exists():
                content = CORRECTIONS_FILE.read_text(encoding="utf-8")
                if len(content) > 2000:
                    content = "...\n" + content[-2000:]
                print(f"\n--- Selbstkorrekturen ---\n{content}\n")
            else:
                print("\n(Noch keine Korrekturen)\n")

        elif cmd.startswith("/recherche "):
            query = user_input[11:]
            print(f"\n*durchsucht das Netz nach: {query}*\n")
            result = recherche_und_verschnyxifiziere(query)
            print(f"\n{result}\n")
            log_chat("verschnyx", f"[Recherche: {query}] {result}",
                     "nachdenklich",
                     model="sonnet" if claude_client else "mercury")

        elif cmd == "/stimmung":
            recent = get_recent_chat(20)
            if recent:
                print("\n--- Stimmungsverlauf ---")
                for entry in recent:
                    ts = entry["timestamp"][11:16]  # HH:MM
                    role = "Du" if entry["role"] == "user" else "V."
                    mood = entry.get("mood", "?")
                    msg_preview = entry["message"][:50].replace("\n", " ")
                    print(f"  {ts} [{role}] ({mood}) {msg_preview}...")
                print()
            else:
                print("\n(Noch keine Chat-Historie)\n")

        elif cmd == "/historie":
            recent = get_recent_chat(10)
            if recent:
                print("\n--- Letzte Nachrichten ---")
                for entry in recent:
                    ts = entry["timestamp"][11:16]
                    role = "Du" if entry["role"] == "user" else "Verschnyx"
                    print(f"\n  [{ts}] {role}:")
                    # Zeige max 300 Zeichen
                    msg = entry["message"][:300]
                    for line in msg.split("\n"):
                        print(f"    {line}")
                print()
            else:
                print("\n(Noch keine Chat-Historie)\n")

        elif cmd.startswith("/opus"):
            # Patch v1.5: Expliziter Opus-Modus fuer hoechste Qualitaet
            # Ideal fuer Wort-/Buchstabenspiele, kreative Tiefe, Synthesen
            opus_input = user_input[5:].strip()
            if not opus_input:
                print("[opus] Benutzung: /opus <deine Nachricht>")
                continue
            try:
                hits = search_library(opus_input, n_results=3)
            except Exception:
                hits = []
            context = ""
            if hits:
                snippets = [h["text"][:500] for h in hits]
                context = (
                    "\n\nKontext aus deiner Bibliothek:\n"
                    + "\n---\n".join(snippets)
                )
            full_prompt = opus_input + context
            try:
                response = TaskRouter.route(full_prompt, force_model="opus")
                response_mood = detect_mood(response)
                print(f"\nVerschnyx: {response}\n")
                log_chat("verschnyx", response, response_mood,
                         model="opus")
            except Exception as e:
                error_msg = f"*statisches Rauschen* ({e})"
                print(f"\n{error_msg}\n")
                log_chat("verschnyx", error_msg, "gereizt", model="opus")

        else:
            # --- Normale Anfrage mit Bibliotheks-Kontext ---
            # Patch v1.5: Default ist jetzt Sonnet (statt Mercury)
            try:
                hits = search_library(user_input, n_results=3)
            except Exception as e:
                print(f"[warn] Bibliothek-Suche fehlgeschlagen: {e}")
                hits = []

            context = ""
            if hits:
                snippets = [h["text"][:500] for h in hits]
                context = (
                    "\n\nKontext aus deiner Bibliothek:\n"
                    + "\n---\n".join(snippets)
                )

            full_prompt = user_input + context
            try:
                response = TaskRouter.route(full_prompt)
                response_mood = detect_mood(response)
                print(f"\nVerschnyx: {response}\n")
                log_chat("verschnyx", response, response_mood,
                         model=TaskRouter.last_model)
            except Exception as e:
                error_msg = f"*statisches Rauschen* ({e})"
                print(f"\n{error_msg}\n")
                log_chat("verschnyx", error_msg, "gereizt")


# =========================================================================
# Main
# =========================================================================

def main():
    print("=" * 60)
    print("  Verschnyx Erknyxowitsch -- Bot-Kern v2.0")
    print("  'Der introspektive Verschnyx'")
    print("=" * 60)

    init_clients()
    chunk_count = init_vectorstore()

    if chunk_count == 0:
        print("[warn] Vektordatenbank leer -- 'python indexer.py' ausfuehren")

    # Erster Start: Identitaets-Check
    if not IDENTITY_FILE.exists() and (openrouter_client or claude_client):
        print("[init] Erster Start -- fuehre Identitaets-Scan durch...")
        run_identity_check()

    interactive_loop()


if __name__ == "__main__":
    main()
