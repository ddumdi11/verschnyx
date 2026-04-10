"""
Over-Night Scheduler fuer Verschnyx
====================================

Schickt eine Sequenz von Kommandos (Gruebeln, Monolog, Identitaet) an den
laufenden verschnyx_bot Container und wartet ordentlich zwischen den
Kommandos.

Wie es funktioniert:
  - Verschnyx laeuft im Container mit stdin_open + tty
  - Der Bot liest Kommandos mit input() aus stdin
  - Wir attachen uns an den Container mit `docker attach` und pipen die
    Kommandos rein -- aber mit genug Zeit zwischen den Zeilen, damit der
    Bot den vorherigen Befehl vollstaendig verarbeiten kann
  - Fuer Gruebel-Befehle warten wir die Gruebel-Dauer + Sicherheitsmarge ab
  - Fuer Monolog/Identitaet warten wir eine feste Zeit

WICHTIG: Bevor dieses Skript startet, muss Verschnyx im Container als
fortlaufender interaktiver Prozess laufen (`docker-compose up -d`).
Das Skript darf NICHT gestartet werden, wenn du gerade selbst mit
Verschnyx chattest -- sonst mischen sich die Eingaben.

Verwendung:
    cd verschnyx_env
    python scheduler/night_run.py [--dry-run]

Der --dry-run Modus zeigt nur, was gesendet WUERDE, ohne wirklich zu senden.
"""
import io
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CONTAINER_NAME = "verschnyx_bot"

# =============================================================================
# Der Nacht-Plan
# =============================================================================
# Jeder Eintrag: (command, argument_or_None, wait_seconds_after)
#   command = "gruebeln" | "monolog" | "identitaet" | "hilfe" | "tagebuch"
#   argument = Minuten fuer gruebeln, sonst None
#   wait_seconds_after = Wie lange wir warten, bevor der naechste Befehl kommt
#
# Faustregel: gruebeln <N> braucht N*60 Sekunden + Puffer fuer die Abschluss-
# Meldung und das Tagebuch-Schreiben. Ich nehme N*60 + 60 Sekunden Puffer.
# Monolog generiert 1-3 Minuten Text -- 180s sollten reichen.
# Identitaet ist nur Anzeige -- 15s reicht.

SCHEDULE = [
    # (command, arg, wait_after_seconds)
    ("gruebeln",    20,   20 * 60 + 60),
    ("monolog",     None, 180),
    ("gruebeln",    45,   45 * 60 + 60),
    ("monolog",     None, 180),
    ("gruebeln",    45,   45 * 60 + 60),
    ("monolog",     None, 180),
    ("monolog",     None, 180),
    ("gruebeln",    15,   15 * 60 + 60),
    ("monolog",     None, 180),
    ("identitaet",  None, 20),
]


def format_command(cmd, arg):
    """Wandelt (command, arg) in einen stdin-Textbefehl um."""
    if arg is not None:
        return f"/{cmd} {arg}"
    return f"/{cmd}"


def estimate_total_duration(schedule) -> int:
    return sum(wait for _, _, wait in schedule)


def send_command_to_container(container: str, command_text: str, dry_run: bool = False) -> bool:
    """
    Schickt eine Zeile Text an den stdin des laufenden Containers.

    Technik: wir nutzen `docker attach` mit einem Pipe. Das ist die sauberste
    Methode, wenn der Container schon interaktiv laeuft. Wir oeffnen einen
    kurzen attach-Prozess, pipen die Zeile, und trennen sofort die
    Verbindung (via --sig-proxy=false und SIGINT).

    ABER: attach kann nicht sauber "nur schreiben" -- es oeffnet auch stdout.
    Daher nutzen wir stattdessen ein einfacheres Workaround: Wir schreiben
    in den Container-stdin via `docker attach` und schliessen den Pipe.
    """
    if dry_run:
        print(f"    [DRY-RUN] wuerde senden: {command_text!r}")
        return True

    try:
        # Attach an den Container, schicke die Zeile, schliesse stdin
        # --detach-keys ist noetig damit Ctrl-P Ctrl-Q nicht interferieren
        proc = subprocess.Popen(
            ["docker", "attach", "--sig-proxy=false", "--detach-keys=ctrl-c", container],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Schicke den Befehl mit newline, dann schliesse stdin
        proc.stdin.write((command_text + "\n").encode("utf-8"))
        proc.stdin.flush()
        # Kurze Wartezeit, damit der Bot den Befehl lesen kann
        time.sleep(0.5)
        proc.stdin.close()
        # attach-Prozess sauber beenden (nicht den Container!)
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        return True
    except Exception as e:
        print(f"    [FEHLER] Konnte Befehl nicht senden: {e}")
        return False


def check_container_running(container: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container}", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10
        )
        return container in result.stdout
    except Exception as e:
        print(f"[FEHLER] docker ps: {e}")
        return False


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 70)
    print("  Verschnyx Over-Night Scheduler")
    print("=" * 70)
    print()

    if dry_run:
        print("  [DRY-RUN MODUS] Es werden KEINE Befehle wirklich gesendet.")
        print()

    # Schaetzen
    total_seconds = estimate_total_duration(SCHEDULE)
    now = datetime.now()
    estimated_end = now + timedelta(seconds=total_seconds)
    print(f"  Start:             {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Geschaetzte Dauer: {total_seconds // 60} Minuten ({total_seconds // 3600}h {(total_seconds % 3600) // 60}m)")
    print(f"  Voraussichtl. Ende: {estimated_end.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print(f"  Plan ({len(SCHEDULE)} Schritte):")
    for i, (cmd, arg, wait) in enumerate(SCHEDULE, 1):
        cmd_str = format_command(cmd, arg)
        print(f"    {i:2d}. {cmd_str:<18s} -> warten: {wait // 60}min {wait % 60:02d}s")
    print()

    # Container-Check
    if not dry_run:
        print("  Pruefe Container-Status...")
        if not check_container_running(CONTAINER_NAME):
            print(f"  [FEHLER] Container '{CONTAINER_NAME}' laeuft nicht!")
            print("  Starte ihn mit: docker-compose up -d")
            sys.exit(1)
        print(f"  [ok] Container '{CONTAINER_NAME}' ist am Laufen")
        print()
        print("  " + "!" * 60)
        print("  ACHTUNG: Stelle sicher, dass du gerade NICHT selbst mit")
        print("  Verschnyx chattest, sonst kollidieren die Eingaben!")
        print("  " + "!" * 60)
        print()
        try:
            input("  Enter druecken, um zu starten (Ctrl-C zum Abbrechen)...")
        except KeyboardInterrupt:
            print("\n  Abgebrochen.")
            sys.exit(0)

    # Ausfuehrung
    print()
    print("=" * 70)
    for i, (cmd, arg, wait) in enumerate(SCHEDULE, 1):
        cmd_str = format_command(cmd, arg)
        t0 = datetime.now().strftime("%H:%M:%S")
        print(f"[{t0}] Schritt {i}/{len(SCHEDULE)}: {cmd_str}")

        success = send_command_to_container(CONTAINER_NAME, cmd_str, dry_run=dry_run)
        if not success and not dry_run:
            print("       Sende-Fehler, ueberspringe Schritt")
            continue

        print(f"       Warte {wait // 60}min {wait % 60:02d}s auf Abschluss...")

        if dry_run:
            # Im dry-run kurz warten, aber nicht die volle Zeit
            time.sleep(0.5)
        else:
            # Aufgeteiltes Warten mit Progress-Anzeige alle 5 Minuten
            start_wait = time.time()
            last_progress = start_wait
            while time.time() - start_wait < wait:
                time.sleep(10)
                now_t = time.time()
                elapsed = now_t - start_wait
                if now_t - last_progress >= 300:  # alle 5 Minuten
                    remaining = wait - elapsed
                    print(f"       ... noch {int(remaining // 60)}min {int(remaining % 60):02d}s")
                    last_progress = now_t

    print()
    print("=" * 70)
    print(f"  Fertig! Alle {len(SCHEDULE)} Schritte abgearbeitet.")
    print(f"  Beendet: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()
    print("  Du kannst jetzt mit 'docker attach verschnyx_bot' wieder in")
    print("  den Chat einsteigen und sehen, was Verschnyx gemacht hat.")


if __name__ == "__main__":
    main()
