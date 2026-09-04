#!/usr/bin/env python3
"""Zwischenlager: nichts zweimal holen, nichts zweimal rendern.

Das ist der Hebel fuer die Ressourcenfrage. Ein Karussell neu zu rendern kostet
einen Browserstart und sieben Seitenaufbauten; ein Reel zusaetzlich einen
ffmpeg-Lauf und, beim ersten Mal, das Sprachmodell. Wenn an einem Beitrag nur
die Bildunterschrift geaendert wird, soll nichts davon noch einmal passieren.

Der Schluessel ist ein Hash ueber alles, was das Ergebnis beeinflusst: der
Inhalt der Slide, die Markendatei, die Vorlage, das Format. Aendert sich eines,
aendert sich der Schluessel und es wird neu gebaut. Aendert sich nichts, liegt
das Ergebnis schon da.

Bewusst kein Verfallsdatum: ein Bild, das aus denselben Eingaben entsteht, ist
in einem Jahr dasselbe Bild. Aufgeraeumt wird ueber `media-kit aufraeumen`.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

ABTEILUNGEN = ("schriften", "bilder", "stimmen", "ton", "seiten", "ergebnisse")


def schluessel(*teile) -> str:
    """Kurzer, stabiler Hash ueber beliebige Bestandteile.

    Sortierte JSON-Darstellung, damit die Reihenfolge der Schluessel in einem
    Woerterbuch das Ergebnis nicht veraendert - sonst waere der Cache nach
    einem Umsortieren der Job-Datei wertlos.
    """
    h = hashlib.sha256()
    for teil in teile:
        if isinstance(teil, (bytes, bytearray)):
            h.update(teil)
        elif isinstance(teil, Path):
            h.update(teil.read_bytes() if teil.exists() else str(teil).encode())
        else:
            h.update(json.dumps(teil, sort_keys=True, ensure_ascii=False,
                                default=str).encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()[:20]


class Lager:
    def __init__(self, wurzel: str | Path | None = None):
        self.wurzel = Path(
            wurzel or os.environ.get("MEDIA_KIT_LAGER") or (Path.cwd() / ".zwischenlager")
        ).resolve()
        for abteilung in ABTEILUNGEN:
            (self.wurzel / abteilung).mkdir(parents=True, exist_ok=True)

    def __truediv__(self, teil: str) -> Path:
        return self.wurzel / teil

    def ablage(self, abteilung: str, name: str) -> Path:
        return self.wurzel / abteilung / name

    # ------------------------------------------------------------- Erzeugen
    def gebaut(self, abteilung: str, name: str, bauer) -> Path:
        """Liefert die Datei; ruft `bauer(ziel)` nur, wenn sie fehlt.

        Gebaut wird ueber eine Nebendatei und erst danach umbenannt. Sonst
        bliebe nach einem abgebrochenen Lauf eine halbe Datei liegen, die beim
        naechsten Mal als fertig gilt - der unangenehmste Cache-Fehler, weil er
        sich als kaputtes Ergebnis tarnt und nicht als Fehler.
        """
        ziel = self.ablage(abteilung, name)
        if ziel.exists() and ziel.stat().st_size > 0:
            return ziel
        neben = ziel.with_suffix(ziel.suffix + f".halb{os.getpid()}")
        try:
            bauer(neben)
            if not neben.exists() or neben.stat().st_size == 0:
                raise RuntimeError(f"{abteilung}/{name}: nichts erzeugt")
            neben.replace(ziel)
        finally:
            if neben.exists():
                neben.unlink()
        return ziel

    # -------------------------------------------------------------- Abrufen
    def geholt(self, url: str, endung: str = "", versuche: int = 3) -> Path:
        """Laedt eine Adresse einmal und behaelt sie.

        Die Wiederholung mit wachsender Wartezeit ist kein Luxus: Pexels und
        Wikimedia drosseln, und ein Beitrag soll nicht daran scheitern, dass
        eine Bilddatenbank gerade zaeh ist.
        """
        name = schluessel(url) + (endung or Path(url.split("?")[0]).suffix or ".bin")
        ziel = self.ablage("bilder", name)
        if ziel.exists() and ziel.stat().st_size > 0:
            return ziel

        letzter: Exception | None = None
        for versuch in range(versuche):
            try:
                anfrage = urllib.request.Request(
                    url, headers={"User-Agent": "media-kit/1.0 (+github.com/shortheaven3-lang/media-kit)"}
                )
                with urllib.request.urlopen(anfrage, timeout=45) as antwort:
                    daten = antwort.read()
                if len(daten) < 512:
                    raise OSError(f"nur {len(daten)} Byte erhalten")
                neben = ziel.with_suffix(ziel.suffix + ".halb")
                neben.write_bytes(daten)
                neben.replace(ziel)
                return ziel
            except (urllib.error.URLError, OSError, TimeoutError) as fehler:
                letzter = fehler
                if versuch < versuche - 1:
                    time.sleep(2 ** versuch)
        raise OSError(f"{url} nicht erreichbar: {letzter}")

    # ------------------------------------------------------------ Aufraeumen
    def groesse(self) -> int:
        return sum(p.stat().st_size for p in self.wurzel.rglob("*") if p.is_file())

    def leeren(self, abteilung: str | None = None) -> int:
        vorher = self.groesse()
        ziele = [self.wurzel / abteilung] if abteilung else [self.wurzel / a for a in ABTEILUNGEN]
        for ordner in ziele:
            if ordner.exists():
                shutil.rmtree(ordner)
            ordner.mkdir(parents=True, exist_ok=True)
        return vorher - self.groesse()
