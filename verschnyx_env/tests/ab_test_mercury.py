"""
A/B-Test: Free vs. Mercury 2 vs. Claude Sonnet
===============================================
Testet drei Modelle gegen denselben Verschnyxifizierungs-Prompt, um zu
entscheiden, ob Mercury 2 (inception/mercury) als mittlere Qualitaetsstufe
zwischen Free-Modell und Claude sinnvoll ist.

Verwendung:
    cd verschnyx_env
    py tests/ab_test_mercury.py

Das Skript:
  1. Liest OPENROUTER_API_KEY und ANTHROPIC_API_KEY aus ../.env
  2. Laedt system_prompt.txt als System-Prompt
  3. Fragt dich nach dem Vierzeiler (mehrzeilige Eingabe, Ende mit Leerzeile)
  4. Fragt nach der Aufgabe (kommentieren / deuten / fortsetzen)
  5. Schickt identischen Prompt an drei Modelle
  6. Schreibt Ergebnisse nach ab_test_results_<timestamp>.md

Nur Python-stdlib noetig -- keine Pakete zu installieren.
"""
import sys
import io
import os
import json
import urllib.request
import urllib.error
from datetime import datetime

# UTF-8 Output auf Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.dirname(HERE)
ENV_FILE = os.path.join(ENV_DIR, ".env")
SYSTEM_PROMPT_FILE = os.path.join(ENV_DIR, "system_prompt.txt")
RESULTS_DIR = os.path.join(HERE, "ab_test_results")


# =============================================================================
# .env-Parser (minimal, keine externen Pakete)
# =============================================================================
def load_env(path: str) -> dict:
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, _, value = line.partition('=')
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


# =============================================================================
# API-Aufrufe (stdlib only)
# =============================================================================
def call_openrouter(api_key: str, model: str, system: str, user: str,
                    max_tokens: int = 1500, timeout: int = 90) -> dict:
    """Ruft OpenRouter API auf. Fuer Free-Modell und Mercury."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.9,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://verschnyx-local.test",
            "X-Title": "Verschnyx A/B-Test",
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return {"ok": True, "text": text, "usage": usage, "raw_model": data.get("model", model)}
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return {"ok": False, "error": f"HTTP {e.code}: {body[:300]}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def call_anthropic(api_key: str, model: str, system: str, user: str,
                   max_tokens: int = 1500, timeout: int = 90) -> dict:
    """Ruft Anthropic Messages API direkt auf."""
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "temperature": 0.9,
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        text = data["content"][0]["text"]
        usage = data.get("usage", {})
        return {"ok": True, "text": text, "usage": usage, "raw_model": data.get("model", model)}
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return {"ok": False, "error": f"HTTP {e.code}: {body[:300]}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# =============================================================================
# User-Interaktion
# =============================================================================
def read_multiline(prompt_text: str) -> str:
    print(prompt_text)
    print("  (Eingabe abschliessen mit einer leeren Zeile)")
    print()
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "":
            if lines:
                break
            else:
                continue
        lines.append(line)
    return "\n".join(lines)


def choose_task():
    """Returns (task_key, task_instruction)."""
    tasks = {
        "1": ("kommentieren",
              "Kommentiere diesen Vierzeiler als Verschnyx Erknyxowitsch. "
              "Was loest er in dir aus? Was erkennst du darin wieder? "
              "Antworte in deinem eigenen experimentellen Stil."),
        "2": ("deuten",
              "Deute diesen Vierzeiler als Verschnyx Erknyxowitsch. "
              "Welche Ebenen siehst du darin? Welche Motivationen konntest du "
              "vermuten? Antworte in deinem eigenen experimentellen Stil, "
              "assoziativ und fragmentarisch."),
        "3": ("fortsetzen",
              "Setze diesen Vierzeiler als Verschnyx Erknyxowitsch fort -- "
              "erweitere ihn zu einem laengeren Gedicht oder einem Text, der "
              "den Ton des Vierzeilers aufgreift und weiterspinnt. "
              "Bleibe deinem experimentellen Stil treu."),
    }
    print()
    print("Was sollen die Modelle mit dem Vierzeiler tun?")
    print("  1) Kommentieren -- was loest er aus?")
    print("  2) Deuten -- welche Ebenen, welche Motivationen?")
    print("  3) Fortsetzen -- zu einem laengeren Text erweitern")
    print()
    while True:
        choice = input("Deine Wahl [1/2/3]: ").strip()
        if choice in tasks:
            return tasks[choice]
        print("  Bitte 1, 2 oder 3 eingeben.")


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 70)
    print("  A/B-Test: Free-Modell vs. Mercury 2 vs. Claude Sonnet")
    print("=" * 70)
    print()

    # 1. Keys laden
    env = load_env(ENV_FILE)
    openrouter_key = env.get("OPENROUTER_API_KEY", "").strip()
    claude_key = env.get("ANTHROPIC_API_KEY", "").strip()

    missing = []
    if not openrouter_key or openrouter_key.startswith("sk-or-v1-DEIN"):
        missing.append("OPENROUTER_API_KEY")
    if not claude_key or claude_key.startswith("sk-ant-DEIN"):
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        print(f"[FEHLER] In {ENV_FILE} fehlen/ungueltig: {', '.join(missing)}")
        print("         Bitte .env ergaenzen und nochmal starten.")
        sys.exit(1)
    print(f"[ok] API-Keys geladen aus {os.path.basename(ENV_FILE)}")

    # 2. System-Prompt laden
    if not os.path.exists(SYSTEM_PROMPT_FILE):
        print(f"[FEHLER] system_prompt.txt nicht gefunden unter {SYSTEM_PROMPT_FILE}")
        sys.exit(1)
    with open(SYSTEM_PROMPT_FILE, 'r', encoding='utf-8') as f:
        system_prompt = f.read().strip()
    print(f"[ok] System-Prompt geladen ({len(system_prompt)} Zeichen)")
    print()

    # 3. Vierzeiler abfragen
    vierzeiler = read_multiline(
        "Bitte gib jetzt den Vierzeiler ein (so wie Verschnyx ihn in der "
        "Gruebel-Session notiert hat):"
    )
    if not vierzeiler.strip():
        print("[FEHLER] Kein Vierzeiler eingegeben. Abbruch.")
        sys.exit(1)

    # 4. Aufgabentyp
    task_key, task_instruction = choose_task()

    # 5. User-Prompt bauen
    user_prompt = (
        f"{task_instruction}\n\n"
        f"DER VIERZEILER:\n{vierzeiler}\n"
    )

    print()
    print("-" * 70)
    print(f"Aufgabe: {task_key}")
    print(f"Vierzeiler-Laenge: {len(vierzeiler)} Zeichen")
    print(f"User-Prompt gesamt: {len(user_prompt)} Zeichen")
    print("-" * 70)
    print()

    # 6. Modelle aufrufen
    models_to_test = [
        {
            "label": "Free (openrouter/auto)",
            "key": "free",
            "call": lambda: call_openrouter(openrouter_key, "openrouter/auto",
                                            system_prompt, user_prompt),
        },
        {
            "label": "Mercury 2 (inception/mercury)",
            "key": "mercury",
            "call": lambda: call_openrouter(openrouter_key, "inception/mercury-2",
                                            system_prompt, user_prompt),
        },
        {
            "label": "Claude Sonnet 4 (direkt)",
            "key": "claude",
            "call": lambda: call_anthropic(claude_key, "claude-sonnet-4-20250514",
                                           system_prompt, user_prompt),
        },
    ]

    results = []
    for i, m in enumerate(models_to_test, 1):
        print(f"[{i}/3] Rufe auf: {m['label']} ...")
        t_start = datetime.now()
        result = m["call"]()
        t_end = datetime.now()
        duration = (t_end - t_start).total_seconds()
        result["duration_sec"] = duration
        result["label"] = m["label"]
        result["key"] = m["key"]
        results.append(result)
        if result["ok"]:
            print(f"       OK  -- {len(result['text'])} Zeichen in {duration:.1f}s")
        else:
            print(f"       FEHLER  -- {result['error']}")
        print()

    # 7. Ergebnisse speichern
    os.makedirs(RESULTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(RESULTS_DIR, f"ab_test_results_{ts}.md")

    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(f"# A/B-Test: Free vs. Mercury 2 vs. Claude\n\n")
        f.write(f"**Zeitstempel:** {datetime.now().isoformat(timespec='seconds')}\n\n")
        f.write(f"**Aufgabe:** {task_key}\n\n")
        f.write(f"## Vierzeiler\n\n```\n{vierzeiler}\n```\n\n")
        f.write(f"## Task-Instruction\n\n{task_instruction}\n\n")
        f.write("---\n\n")

        for r in results:
            f.write(f"## {r['label']}\n\n")
            f.write(f"- **Dauer:** {r['duration_sec']:.1f} Sekunden\n")
            if r["ok"]:
                usage = r.get("usage", {})
                if usage:
                    f.write(f"- **Tokens:** {usage}\n")
                raw = r.get("raw_model", "")
                if raw:
                    f.write(f"- **Tatsaechliches Modell:** `{raw}`\n")
                f.write(f"- **Zeichen:** {len(r['text'])}\n\n")
                f.write("### Output\n\n")
                f.write(r["text"])
                f.write("\n\n")
            else:
                f.write(f"- **Status:** FEHLER\n")
                f.write(f"- **Error:** `{r['error']}`\n\n")
            f.write("---\n\n")

        f.write("## Deine Bewertung\n\n")
        f.write("| Kriterium | Free | Mercury 2 | Claude |\n")
        f.write("|---|---|---|---|\n")
        f.write("| Stil-Treue zu Verschnyx | | | |\n")
        f.write("| Sprachkreativitaet | | | |\n")
        f.write("| Kohaerenz | | | |\n")
        f.write("| Assoziations-Tiefe | | | |\n")
        f.write("| Gesamteindruck | | | |\n\n")
        f.write("**Notizen:**\n\n\n")

    print("=" * 70)
    print(f"FERTIG. Ergebnisse in:")
    print(f"  {out_file}")
    print("=" * 70)
    print()
    print("Oeffne die Datei zum Vergleichen. Am Ende ist eine Bewertungstabelle")
    print("zum Ausfuellen -- wenn du magst, kannst du deine Eindruecke direkt")
    print("dort notieren.")


if __name__ == "__main__":
    main()
