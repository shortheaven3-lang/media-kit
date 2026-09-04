#!/usr/bin/env python3
"""Freie Bilder holen - und den Lizenznachweis gleich mit.

Was hier drin ist und was nicht
-------------------------------
Aufgenommen sind nur Quellen, deren Lizenz die kommerzielle Nutzung ausdruecklich
erlaubt:

  pexels     Pexels-Lizenz: kommerziell erlaubt, Namensnennung nicht verlangt.
             Braucht einen kostenlosen Schluessel (PEXELS_API_KEY).
  wikimedia  Wikimedia Commons: alles Public Domain oder CC. Braucht keinen
             Schluessel - die einzige Quelle, die ohne Anmeldung funktioniert,
             und deshalb der Rueckfall.
  pixabay    Pixabay-Lizenz, kommerziell erlaubt. Schluessel: PIXABAY_API_KEY.
  datei      eine Datei aus dem Repository. Schlaegt alles andere.

Ausdruecklich nicht aufgenommen:
  * Openverse - hat den anonymen Zugang am 31.08.2026 geschlossen (HTTP 401).
  * Unsplash - die Lizenz ist grosszuegig, die API-Bedingungen verlangen aber
    eine Verlinkung zurueck und verbieten das dauerhafte Speichern der Bilder.
    Fuer ein Repository, das die Bilder festhaelt, passt das nicht.
  * Bildersuchen ueber Suchmaschinen. Was dort liegt, ist meist nicht frei.

Der Nachweis
------------
Jeder Treffer wird mit Urheber, Lizenz und Fundstelle protokolliert und landet
neben dem Beitrag in `nachweis.json`. Das kostet nichts und ist im Zweifel der
Beleg. Die Pexels-Lizenz verlangt keine Namensnennung - das ist kein Grund,
sie nicht festzuhalten.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

from .zwischenlager import Lager


@dataclass
class Treffer:
    url: str
    anbieter: str
    urheber: str = ""
    lizenz: str = ""
    fundstelle: str = ""
    kennung: str = ""

    def als_nachweis(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}


class KeinTreffer(RuntimeError):
    pass


# Wikimedia verlangt in seiner Richtlinie fuer Zugriffe ohne Anmeldung einen
# User-Agent, der das Programm nennt und eine Kontaktmoeglichkeit angibt, und
# beantwortet generische Kennungen mit 403. Dieselbe Kennung schadet bei den
# anderen Anbietern nicht, also gilt sie ueberall.
KENNUNG = ("media-kit/1.0 (https://github.com/shortheaven3-lang/media-kit; "
           "Medienerzeugung fuer eigene Social-Media-Konten)")

# Was beim letzten Abruf schiefging, je Anbieter. Ohne das sieht ein
# abgewiesener Zugriff genauso aus wie ein Suchwort ohne Treffer.
letzter_fehler: dict[str, str] = {}


def _json_holen(url: str, kopfzeilen: dict | None = None, zeit: int = 30) -> dict:
    anfrage = urllib.request.Request(
        url, headers={"User-Agent": KENNUNG, **(kopfzeilen or {})}
    )
    with urllib.request.urlopen(anfrage, timeout=zeit) as antwort:
        return json.loads(antwort.read().decode("utf-8"))


# ------------------------------------------------------------------- Pexels
def pexels(begriff: str, anzahl: int = 5, quer: bool = False) -> list[Treffer]:
    schluessel = os.environ.get("PEXELS_API_KEY")
    if not schluessel:
        letzter_fehler["pexels"] = "kein PEXELS_API_KEY gesetzt"
        return []
    url = ("https://api.pexels.com/v1/search?"
           + urllib.parse.urlencode({
               "query": begriff, "per_page": max(1, min(anzahl, 30)),
               "orientation": "landscape" if quer else "portrait",
           }))
    try:
        daten = _json_holen(url, {"Authorization": schluessel})
    except Exception as fehler:
        letzter_fehler["pexels"] = f"{type(fehler).__name__}: {fehler}"
        return []
    treffer = []
    for foto in daten.get("photos", []):
        quellen = foto.get("src", {})
        gross = quellen.get("original") or quellen.get("large2x") or quellen.get("large")
        if not gross:
            continue
        treffer.append(Treffer(
            url=gross, anbieter="pexels",
            urheber=foto.get("photographer", ""),
            lizenz="Pexels-Lizenz (kommerziell erlaubt, Namensnennung nicht verlangt)",
            fundstelle=foto.get("url", ""), kennung=str(foto.get("id", "")),
        ))
    return treffer


# ---------------------------------------------------------------- Wikimedia
def wikimedia(begriff: str, anzahl: int = 5, quer: bool = False) -> list[Treffer]:
    """Commons durchsuchen. Ohne Schluessel, deshalb der Rueckfall.

    Gesucht wird ueber die Volltextsuche im Dateinamensraum und danach werden
    die Bildinformationen in einem zweiten Aufruf geholt. Zwei Abrufe statt
    einem, dafuer kommen Urheber und Lizenz gleich mit - und ohne die waere der
    Treffer wertlos, weil Commons eben nicht durchgehend frei ist.
    """
    # Der Korb muss deutlich groesser sein als die gewuenschte Zahl: danach
    # faellt alles mit NC oder ND heraus, und die Sortierung nach Ausrichtung
    # kommt noch dazu. Mit gsrlimit=anzahl*2 blieb regelmaessig nichts uebrig.
    #
    # 1280 statt 2000 als Thumbnailbreite ist kein Qualitaetsverzicht, sondern
    # eine Zeitfrage: Commons haelt die gaengigen Breiten vorgerechnet bereit
    # und erzeugt krumme Werte erst auf Anfrage. Bei grossen Originalen dauert
    # das zehn Sekunden und mehr - pro Bild. Der Hintergrund wird ohnehin
    # weichgezeichnet und abgedunkelt.
    suche = ("https://commons.wikimedia.org/w/api.php?"
             + urllib.parse.urlencode({
                 "action": "query", "format": "json", "generator": "search",
                 "gsrnamespace": "6", "gsrsearch": f"filetype:bitmap {begriff}",
                 "gsrlimit": max(10, min(anzahl * 8, 50)),
                 "prop": "imageinfo", "iiprop": "url|extmetadata|size",
                 "iiurlwidth": "1280",
             }))
    try:
        daten = _json_holen(suche)
    except Exception as fehler:
        letzter_fehler["wikimedia"] = f"{type(fehler).__name__}: {fehler}"
        return []

    treffer = []
    for seite in (daten.get("query", {}).get("pages", {}) or {}).values():
        infos = (seite.get("imageinfo") or [{}])[0]
        breite, hoehe = infos.get("width", 0), infos.get("height", 0)
        if not breite or not hoehe:
            continue
        meta = infos.get("extmetadata", {}) or {}
        lizenz = (meta.get("LicenseShortName", {}) or {}).get("value", "")
        # Alles mit NC oder ND fliegt raus - die Konten haben Umsatzabsicht.
        if _eingeschraenkt(lizenz):
            continue
        treffer.append((_abstand(breite, hoehe, quer), Treffer(
            url=infos.get("thumburl") or infos.get("url", ""),
            anbieter="wikimedia",
            urheber=_text_ohne_html((meta.get("Artist", {}) or {}).get("value", "")),
            lizenz=lizenz or "siehe Fundstelle",
            fundstelle=infos.get("descriptionurl", ""),
            kennung=seite.get("title", ""),
        )))

    # Nach Ausrichtung sortiert, nicht danach gefiltert. Commons ist ueberwiegend
    # Querformat; wer Hochformat erzwingt, bekommt fuer die meisten Suchworte gar
    # nichts. Ein liegendes Foto laesst sich mittig beschneiden - fuer einen
    # weichgezeichneten Stimmungshintergrund reicht das allemal.
    treffer.sort(key=lambda paar: paar[0])
    return [t for _, t in treffer if t.url][:anzahl]


def _abstand(breite: int, hoehe: int, quer: bool) -> float:
    """Wie weit ein Bild vom gewuenschten Seitenverhaeltnis entfernt ist."""
    ziel = 16 / 9 if quer else 9 / 16
    return abs((breite / hoehe) - ziel)


# NC und ND nur als eigenstaendige Bausteine, nicht als Buchstabenfolge.
# Ein schlichtes "NC" in lizenz.upper() trifft auch "LICENCE" - L-I-C-E-N-C-E -
# und warf damit jede Lizenz in britischer oder franzoesischer Schreibweise
# hinaus, obwohl sie voellig frei ist.
_EINGESCHRAENKT = __import__("re").compile(r"(?:^|[^A-Z])(NC|ND)(?:[^A-Z]|$)")


def _eingeschraenkt(lizenz: str) -> bool:
    """Ob die Lizenz kommerzielle Nutzung oder Bearbeitung untersagt."""
    return bool(_EINGESCHRAENKT.search((lizenz or "").upper()))


def _text_ohne_html(roh: str) -> str:
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", roh or "")).strip()[:120]


# ------------------------------------------------------------------ Pixabay
def pixabay(begriff: str, anzahl: int = 5, quer: bool = False) -> list[Treffer]:
    schluessel = os.environ.get("PIXABAY_API_KEY")
    if not schluessel:
        letzter_fehler["pixabay"] = "kein PIXABAY_API_KEY gesetzt"
        return []
    url = ("https://pixabay.com/api/?"
           + urllib.parse.urlencode({
               "key": schluessel, "q": begriff, "image_type": "photo",
               "orientation": "horizontal" if quer else "vertical",
               "per_page": max(3, min(anzahl, 200)), "safesearch": "true",
           }))
    try:
        daten = _json_holen(url)
    except Exception as fehler:
        letzter_fehler["pixabay"] = f"{type(fehler).__name__}: {fehler}"
        return []
    return [
        Treffer(url=t.get("largeImageURL", ""), anbieter="pixabay",
                urheber=t.get("user", ""),
                lizenz="Pixabay-Lizenz (kommerziell erlaubt)",
                fundstelle=t.get("pageURL", ""), kennung=str(t.get("id", "")))
        for t in daten.get("hits", []) if t.get("largeImageURL")
    ][:anzahl]


ANBIETER = {"pexels": pexels, "wikimedia": wikimedia, "pixabay": pixabay}
REIHENFOLGE = ("pexels", "pixabay", "wikimedia")


def suchen_mit_bericht(begriff: str, anbieter: str = "", anzahl: int = 5,
                       quer: bool = False) -> tuple[list[Treffer], dict[str, int]]:
    """Wie `suchen`, liefert aber zusaetzlich, was jeder Anbieter beigetragen hat.

    Der Bericht ist kein Beiwerk. Findet die Kette nichts, sieht man ohne ihn
    nur ein Bild, das fehlt - und nicht, ob ein Schluessel fehlt, ein Anbieter
    schweigt oder das Suchwort einfach nichts hergibt. Genau dieser Fall ist
    hier schon einmal unbemerkt durchgelaufen.
    """
    liste = [anbieter] if anbieter else list(REIHENFOLGE)
    gefunden: list[Treffer] = []
    bericht: dict[str, int] = {}
    for name in liste:
        funktion = ANBIETER.get(name)
        if not funktion:
            raise SystemExit(f"Unbekannter Anbieter {name!r}. "
                             f"Bekannt: {', '.join(sorted(ANBIETER))}")
        letzter_fehler.pop(name, None)
        teil = funktion(begriff, anzahl, quer)
        bericht[name] = len(teil)
        gefunden += teil
        if len(gefunden) >= anzahl:
            break
    return gefunden[:anzahl], bericht


def suchen(begriff: str, anbieter: str = "", anzahl: int = 5,
           quer: bool = False) -> list[Treffer]:
    """Sucht bei einem Anbieter oder der Reihe nach bei allen.

    Ohne Angabe wird Pexels zuerst gefragt (beste Treffer fuer Stimmungsbilder)
    und Wikimedia zuletzt (braucht keinen Schluessel und antwortet immer).
    """
    return suchen_mit_bericht(begriff, anbieter, anzahl, quer)[0]


# -------------------------------------------------------------------- Holen
def beschaffen(angabe: str, lager: Lager, wurzel: Path,
               quer: bool = False) -> tuple[Path | None, Treffer | None]:
    """Loest eine Bildangabe aus der Job-Datei zu einer lokalen Datei auf.

    Erlaubte Formen, in dieser Reihenfolge der Bestimmtheit:
        datei:bilder/eigenes.jpg   eine Datei im Repository
        https://...                eine feste Adresse
        pexels:12345               ein bestimmter Treffer
        motiv:leerer strand        eine Suche - blind und trifft oft daneben,
                                   deshalb nur als Notnagel gedacht

    Der vorgesehene Weg ist die feste Adresse: sie wird beim Redigieren gesetzt,
    nachdem jemand die Treffer wirklich angesehen hat. Der Renderlauf laedt dann
    nur noch herunter, und das Ergebnis bleibt Bild fuer Bild reproduzierbar.
    """
    angabe = (angabe or "").strip()
    if not angabe:
        return None, None

    if angabe.startswith("datei:"):
        pfad = (wurzel / angabe[len("datei:"):]).resolve()
        if not pfad.exists():
            raise KeinTreffer(f"{angabe}: die Datei gibt es nicht ({pfad})")
        return pfad, Treffer(url=str(pfad), anbieter="datei", lizenz="eigen")

    if angabe.startswith(("http://", "https://")):
        return lager.geholt(angabe), Treffer(url=angabe, anbieter="adresse")

    if ":" in angabe:
        art, rest = angabe.split(":", 1)
        rest = rest.strip()
        if art == "motiv":
            treffer, bericht = suchen_mit_bericht(rest, anzahl=1, quer=quer)
            if not treffer:
                teile = []
                for name, zahl in bericht.items():
                    grund = letzter_fehler.get(name)
                    teile.append(f"{name}: {zahl}" + (f" ({grund})" if grund else ""))
                raise KeinTreffer(
                    f"kein freies Bild zu {rest!r} gefunden - "
                    + "; ".join(teile)
                )
            return lager.geholt(treffer[0].url), treffer[0]
        if art in ANBIETER:
            # Ein benannter Treffer: ueber die Suche nach der Kennung finden.
            for kandidat in ANBIETER[art](rest, 30, quer):
                if kandidat.kennung == rest:
                    return lager.geholt(kandidat.url), kandidat
            treffer = ANBIETER[art](rest, 1, quer)
            if treffer:
                return lager.geholt(treffer[0].url), treffer[0]
            return None, None

    raise KeinTreffer(
        f"Mit {angabe!r} kann ich nichts anfangen. Erwartet wird "
        "'datei:...', eine https-Adresse, 'pexels:<kennung>' oder 'motiv:<suchwort>'."
    )


# ------------------------------------------------------------- Aufbereiten
def aufbereiten(quelle: Path, ziel: Path, breite: int, hoehe: int,
                klima: dict | None = None) -> Path:
    """Zuschneiden, auf das Markenklima ziehen, weichzeichnen, abdunkeln.

    Ein Foto soll Stimmung tragen, nicht mit der Schrift um Aufmerksamkeit
    streiten. Ohne diese Aufbereitung gewinnt immer das Foto.
    """
    from PIL import Image, ImageFilter

    klima = klima or {}
    bild = Image.open(quelle).convert("RGB")

    # Fuellend zuschneiden, mittig. Kein Verzerren, kein Rand.
    ziel_verh = breite / hoehe
    ist_verh = bild.width / bild.height
    if ist_verh > ziel_verh:
        neu = int(bild.height * ziel_verh)
        links = (bild.width - neu) // 2
        bild = bild.crop((links, 0, links + neu, bild.height))
    else:
        neu = int(bild.width / ziel_verh)
        oben = (bild.height - neu) // 2
        bild = bild.crop((0, oben, bild.width, oben + neu))
    bild = bild.resize((breite, hoehe), Image.LANCZOS)

    if klima.get("an"):
        bild = _einfaerben(bild, klima)
        if klima.get("weichzeichnen"):
            bild = bild.filter(ImageFilter.GaussianBlur(float(klima["weichzeichnen"])))

    ziel.parent.mkdir(parents=True, exist_ok=True)
    bild.save(ziel, "JPEG", quality=90, optimize=True)
    return ziel


def _einfaerben(bild, klima: dict):
    """Dreipunkt-Rampe statt Graustufen.

    Ein reines Duplex zieht das ganze Bild ins Braune und nimmt dem Konto sein
    Farbklima. Mit drei Stuetzstellen bleiben Schatten und Mitten im Markenton
    und die Waerme kommt erst in den Lichtern dazu.
    """
    import numpy as np
    from PIL import Image

    rampe = klima.get("rampe") or [[0.0, [0, 0, 0]], [1.0, [255, 255, 255]]]
    stellen = np.array([float(s[0]) for s in rampe], dtype=np.float32)
    farben = np.array([s[1] for s in rampe], dtype=np.float32)

    grau = np.asarray(bild.convert("L"), dtype=np.float32) / 255.0
    kanaele = [np.interp(grau, stellen, farben[:, k]) for k in range(3)]
    getont = np.stack(kanaele, axis=-1)

    dunkel = float(klima.get("abdunkeln", 0.0))
    if dunkel:
        getont *= (1.0 - dunkel)

    return Image.fromarray(np.clip(getont, 0, 255).astype("uint8"), "RGB")
