#!/usr/bin/env python3
"""Ausgabeformate.

Ein Job beschreibt einen Beitrag inhaltlich. Welche Datei am Ende herauskommt,
entscheidet das Format. Die Masse stehen hier an genau einer Stelle, damit eine
Aenderung an der Instagram-Spezifikation nicht durch fuenf Dateien wandert.

Die Hoehe 1350 statt 1440: Instagram nimmt 4:5 an, schneidet aber alles
Hoehere auf 4:5 zurueck. Wer 1440 liefert, laesst zuschneiden statt zu setzen.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Format:
    name: str
    breite: int
    hoehe: int
    art: str            # "slides" | "bild" | "video"
    endung: str
    guete: int | None   # JPEG-Guete; None bei PNG und MP4
    zweck: str

    @property
    def verhaeltnis(self) -> float:
        return self.breite / self.hoehe

    @property
    def ist_video(self) -> bool:
        return self.art == "video"

    def dateiname(self, stamm: str, nummer: int | None = None) -> str:
        if nummer is None:
            return f"{stamm}.{self.endung}"
        return f"{nummer:02d}.{self.endung}"


FORMATE: dict[str, Format] = {
    "karussell": Format(
        "karussell", 1080, 1350, "slides", "jpg", 88,
        "Instagram-Karussell, 4:5. Der Standard fuer mehrteilige Beitraege.",
    ),
    "reel": Format(
        "reel", 1080, 1920, "video", "mp4", None,
        "Reel oder Short, 9:16 mit Ton. Die einzige Flaeche mit Reichweite ueber die Follower hinaus.",
    ),
    "story": Format(
        "story", 1080, 1920, "bild", "jpg", 88,
        "Story-Standbild, 9:16. Ankuendigung, Zitatkarte, Verweis auf den Beitrag.",
    ),
    "beitrag": Format(
        "beitrag", 1080, 1080, "bild", "jpg", 88,
        "Einzelbild im Quadrat. Fuer Konten, die kein 4:5 fahren.",
    ),
    "og": Format(
        "og", 1200, 630, "bild", "png", None,
        "Vorschaubild fuer Web und Messenger (Open Graph). PNG, weil Text darauf hart bleiben soll.",
    ),
    "titelbild": Format(
        "titelbild", 1600, 900, "bild", "jpg", 90,
        "Titelbild fuer Seiten und Lektionen der WebApp, 16:9.",
    ),
}

# Formate, die ohne ausdrueckliche Angabe gerendert werden, wenn eine Marke
# selbst nichts vorgibt.
STANDARD = ("karussell",)


def hole(name: str) -> Format:
    try:
        return FORMATE[name]
    except KeyError:
        bekannt = ", ".join(sorted(FORMATE))
        raise SystemExit(f"Unbekanntes Format {name!r}. Bekannt sind: {bekannt}")


def alle_namen() -> tuple[str, ...]:
    return tuple(sorted(FORMATE))
