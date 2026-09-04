#!/usr/bin/env python3
"""Marken: alles, was das Aussehen bestimmt, an einer Stelle.

Eine Marke ist eine JSON-Datei unter marken/. Sie sagt, welche Vorlage gilt,
welche Farben und Schriften, wie Fotos eingefaerbt werden und wie der Ton
klingt. Der Renderkern kennt keine einzige Farbe.

Damit laesst sich ein zweites Konto anlegen, ohne Code anzufassen - und der
Grund, warum in diesem Projekt zwei sehr verschiedene Bildsprachen aus
demselben Renderer kommen (@shortheaven3 dunkel und seriflastig, @denkbeleg
hell und sachlich), ist genau diese Trennung.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent


@dataclass
class Marke:
    name: str
    anzeigename: str
    vorlage: str
    farben: dict[str, str]
    schriften: dict[str, str]          # Rolle -> Familie, z.B. "titel": "Archivo"
    schriftdateien: list[str]          # Familien, die geholt werden muessen
    ton: dict = field(default_factory=dict)
    bildklima: dict = field(default_factory=dict)
    standardformate: list[str] = field(default_factory=lambda: ["karussell"])
    abbinder: str = ""
    quelle: Path | None = None

    @property
    def hat_bildklima(self) -> bool:
        """Ob Fotos auf das Farbklima der Marke gezogen werden.

        @shortheaven3 legt jedes Foto auf Blau/Kupfer, damit der Feed als
        Flaeche zusammenhaengt. @denkbeleg arbeitet ohne Fotos und braucht das
        nicht.
        """
        return bool(self.bildklima.get("an"))

    def css_variablen(self) -> str:
        """Die Farben als CSS-Custom-Properties, so wie die Vorlagen sie erwarten."""
        zeilen = "".join(f"--{schluessel}:{wert};" for schluessel, wert in self.farben.items())
        for rolle, familie in self.schriften.items():
            zeilen += f"--schrift-{rolle}:'{familie}';"
        return f":root{{{zeilen}}}"


def laden(name: str, ordner: Path | None = None) -> Marke:
    ordner = ordner or (WURZEL / "marken")
    datei = ordner / f"{name}.json"
    if not datei.exists():
        vorhanden = ", ".join(sorted(p.stem for p in ordner.glob("*.json"))) or "keine"
        raise SystemExit(f"Marke {name!r} gibt es nicht. Vorhanden: {vorhanden}")

    daten = json.loads(datei.read_text(encoding="utf-8"))
    fehlend = {"anzeigename", "vorlage", "farben", "schriften"} - set(daten)
    if fehlend:
        raise SystemExit(f"{datei.name}: es fehlt {', '.join(sorted(fehlend))}")

    return Marke(
        name=name,
        anzeigename=daten["anzeigename"],
        vorlage=daten["vorlage"],
        farben=daten["farben"],
        schriften=daten["schriften"],
        schriftdateien=daten.get("schriftdateien") or sorted(set(daten["schriften"].values())),
        ton=daten.get("ton", {}),
        bildklima=daten.get("bildklima", {}),
        standardformate=daten.get("standardformate", ["karussell"]),
        abbinder=daten.get("abbinder", ""),
        quelle=datei,
    )


def alle(ordner: Path | None = None) -> list[str]:
    ordner = ordner or (WURZEL / "marken")
    return sorted(p.stem for p in ordner.glob("*.json"))
