#!/usr/bin/env python3
"""Welches Angebot zu einem Beitrag passt - und wie es aussieht.

Warum ueber den Selbsttest und nicht ueber die Verkaufsseite
------------------------------------------------------------
Ein Beitrag, der nichts anbietet, verdient nichts. Ein Beitrag, der etwas
verkauft, wird weggewischt. Der Selbsttest liegt dazwischen: er redet ueber den
Leser statt ueber das Produkt, kostet nichts und verlangt keine E-Mail-Adresse.
Wer sein Ergebnis gelesen hat, nimmt die drei freien Tage deutlich eher als
jemand, der auf einer Verkaufsseite landet.

Warum die Zuordnung automatisch laeuft
--------------------------------------
Weil sie sonst vergessen wird. Beim Redigieren denkt niemand an den Verweis,
und ein Beitrag ohne Verweis verdient nichts. Die Zuordnung zaehlt Schlagworte
im Beitragstext und nimmt den Bereich mit den meisten Treffern; wer es besser
weiss, schreibt den Bereich in die Job-Datei und ueberstimmt sie damit.

Trifft nichts zu, gibt es den allgemeinen Einstieg statt eines schlecht
geratenen Bereichs. Ein unpassendes Angebot ist schaedlicher als ein
allgemeines: es zeigt, dass niemand hingesehen hat.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent


class AngebotFehler(ValueError):
    pass


@dataclass
class Angebot:
    produkt: str
    name: str
    bereich: str          # "" heisst: der allgemeine Einstieg
    frage: str
    einladung: str
    adresse: str
    art: str = "eigenes"
    treffer: tuple[str, ...] = ()

    def als_slide(self) -> dict:
        """Die Abschluss-Slide, wie sie in die Slide-Liste wandert."""
        return {"typ": "angebot", "frage": self.frage,
                "einladung": self.einladung, "adresse": _ohne_schema(self.adresse)}

    def als_nachweis(self) -> dict:
        return {k: v for k, v in {
            "produkt": self.produkt, "name": self.name, "art": self.art,
            "bereich": self.bereich or "allgemein", "adresse": self.adresse,
            "zugeordnet_ueber": ", ".join(self.treffer) or "keine Treffer, allgemeiner Einstieg",
        }.items() if v}


# Platzhalter, die wie eine Adresse aussehen und keine sind. Die erste steht so
# in der Dokumentation der WebApp - genau deshalb landet sie leicht versehentlich
# hier, und genau deshalb steht sie in dieser Liste.
PLATZHALTER = ("deine-adresse", "example.", "beispiel.", "localhost",
               "127.0.0.1", "meine-domain", "your-domain")


def _ist_platzhalter(adresse: str) -> bool:
    niedrig = adresse.lower()
    return any(p in niedrig for p in PLATZHALTER)


def _ohne_schema(adresse: str) -> str:
    """Fuer die Anzeige: kein https:// und kein www davor.

    Auf einer Slide steht die Adresse zum Abtippen, nicht zum Anklicken -
    Instagram macht daraus ohnehin keinen Verweis. Was niemand tippen muss,
    soll auch nicht dastehen.
    """
    return re.sub(r"^https?://(www\.)?", "", adresse).rstrip("/")


def _normal(text: str) -> str:
    """Kleinschreibung und Umlaute vereinheitlicht.

    Damit "gruebeln" in den Schlagworten auch "grübeln" im Beitrag findet und
    umgekehrt - sonst haengt die Zuordnung daran, wie jemand gerade tippt.
    """
    text = (text or "").lower()
    for um, ersatz in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(um, ersatz)
    return unicodedata.normalize("NFKD", text)


def laden(pfad: Path | None = None) -> dict:
    pfad = pfad or (WURZEL / "produkte.json")
    if not pfad.exists():
        raise AngebotFehler(f"{pfad} fehlt - ohne sie gibt es keine Angebote.")
    return json.loads(pfad.read_text(encoding="utf-8"))


def text_des_beitrags(job) -> str:
    """Alles, woraus sich das Thema ablesen laesst."""
    teile = [job.caption, job.rubrik, job.notiz]
    for slide in job.slides:
        teile += [str(slide.get(feld, "")) for feld in
                  ("titel", "unterzeile", "kopf", "text", "merksatz", "herkunft")]
    return _normal(" ".join(t for t in teile if t))


def zuordnen(job, daten: dict | None = None, produkt: str = "selbsttest",
             bereich: str = "") -> Angebot:
    """Sucht den passenden Bereich - oder nimmt den vorgegebenen."""
    daten = daten or laden()
    basis = (daten.get("basis") or "").rstrip("/")
    if not basis or _ist_platzhalter(basis):
        raise AngebotFehler(
            f"In produkte.json steht keine brauchbare Basisadresse ({basis or 'leer'}). "
            "Eine Abschluss-Slide mit falscher Adresse ist schlimmer als keine: sie "
            "verspricht eine Seite, die niemand findet, und das faellt erst auf, "
            "wenn der Beitrag schon steht."
        )

    p = (daten.get("produkte") or {}).get(produkt)
    if not p:
        bekannt = ", ".join(sorted((daten.get("produkte") or {}))) or "keine"
        raise AngebotFehler(f"Unbekanntes Produkt {produkt!r}. Bekannt: {bekannt}")

    bereiche = p.get("bereiche") or {}
    if bereich and bereich not in bereiche:
        raise AngebotFehler(
            f"Bereich {bereich!r} gibt es bei {produkt!r} nicht. "
            f"Bekannt: {', '.join(sorted(bereiche))}"
        )

    treffer: tuple[str, ...] = ()
    if not bereich:
        bereich, treffer = _bester_bereich(text_des_beitrags(job), bereiche)

    if bereich:
        eintrag = bereiche[bereich]
        return Angebot(produkt=produkt, name=p.get("name", produkt), bereich=bereich,
                       frage=eintrag.get("frage", ""),
                       einladung=p.get("einladung", ""),
                       adresse=basis + eintrag.get("adresse", "/"),
                       art=p.get("art", "eigenes"), treffer=treffer)

    return Angebot(produkt=produkt, name=p.get("name", produkt), bereich="",
                   frage=p.get("frage", "In welchem Bereich ist es bei dir am lautesten?"),
                   einladung=p.get("einladung", ""),
                   adresse=basis + p.get("einstieg", "/"),
                   art=p.get("art", "eigenes"))


# Ein einzelnes Schlagwort ist Zufall. Erst ab zwei wird aus einem Streiftreffer
# ein Thema - darunter ist der allgemeine Einstieg die ehrlichere Antwort.
MINDESTTREFFER = 2


def _bester_bereich(text: str, bereiche: dict) -> tuple[str, tuple[str, ...]]:
    beste, bestpunkte, besttreffer = "", 0, ()
    for name, eintrag in sorted(bereiche.items()):
        gefunden = tuple(w for w in eintrag.get("schlagworte", []) if _normal(w) in text)
        if len(gefunden) > bestpunkte:
            beste, bestpunkte, besttreffer = name, len(gefunden), gefunden
    if bestpunkte < MINDESTTREFFER:
        return "", ()
    return beste, besttreffer


def gewuenscht(job, marke) -> tuple[bool, str]:
    """Ob dieser Beitrag ein Angebot bekommt und welcher Bereich gilt.

    Die Marke gibt vor, der Beitrag darf ueberstimmen - auch nach unten:
    `"angebot": false` laesst die Slide weg. Nicht jeder Beitrag vertraegt
    einen Verweis.
    """
    wunsch = job.angebot
    if wunsch is False:
        return False, ""
    if isinstance(wunsch, str) and wunsch:
        return True, wunsch
    if wunsch is True:
        return True, ""
    return bool((marke.angebot or {}).get("an")), ""
