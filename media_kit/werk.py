#!/usr/bin/env python3
"""Der Zusammenbau: aus einer Job-Datei werden Dateien.

Die Reihenfolge ist nicht beliebig, sie folgt den Abhaengigkeiten:

  1. Marke laden, Schriften bereitlegen
  2. Hintergrundbilder beschaffen und aufbereiten (falls die Marke Fotos nutzt)
  3. Stimme sprechen - denn erst die Sprechdauer sagt, wie lange eine Slide steht
  4. alle Standbilder aufnehmen, in einem Browserlauf
  5. Musik in genau der Laenge erzeugen, die Schritt 3 und 4 ergeben haben
  6. Video bauen, ein ffmpeg-Aufruf
  7. Nachweis und Bildunterschrift danebenlegen

Schritt 3 vor Schritt 4 ist der Punkt, den man leicht falsch herum baut. Wer
die Standzeiten vorher festlegt, schneidet der Stimme das Wort ab.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import bild, formate, layout, quellen, schriften, ton, video
from .job import Job
from .marke import Marke, laden as marke_laden
from .zwischenlager import Lager, schluessel

WURZEL = Path(__file__).resolve().parent.parent


@dataclass
class Ergebnis:
    job: str
    dateien: list[Path] = field(default_factory=list)
    nachweise: list[dict] = field(default_factory=list)
    aufnahmen: int = 0
    aus_lager: int = 0
    laenge: float = 0.0

    def bericht(self) -> str:
        zeilen = [f"{self.job}: {len(self.dateien)} Datei(en)"]
        for pfad in self.dateien:
            byte = pfad.stat().st_size
            groesse = f"{byte / 1e6:.1f} MB" if byte >= 1e6 else (
                f"{byte / 1024:.0f} kB" if byte >= 1024 else f"{byte} B")
            zeilen.append(f"    {pfad}  ({groesse})")
        gespart = ""
        if self.aus_lager:
            gespart = f", {self.aus_lager} aus dem Zwischenlager"
        zeilen.append(f"    {self.aufnahmen} Aufnahme(n){gespart}")
        if self.laenge:
            zeilen.append(f"    Videolaenge {self.laenge:.1f} s")
        return "\n".join(zeilen)


def _stempel_fuer(job: Job, nummer: int) -> str:
    """Rubrikstempel, nur auf der ersten Slide.

    Fest verdrahtet ist hier nichts: welche Rubrik einen Stempel bekommt, sagt
    die Job-Datei ueber `rubrik`, und ob die Marke ihn ueberhaupt zeigt,
    entscheidet ihre Vorlage (`.stempel{display:none}`).
    """
    if nummer != 1 or not job.rubrik:
        return ""
    return job.rubrik.upper() if job.rubrik.lower() in ("widerlegt", "belegt", "neu") else ""


def _quellbilder(job: Job, lager: Lager, quer: bool,
                 merker: dict) -> list[tuple[Path | None, object]]:
    """Beschafft je Slide die Bildquelle - einmal, nicht einmal je Format.

    Suche und Abruf haengen nicht vom Zielformat ab, nur der Zuschnitt tut das.
    Eine fruehere Fassung rief `beschaffen` in jeder Formatschleife erneut auf
    und suchte damit bei einem Beitrag in vier Formaten viermal dasselbe Bild.

    Faellt ein Abruf aus, steht dort None und die Slide bekommt das Farbfeld der
    Vorlage. Der Lauf bricht nie ab, nur weil eine Bilddatenbank gerade nicht
    antwortet: ein Beitrag ohne Foto ist besser als kein Beitrag.
    """
    ergebnis = []
    for nummer, slide in enumerate(job.slides, start=1):
        angabe = slide.get("bild") or (f"motiv:{slide['motiv']}" if slide.get("motiv") else "")
        if not angabe:
            ergebnis.append((None, None))
            continue
        kennung = (angabe, quer)
        if kennung not in merker:
            try:
                merker[kennung] = quellen.beschaffen(angabe, lager, WURZEL, quer=quer)
            except Exception as fehler:
                print(f"  Slide {nummer}: Hintergrund faellt aus - {fehler}")
                merker[kennung] = (None, None)
        ergebnis.append(merker[kennung])
    return ergebnis


def _hintergruende(job: Job, m: Marke, lager: Lager, breite: int, hoehe: int,
                   merker: dict) -> tuple[list[Path | None], list[dict]]:
    """Je Slide ein auf dieses Format zugeschnittenes Hintergrundbild - oder None."""
    bilder: list[Path | None] = []
    nachweise: list[dict] = []
    for nummer, (quelle, treffer) in enumerate(
            _quellbilder(job, lager, breite > hoehe, merker), start=1):
        if quelle is None:
            bilder.append(None)
            continue
        name = schluessel(str(quelle), breite, hoehe, m.bildklima) + ".jpg"
        fertig = lager.gebaut(
            "bilder", name,
            lambda ziel, q=quelle: quellen.aufbereiten(q, ziel, breite, hoehe, m.bildklima),
        )
        bilder.append(fertig)
        if treffer:
            nachweise.append({"slide": nummer, **treffer.als_nachweis()})
    return bilder, nachweise


def rendern(job: Job, *, ziel: Path, lager: Lager | None = None,
            nur: list[str] | None = None, erzwingen: bool = False,
            arbeit: Path | None = None) -> Ergebnis:
    lager = lager or Lager()
    arbeit = Path(arbeit or (lager.wurzel / "arbeit" / job.id))
    arbeit.mkdir(parents=True, exist_ok=True)
    ziel = Path(ziel) / job.id
    ergebnis = Ergebnis(job=job.id)

    m = marke_laden(job.marke)
    schrift_css = schriften.css(m.schriftdateien, lager.wurzel, arbeit)
    pruef_familien = schriften.geprueft_werden(m.schriftdateien)

    gewuenscht = [a for a in job.ausgaben if not nur or a in nur]
    if not gewuenscht:
        raise SystemExit(f"{job.id}: keine der gewuenschten Ausgaben ({', '.join(nur or [])}) "
                         f"steht im Job. Vorhanden: {', '.join(job.ausgaben)}")

    # ------------------------------------------------- Stimme zuerst (Schritt 3)
    videoformate = [formate.hole(a) for a in gewuenscht if formate.hole(a).ist_video]
    clips = None
    if videoformate and job.will_ton() and job.ton.get("stimme", True):
        saetze = [job.sprechtext(s) for s in job.slides]
        clips = ton.sprechen(saetze, m.ton.get("stimme", "de_DE-thorsten-medium"), lager.wurzel)
    standzeiten = ton.standzeiten(clips, job.anzahl_slides, job.slidedauer())

    alle_nachweise: list[dict] = []
    # Merker fuer schon beschaffte Bildquellen, ueber alle Formate hinweg.
    beschafft: dict = {}

    with bild.Kamera(arbeit, pruef_familien) as kamera:
        for name in gewuenscht:
            f = formate.hole(name)
            hintergruende, nachweise = _hintergruende(job, m, lager, f.breite,
                                                      f.hoehe, beschafft)
            alle_nachweise += [{"format": name, **n} for n in nachweise]
            ordner = ziel / name
            ordner.mkdir(parents=True, exist_ok=True)

            if f.ist_video:
                ergebnis.laenge = _video_bauen(
                    job, m, f, kamera, hintergruende, standzeiten, clips,
                    schrift_css, lager, ordner, ergebnis, erzwingen,
                )
                ergebnis.dateien.append(ordner / f"{job.id}.mp4")
            else:
                ergebnis.dateien += _bilder_bauen(
                    job, m, f, kamera, hintergruende, schrift_css,
                    lager, ordner, ergebnis, erzwingen,
                )
        ergebnis.aufnahmen = kamera.aufnahmen

    _beiwerk(job, m, ziel, alle_nachweise, ergebnis)
    return ergebnis


def _bilder_bauen(job, m, f, kamera, hintergruende, schrift_css,
                  lager, ordner, ergebnis, erzwingen) -> list[Path]:
    """Standbilder. Ein Einzelbildformat nimmt nur die erste Slide."""
    entstanden = []
    slides = job.slides if f.art == "slides" else job.slides[:1]
    for nummer, slide in enumerate(slides, start=1):
        hg = hintergruende[nummer - 1] if nummer - 1 < len(hintergruende) else None
        marker = schluessel(slide, m.quelle, f.name, "voll", str(hg or ""),
                            job.rubrik, m.anzeigename)
        name = (f.dateiname(job.id, nummer if f.art == "slides" else None))
        endgueltig = ordner / name

        def bauen(pfad, slide=slide, nummer=nummer, hg=hg):
            quelltext = layout.seite(
                slide, nummer, len(slides), m, f, schrift_css,
                hintergrundbild=_relativ(hg, kamera.arbeit),
                stempel=_stempel_fuer(job, nummer),
            )
            kamera.aufnehmen(quelltext, f, pfad, name=f"{f.name}-{nummer}")

        gelagert = lager.ablage("seiten", marker + "." + f.endung)
        if erzwingen and gelagert.exists():
            gelagert.unlink()
        vorher = gelagert.exists()
        fertig = lager.gebaut("seiten", marker + "." + f.endung, bauen)
        if vorher:
            ergebnis.aus_lager += 1
        shutil.copyfile(fertig, endgueltig)
        entstanden.append(endgueltig)
    return entstanden


def _video_bauen(job, m, f, kamera, hintergruende, standzeiten, clips,
                 schrift_css, lager, ordner, ergebnis, erzwingen) -> float:
    einstellungen = []
    for nummer, slide in enumerate(job.slides, start=1):
        hg = hintergruende[nummer - 1] if nummer - 1 < len(hintergruende) else None
        grund = schluessel(slide, m.quelle, f.name, str(hg or ""), job.rubrik)

        def hintergrund_bauen(pfad, slide=slide, nummer=nummer, hg=hg):
            kamera.aufnehmen(
                layout.seite(slide, nummer, job.anzahl_slides, m, f, schrift_css,
                             schicht="hintergrund", hintergrundbild=_relativ(hg, kamera.arbeit)),
                f, pfad, skalierung=video.RESERVE, name=f"hg-{nummer}",
            )

        def text_bauen(pfad, slide=slide, nummer=nummer):
            kamera.aufnehmen(
                layout.seite(slide, nummer, job.anzahl_slides, m, f, schrift_css,
                             schicht="text", stempel=_stempel_fuer(job, nummer)),
                f, pfad, transparent=True, name=f"tx-{nummer}",
            )

        for marker, bauer in ((grund + "-hg.png", hintergrund_bauen),
                              (grund + "-tx.png", text_bauen)):
            if erzwingen and lager.ablage("seiten", marker).exists():
                lager.ablage("seiten", marker).unlink()
            elif lager.ablage("seiten", marker).exists():
                ergebnis.aus_lager += 1
            lager.gebaut("seiten", marker, bauer)

        einstellungen.append(video.Einstellung(
            hintergrund=lager.ablage("seiten", grund + "-hg.png"),
            text=lager.ablage("seiten", grund + "-tx.png"),
            dauer=standzeiten[nummer - 1],
            richtung="rein" if nummer % 2 else "raus",
        ))

    laenge = video.gesamtlaenge(einstellungen)
    tonspur = _tonspur(job, m, clips, standzeiten, laenge, lager) if job.will_ton() else None
    video.bauen(einstellungen, ordner / f"{job.id}.mp4", f.breite, f.hoehe, ton=tonspur)
    return laenge


def _tonspur(job, m, clips, standzeiten, laenge: float, lager: Lager) -> Path | None:
    """Musik in exakt der Videolaenge, Stimme an den richtigen Stellen darueber."""
    if not job.ton.get("musik", True) and not clips:
        return None

    stimmungen = m.ton.get("stimmungen", {})
    gewaehlt = job.ton.get("stimmung") or job.rubrik or m.ton.get("standardstimmung", "")
    stimmung = stimmungen.get(gewaehlt) or (
        stimmungen.get(m.ton.get("standardstimmung", "")) or None
    )
    saat = int(schluessel(job.id)[:8], 16) % 100_000

    def bauen(pfad):
        bett = ton.musik(laenge, stimmung, seed=saat)
        if clips:
            # Die Stimme setzt kurz nach dem Bildwechsel ein, damit der Satz
            # nicht in die Ueberblende hineingesprochen wird.
            starts, uhr = [], 0.0
            for dauer in standzeiten:
                starts.append(uhr + 0.25)
                uhr += dauer
            bett = ton.mischen(bett, clips, starts)
        ton.schreiben(pfad, bett)

    name = schluessel(job.id, laenge, standzeiten, bool(clips), stimmung) + ".wav"
    return lager.gebaut("ton", name, bauen)


def _relativ(pfad: Path | None, arbeit: Path) -> str | None:
    """Hintergrundbild neben die HTML-Datei legen und relativ verweisen."""
    if pfad is None:
        return None
    ordner = arbeit / "bilder"
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / pfad.name
    if not ziel.exists() or ziel.stat().st_size != pfad.stat().st_size:
        shutil.copyfile(pfad, ziel)
    return f"bilder/{pfad.name}"


def _beiwerk(job: Job, m: Marke, ziel: Path, nachweise: list[dict],
             ergebnis: Ergebnis) -> None:
    """Bildunterschrift und Lizenznachweis neben die Medien legen."""
    ziel.mkdir(parents=True, exist_ok=True)
    if job.caption:
        (ziel / "caption.txt").write_text(job.caption.rstrip() + "\n", encoding="utf-8")
        ergebnis.dateien.append(ziel / "caption.txt")

    nachweis = {
        "job": job.id,
        "marke": job.marke,
        "termin": job.termin,
        "ausgaben": job.ausgaben,
        "schriften": schriften.lizenzen(m.schriftdateien),
        "stimme": {"modell": m.ton.get("stimme", ""),
                   "lizenz": m.ton.get("stimme_lizenz", "")} if job.will_ton() else None,
        "musik": "im Programm erzeugt, keine fremden Rechte" if job.will_ton() else None,
        "bilder": nachweise,
    }
    (ziel / "nachweis.json").write_text(
        json.dumps({k: v for k, v in nachweis.items() if v not in (None, [], "")},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ergebnis.dateien.append(ziel / "nachweis.json")
    ergebnis.nachweise = nachweise
