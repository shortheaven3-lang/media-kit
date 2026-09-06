#!/usr/bin/env python3
"""Aus Job und Marke wird HTML.

Warum HTML und nicht direkt gezeichnet
--------------------------------------
Weil Textsatz schwer ist. Zeilenumbruch, Ligaturen, Kerning, haengende
Interpunktion, gemischte Auszeichnung mitten im Satz - das alles kann ein
Browser seit Jahrzehnten richtig, und eine Zeichenschleife in Python kann es
nie ganz. Dazu kommt, dass sich ein Layout in CSS aendern laesst, ohne den
Renderkern anzufassen.

Der Preis ist ein Browser als Abhaengigkeit. Er wird einmal je Lauf gestartet
und macht alle Slides aller Formate - siehe bild.py.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from .formate import Format
from .marke import Marke

WURZEL = Path(__file__).resolve().parent.parent

# Was Instagram im Reel ueberdeckt: oben die Profilzeile, unten Bildunterschrift
# und Schaltflaechen. Zahlen aus der Praxis des Autoposters, nicht geraten.
# Wer sie ignoriert, setzt den Merksatz unter den Folgen-Knopf.
SICHERHEIT: dict[str, tuple[int, int]] = {
    "reel":  (140, 330),
    "story": (150, 250),   # Story: unten die Antwortzeile, oben der Fortschrittsbalken
}

# Auszeichnung, die im Slide-Text stehen darf. Alles andere wird escaped -
# eine Job-Datei ist Inhalt, keine Programmiersprache.
ERLAUBT = ("b", "strong", "i", "em", "mark", "br", "span", "small")
_ERLAUBT_MUSTER = re.compile(
    r"&lt;(/?)(" + "|".join(ERLAUBT) + r")\s*(/?)&gt;", re.IGNORECASE
)


def sicher(text: str) -> str:
    """Escapt alles und laesst die Handvoll erlaubter Auszeichnungen wieder zu.

    Der Weg ueber "erst alles escapen, dann gezielt zuruecknehmen" statt ueber
    "die gefaehrlichen Sachen entfernen" ist Absicht: eine Positivliste kann man
    nicht unterlaufen, eine Negativliste immer.
    """
    return _ERLAUBT_MUSTER.sub(r"<\1\2\3>", html.escape(str(text or "")))


def absaetze(text: str) -> str:
    """Leerzeile trennt Absatz. Genau wie in den bestehenden Beitragsdateien."""
    teile = [t.strip() for t in re.split(r"\n\s*\n", str(text or "").strip()) if t.strip()]
    return "".join(f"<p>{sicher(t)}</p>" for t in teile)


# --------------------------------------------------------------- Slide-Rumpf
def rumpf(slide: dict, nummer: int, gesamt: int, marke: Marke) -> tuple[str, str]:
    """Liefert (Typklasse, innerer HTML-Block) fuer eine Slide."""
    typ = slide.get("typ", "inhalt")

    if typ == "haken":
        block = f"<h1>{sicher(slide['titel'])}</h1>"
        if slide.get("unterzeile"):
            block += f"<div class='unterzeile'>{sicher(slide['unterzeile'])}</div>"

    elif typ == "ende":
        abbinder = slide.get("abbinder") or (
            f"Folge <span>{marke.abbinder}</span>" if marke.abbinder else ""
        )
        block = f"<div class='merksatz'>{sicher(slide['merksatz'])}</div>"
        if abbinder:
            block += f"<div class='abbinder'>{sicher(abbinder)}</div>"

    elif typ == "angebot":
        # Kein Verkauf, ein Angebot: erst die Frage, die den Leser meint, dann
        # was dahintersteckt, dann die Adresse. Umgekehrt liest es niemand.
        block = f"<div class='frage'>{sicher(slide['frage'])}</div>"
        if slide.get("einladung"):
            block += f"<div class='einladung'>{sicher(slide['einladung'])}</div>"
        if slide.get("adresse"):
            block += f"<div class='adresse'>{sicher(slide['adresse'])}</div>"

    elif typ == "zitat":
        block = f"<div class='fliess'>{absaetze(slide['text'])}</div>"
        if slide.get("herkunft"):
            block += f"<div class='herkunft'>{sicher(slide['herkunft'])}</div>"

    else:  # inhalt und frage
        block = ""
        if slide.get("kopf"):
            block += f"<div class='kopf'>{sicher(slide['kopf'])}</div>"
        block += f"<div class='fliess'>{absaetze(slide['text'])}</div>"
        if slide.get("quelle"):
            block += f"<div class='quelle'>{sicher(slide['quelle'])}</div>"

    # Zaehler nur dort, wo er hilft: nicht auf der letzten Slide, nie bei einem
    # Einzelbild. "03 / 07" auf einem Einzelbild verspricht sechs Slides, die
    # es nicht gibt.
    zaehler = ""
    if gesamt > 1 and typ not in ("ende", "angebot"):
        zaehler = f"<div class='zaehler'>{nummer:02d} / {gesamt:02d}</div>"

    return typ, zaehler + block


# ------------------------------------------------------------------- Ganzes
def seite(
    slide: dict,
    nummer: int,
    gesamt: int,
    marke: Marke,
    format: Format,
    schrift_css: str,
    *,
    schicht: str = "voll",
    hintergrundbild: str | None = None,
    stempel: str = "",
) -> str:
    """Baut die vollstaendige HTML-Seite fuer genau eine Aufnahme.

    `schicht` steuert, was sichtbar ist:
      voll         alles - der Weg fuer Standbilder
      hintergrund  nur Grund und Schleier - im Video die Ebene, die zieht
      text         nur der Satz, transparent - im Video die Ebene, die steht
    """
    oben, unten = SICHERHEIT.get(format.name, (0, 0))
    grundgroesse = format.breite / 1080 * 16
    quer = "quer" if format.verhaeltnis > 1 else "hoch"

    typ, block = rumpf(slide, nummer, gesamt, marke)

    basis = (WURZEL / "vorlagen" / "basis.css").read_text(encoding="utf-8")
    stil = (WURZEL / "vorlagen" / f"{marke.vorlage}.css").read_text(encoding="utf-8")

    bild = ""
    if hintergrundbild and schicht in ("voll", "hintergrund"):
        bild = f"<img src='{html.escape(hintergrundbild)}' alt=''>"

    stempelblock = f"<div class='stempel'>{sicher(stempel)}</div>" if stempel else ""

    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>{html.escape(str(nummer))}</title>
<style>
{schrift_css}
{marke.css_variablen()}
:root{{
  --breite:{format.breite}px; --hoehe:{format.hoehe}px;
  --sicher-oben:{oben}px; --sicher-unten:{unten}px;
}}
html{{font-size:{grundgroesse:.4f}px;}}
{basis}
{stil}
</style></head>
<body class="fmt-{format.name} {quer} typ-{typ} schicht-{schicht}">
  <div class="grund">{bild}</div>
  <div class="schleier"></div>
  {stempelblock}
  <div class="blatt">{block}</div>
</body></html>"""
