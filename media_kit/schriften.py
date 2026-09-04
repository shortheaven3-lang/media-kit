#!/usr/bin/env python3
"""Schriften holen und im Zwischenlager halten.

Warum nicht ueber das System (apt-get install fonts-...)
--------------------------------------------------------
Weil das Ergebnis dann von der Distribution des Laufs abhaengt. Debian liefert
eine andere Fassung von EB Garamond als Ubuntu, und ein Zeilenumbruch, der
lokal sitzt, sitzt in der Action ploetzlich anders. Eine feste Datei aus dem
Google-Fonts-Bestand ist ueberall dieselbe Datei.

Alle hier genannten Schriften stehen unter der SIL Open Font License. Die
erlaubt die kommerzielle Nutzung und die Einbettung ausdruecklich; verlangt
wird nur, dass die Schrift nicht selbst verkauft wird. Der Lizenztext wandert
beim ersten Holen mit ins Zwischenlager, damit der Beleg vorliegt.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path

BESTAND = "https://raw.githubusercontent.com/google/fonts/main"

# Familie -> (Pfad im Google-Fonts-Bestand, Lizenz)
# Variable Schnitte, wo es sie gibt: eine Datei deckt alle Staerken ab und
# spart drei weitere Abrufe.
SCHRIFTEN: dict[str, tuple[str, str]] = {
    "Archivo":        ("ofl/archivo/Archivo%5Bwdth,wght%5D.ttf", "OFL-1.1"),
    "Inter":          ("ofl/inter/Inter%5Bopsz,wght%5D.ttf", "OFL-1.1"),
    "JetBrainsMono":  ("ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf", "OFL-1.1"),
    "EBGaramond":     ("ofl/ebgaramond/EBGaramond%5Bwght%5D.ttf", "OFL-1.1"),
    "EBGaramondItalic": ("ofl/ebgaramond/EBGaramond-Italic%5Bwght%5D.ttf", "OFL-1.1"),
    "Lora":           ("ofl/lora/Lora%5Bwght%5D.ttf", "OFL-1.1"),
    "LoraItalic":     ("ofl/lora/Lora-Italic%5Bwght%5D.ttf", "OFL-1.1"),
    "Cormorant":      ("ofl/cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf", "OFL-1.1"),
    "SpaceGrotesk":   ("ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf", "OFL-1.1"),
}


class SchriftFehlt(RuntimeError):
    pass


def pfad(familie: str, lager: Path) -> Path:
    """Liefert die lokale Datei; holt sie beim ersten Mal.

    Das Ergebnis liegt im Zwischenlager und ueberlebt damit den Lauf. In der
    Action haengt ein actions/cache davor, sodass auch der Abruf entfaellt.
    """
    if familie not in SCHRIFTEN:
        bekannt = ", ".join(sorted(SCHRIFTEN))
        raise SchriftFehlt(f"Schrift {familie!r} ist nicht hinterlegt. Bekannt: {bekannt}")

    ziel = lager / "schriften" / f"{familie}.ttf"
    if ziel.exists() and ziel.stat().st_size > 20_000:
        return ziel

    ziel.parent.mkdir(parents=True, exist_ok=True)
    quelle, _lizenz = SCHRIFTEN[familie]
    url = f"{BESTAND}/{quelle}"
    try:
        with urllib.request.urlopen(url, timeout=30) as antwort:
            daten = antwort.read()
    except (urllib.error.URLError, TimeoutError) as fehler:
        raise SchriftFehlt(f"{familie} nicht erreichbar ({url}): {fehler}") from fehler

    if len(daten) < 20_000:
        raise SchriftFehlt(f"{familie} kam unvollstaendig an ({len(daten)} Byte)")

    ziel.write_bytes(daten)
    return ziel


def css(familien: list[str], lager: Path, arbeit: Path) -> str:
    """Legt die Schriftdateien neben die HTML-Datei und liefert die @font-face-Regeln.

    Nicht als data:-URI eingebettet, obwohl das verlockend waere: EB Garamond
    allein ist 851 KB, base64 macht daraus 1,1 MB, und das steckte dann in
    jeder einzelnen Slide-Seite. Bei sieben Slides mal vier Formaten ist das
    Verschwendung ohne Gegenwert.

    Der bekannte Haken an file:-Schriften ist, dass ein fehlgeschlagener Ladevorgang
    stillschweigend auf die Ersatzschrift zurueckfaellt - das Bild sieht falsch
    aus, aber nichts bricht ab. Dagegen steht die Pruefung in bild.py: dort wird
    nach dem Laden ausdruecklich nachgesehen, ob jede Familie wirklich da ist,
    und der Lauf bricht ab, wenn nicht. Ein falsch gesetztes Bild faellt so hier
    auf und nicht erst auf Instagram.
    """
    ordner = arbeit / "schriften"
    ordner.mkdir(parents=True, exist_ok=True)

    teile = []
    for familie in familien:
        quelle = pfad(familie, lager)
        ziel = ordner / quelle.name
        if not ziel.exists() or ziel.stat().st_size != quelle.stat().st_size:
            ziel.write_bytes(quelle.read_bytes())
        # Ein kursiver Schnitt bekommt denselben Familiennamen wie sein
        # aufrechter und unterscheidet sich nur im font-style. Sonst muesste
        # jede Vorlage zwei Familien kennen und <em> von Hand umschalten.
        if familie.endswith("Italic"):
            name, stil = familie[: -len("Italic")], "italic"
        else:
            name, stil = familie, "normal"
        teile.append(
            f"@font-face{{font-family:'{name}';"
            f"src:url('schriften/{quelle.name}') format('truetype');"
            f"font-weight:100 900;font-style:{stil};font-display:block;}}"
        )
    return "".join(teile)


def geprueft_werden(familien: list[str]) -> list[str]:
    """Die Familiennamen, die nach dem Laden im Browser vorhanden sein muessen."""
    return sorted({f[: -len("Italic")] if f.endswith("Italic") else f for f in familien})


def lizenzen(familien: list[str]) -> list[dict]:
    """Nachweis fuer die verwendeten Schriften."""
    return [
        {"familie": f, "lizenz": SCHRIFTEN[f][1],
         "quelle": f"{BESTAND}/{SCHRIFTEN[f][0]}"}
        for f in familien if f in SCHRIFTEN
    ]
