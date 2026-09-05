#!/usr/bin/env python3
"""Der Job: was gemacht werden soll, nicht wie.

Ein Job beschreibt einen Beitrag inhaltlich - Marke, Slides, Text, Ton. Welche
Dateien daraus entstehen, entscheidet die Liste unter "ausgaben". Derselbe Job
liefert so das Karussell fuer Instagram und das Vorschaubild fuer die WebApp,
ohne dass der Text zweimal irgendwo steht.

Die Pruefung ist bewusst streng und laeuft vor jedem Rendern. Ein Tippfehler im
Slide-Typ soll beim Einreichen auffallen und nicht dadurch, dass in der Action
eine leere Slide herauskommt.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import formate

# Welche Felder ein Slide-Typ braucht und welche er kennt.
# "bildnachweis" gehoert ueberall dazu, wo ein Bild stehen darf: wer eine feste
# Adresse eintraegt, statt suchen zu lassen, bekommt sonst keinen Nachweis - die
# Suche liefert Urheber und Lizenz mit, eine nackte Adresse nicht.
_BILD = {"bild", "motiv", "bildnachweis"}

SLIDE_TYPEN: dict[str, tuple[set[str], set[str]]] = {
    # typ:          (pflicht,                 zusaetzlich erlaubt)
    "haken":  ({"titel"},    {"unterzeile"} | _BILD),
    "inhalt": ({"text"},     {"kopf", "quelle"} | _BILD),
    "zitat":  ({"text"},     {"herkunft"} | _BILD),
    "frage":  ({"text"},     {"kopf"} | _BILD),
    "ende":   ({"merksatz"}, {"abbinder"} | _BILD),
}

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class JobFehler(ValueError):
    """Ein Job ist nicht renderbar. Die Meldung nennt Datei und Stelle."""


@dataclass
class Job:
    id: str
    marke: str
    slides: list[dict]
    ausgaben: list[str]
    caption: str = ""
    rubrik: str = ""
    termin: str = ""
    ton: dict = field(default_factory=dict)
    video: dict = field(default_factory=dict)
    notiz: str = ""
    quelle: Path | None = None

    # ------------------------------------------------------------- Bequemes
    @property
    def anzahl_slides(self) -> int:
        return len(self.slides)

    def formate(self) -> list[formate.Format]:
        return [formate.hole(name) for name in self.ausgaben]

    def will_ton(self) -> bool:
        """Ohne ausdrueckliche Angabe bekommt ein Video Ton, ein Bild nicht."""
        if "stimme" in self.ton or "musik" in self.ton:
            return bool(self.ton.get("stimme", True)) or bool(self.ton.get("musik", True))
        return any(formate.hole(a).ist_video for a in self.ausgaben)

    def slidedauer(self) -> float:
        """Sekunden je Slide im Video, wenn keine Stimme die Laenge vorgibt."""
        return float(self.video.get("slidedauer", 4.0))

    def sprechtext(self, slide: dict) -> str:
        """Was vorgelesen wird. Ausdrueckliches "sprich" schlaegt den Slide-Text.

        Der Grund fuer das eigene Feld: auf der Slide steht oft eine Zahl als
        Zeichen ("66 Tage"), vorgelesen klingt aber ein Satz besser. Und
        Auszeichnungen wie <b> sollen nicht mitgesprochen werden.
        """
        wenn_gesetzt = slide.get("sprich")
        if wenn_gesetzt is not None:
            return str(wenn_gesetzt).strip()
        roh = " ".join(
            str(slide.get(feld, ""))
            for feld in ("titel", "kopf", "text", "merksatz")
            if slide.get(feld)
        )
        return ohne_auszeichnung(roh)

    def als_json(self) -> str:
        daten = {
            "id": self.id, "marke": self.marke, "rubrik": self.rubrik,
            "termin": self.termin, "ausgaben": self.ausgaben,
            "slides": self.slides, "caption": self.caption,
            "ton": self.ton, "video": self.video, "notiz": self.notiz,
        }
        return json.dumps({k: v for k, v in daten.items() if v not in ("", {}, [])},
                          ensure_ascii=False, indent=2)


def ohne_auszeichnung(text: str) -> str:
    """HTML-Auszeichnung raus, damit die Stimme keine spitzen Klammern liest."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "und")
    return re.sub(r"\s+", " ", text).strip()


# ------------------------------------------------------------------ Pruefung
def pruefen(daten: dict, herkunft: str = "<unbekannt>") -> list[str]:
    """Liefert alle Beanstandungen. Leere Liste heisst: renderbar.

    Bewusst alle statt der ersten: wer eine Datei von Hand schreibt, will nicht
    fuenfmal rendern, um fuenf Tippfehler zu finden.
    """
    klagen: list[str] = []
    an = lambda t: klagen.append(f"{herkunft}: {t}")

    kennung = daten.get("id")
    if not kennung:
        an("es fehlt 'id'")
    elif not SLUG.match(str(kennung)):
        an(f"'id' muss klein, ohne Umlaute und mit Bindestrichen sein, ist aber {kennung!r}")

    if not daten.get("marke"):
        an("es fehlt 'marke'")

    ausgaben = daten.get("ausgaben") or []
    if not isinstance(ausgaben, list) or not ausgaben:
        an("'ausgaben' muss eine nicht leere Liste sein, z.B. [\"karussell\"]")
    else:
        for name in ausgaben:
            if name not in formate.FORMATE:
                an(f"unbekanntes Format {name!r}; bekannt: {', '.join(formate.alle_namen())}")

    slides = daten.get("slides")
    if not isinstance(slides, list) or not slides:
        an("'slides' muss eine nicht leere Liste sein")
    else:
        for nummer, slide in enumerate(slides, start=1):
            klagen += _slide_pruefen(slide, nummer, herkunft)

    termin = daten.get("termin")
    if termin:
        try:
            datetime.fromisoformat(str(termin))
        except ValueError:
            an(f"'termin' ist kein ISO-Zeitpunkt: {termin!r} (erwartet 2026-09-12T06:30:00+02:00)")

    video = daten.get("video") or {}
    if video:
        dauer = video.get("slidedauer")
        if dauer is not None and not (0.5 <= float(dauer) <= 30):
            an(f"'video.slidedauer' liegt bei {dauer}; sinnvoll sind 0,5 bis 30 Sekunden")

    return klagen


def _slide_pruefen(slide, nummer: int, herkunft: str) -> list[str]:
    ort = f"{herkunft}: Slide {nummer}"
    if not isinstance(slide, dict):
        return [f"{ort} ist kein Objekt"]

    typ = slide.get("typ", "inhalt")
    if typ not in SLIDE_TYPEN:
        return [f"{ort}: unbekannter Typ {typ!r}; bekannt: {', '.join(sorted(SLIDE_TYPEN))}"]

    pflicht, erlaubt = SLIDE_TYPEN[typ]
    allgemein = {"typ", "sprich", "dauer"}
    klagen = []
    for feld in sorted(pflicht - set(slide)):
        klagen.append(f"{ort} ({typ}): es fehlt {feld!r}")
    for feld in sorted(set(slide) - pflicht - erlaubt - allgemein):
        klagen.append(f"{ort} ({typ}): unbekanntes Feld {feld!r}")
    for feld in sorted(pflicht & set(slide)):
        if not str(slide[feld]).strip():
            klagen.append(f"{ort} ({typ}): {feld!r} ist leer")
    return klagen


def laden(pfad: str | Path) -> Job:
    pfad = Path(pfad)
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as fehler:
        raise JobFehler(f"{pfad.name}: kein gueltiges JSON - {fehler}") from fehler

    klagen = pruefen(daten, pfad.name)
    if klagen:
        raise JobFehler("\n".join(klagen))

    return Job(
        id=daten["id"],
        marke=daten["marke"],
        slides=daten["slides"],
        ausgaben=daten["ausgaben"],
        caption=daten.get("caption", ""),
        rubrik=daten.get("rubrik", ""),
        termin=daten.get("termin", ""),
        ton=daten.get("ton", {}),
        video=daten.get("video", {}),
        notiz=daten.get("notiz", ""),
        quelle=pfad,
    )
