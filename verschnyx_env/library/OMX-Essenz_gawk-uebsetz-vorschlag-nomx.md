---
title: "gawk-uebsetz-vorschlag\noomx"
author: "zarko maroli"
source: ebook
---

# gawk-uebsetz-vorschlag\noomx

``` # gawk -help
Aufruf: gawk [POSIX- oder GNU-Optionen] -f PROGRAMM [--] Datei ...
Aufruf: gawk [POSIX- oder GNU-Optionen] -- 'PROGRAMM' Datei ...
POSIX-Optionen          GNU-Optionen (lang):
        -f PROGRAMM             --file=PROGRAMM
        -F Feldtrenner                  --field-separator=Feldtrenner
        -v var=Wert             --assign=var=Wert
        -m[fr] Wert
        -O                      --optimize
        -W compat               --compat
        -W copyleft             --copyleft
        -W copyright            --copyright
        -W dump-variables[=Datei]       --dump-variables[=Datei]
        -W exec=file            --exec=file
        -W gen-po               --gen-po
        -W help                 --help
        -W lint[=fatal]         --lint[=fatal]
        -W lint-old             --lint-old
        -W non-decimal-data     --non-decimal-data
        -W profile[=Datei]      --profile[=Datei]
        -W posix                --posix
        -W re-interval          --re-interval
        -W source=Programmtext  --source=Programmtext
        -W traditional          --traditional
        -W usage                --usage
        -W use-lc-numeric       --use-lc-numeric
        -W version              --version

Zum Berichten von Fehlern sehen Sie bitte den Punkt »Bugs«
in »gawk.info«, den Sie als Kapitel »Reporting Problems and Bugs«
in der gedruckten Version finden.

Fehler in der Übersetzuung senden Sie bitte als E-Mail an
an translation-team-de@lists.sourceforge.net

gawk ist eine Sprache zur Suche nach und dem Verarbeiten von Mustern.
Normalerweise ließt das Programm von der Standardeingabe und gibt
auf der Standardausgabe aus.

Beispiele:
        gawk '{ sum += $1 }; END { print sum }' file
        gawk -F: '{ print $1 }' /etc/passwd

[Aus/Von: Die Help-Ausgabe von Gawk - einem sehr interessanten, 
 guten wie einfachen Programm für die Anwendung in der Shell & mehr.]
 
 Damit's auch für Deutsche verwend- & nutzbar* wird, meine Vorschläge
 für bessere Formulierung in Deutsch, hier:
 
 Evtl. anfallende Fehlerberichterstattung läßt sich dem Punkt »Bugs«
 in »gawk.info« entnehmen, den Sie in der gedruckten Version außerdem
 unter dem Kapitel »Reporting Problems and Bugs« finden.
 
 Fehler in der Übersetzuung senden Sie bitte als E-Mail an die Adresse
 "translation-team-de@lists.sourceforge.net"!
 
 gawk ist eine Sprache zur Suche nach und zum Verarbeiten von Mustern.
 Normalerweise liest das Programm von der Standardeingabe ein und gibt
 auf der Standardausgabe aus.
 
 (Es läßt sich sicherlich noch besser machen, aber so - meine ich -
  wäre es schon ein bisschen schöner für deutschsprachige Leser.)
 
 * Man kennt ja die etwas gesteigerte Pingeligkeit*** - oder sagen wir
   besser Korrekt-Genauigkeit**
   
   ** Man muss ja nicht immer gleich alles ins Negative umwenden oder
      um-/hindeuten, was per se ohnehin rein sachlich genommen & benannt
      werden kann und - je nach Ausmaß der Intensivierung im Individual-
      fall - gar nix Schlechtes sein muss, sondern sogar im Gegenteil als
      etwas durchweg Gutes ebenso beurteilt werden kann & ggf. auch sollte
      (vielleicht).
      
*** Ich bin es gewohnt, da notorisch zwischen allen Stühlen zu sitzen:
    Die einen mosern über meine "Überpingeligkeit", die anderen über meine
    "Schludrigkeiten". Lustigerweise kenne ich es auch, beide Vorwürfe von
    ein und derselben Person ab und an mal übergebreezlt oder um die Ohren
    gerieben zu bekommen - je Lust & Laun (hajo, so isch des - wem's Glück
    zu bescheren verspricht: Wrrumn nicht?). ```

Updated on 
Mrz 30, 2014
 by 
Zarko Maroli
 (
Version 2
)