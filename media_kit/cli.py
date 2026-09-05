#!/usr/bin/env python3
"""Kommandozeile.

    media-kit pruefen  jobs/                 Jobs pruefen, ohne zu rendern
    media-kit rendern  jobs/mein-post.json   alle Ausgaben des Jobs
    media-kit rendern  --alle --nur reel     nur die Reels aller Jobs
    media-kit neu      --marke denkbeleg --id 2026-09-20-testeffekt
    media-kit suchen   "leerer strand" --anbieter wikimedia
    media-kit marken | media-kit formate
    media-kit aufraeumen

`pruefen` vor `rendern` ist kein Ritual: das Rendern kostet einen Browserstart
und, beim Video, einen ffmpeg-Lauf. Ein Tippfehler soll vorher auffallen.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import formate, job as job_modul, marke, quellen, werk
from .zwischenlager import Lager

WURZEL = Path(__file__).resolve().parent.parent


def _jobdateien(angaben: list[str], alle: bool) -> list[Path]:
    if alle:
        return sorted((WURZEL / "jobs").glob("*.json"))
    dateien: list[Path] = []
    for angabe in angaben:
        pfad = Path(angabe)
        if pfad.is_dir():
            dateien += sorted(pfad.glob("*.json"))
        else:
            dateien.append(pfad)
    return dateien


# ------------------------------------------------------------------ Befehle
def befehl_pruefen(args) -> int:
    dateien = _jobdateien(args.jobs, args.alle)
    if not dateien:
        print("Keine Job-Datei angegeben oder gefunden.")
        return 1
    fehler = 0
    for datei in dateien:
        try:
            daten = json.loads(datei.read_text(encoding="utf-8"))
        except json.JSONDecodeError as f:
            print(f"  {datei.name}: kein gueltiges JSON - {f}")
            fehler += 1
            continue
        klagen = job_modul.pruefen(daten, datei.name)
        if klagen:
            fehler += 1
            for klage in klagen:
                print(f"  {klage}")
        else:
            print(f"  {datei.name}: in Ordnung "
                  f"({len(daten['slides'])} Slides -> {', '.join(daten['ausgaben'])})")
    print(f"\n{len(dateien) - fehler} von {len(dateien)} renderbar.")
    return 1 if fehler else 0


def befehl_rendern(args) -> int:
    dateien = _jobdateien(args.jobs, args.alle)
    if not dateien:
        print("Keine Job-Datei angegeben oder gefunden.")
        return 1
    lager = Lager(args.lager)
    ziel = Path(args.ziel)
    schlecht = 0
    for datei in dateien:
        try:
            auftrag = job_modul.laden(datei)
        except job_modul.JobFehler as fehler:
            print(f"{datei.name} uebersprungen:\n{fehler}")
            schlecht += 1
            continue
        print(f"{datei.name} -> {auftrag.marke}, {auftrag.anzahl_slides} Slides")
        try:
            ergebnis = werk.rendern(auftrag, ziel=ziel, lager=lager,
                                    nur=args.nur, erzwingen=args.neu)
        except Exception as fehler:
            print(f"  ausgestiegen: {type(fehler).__name__}: {fehler}")
            schlecht += 1
            continue
        print(ergebnis.bericht())
    return 1 if schlecht else 0


def befehl_neu(args) -> int:
    m = marke.laden(args.marke)
    ausgaben = args.format or m.standardformate
    geruest = {
        "id": args.id,
        "marke": args.marke,
        "rubrik": "",
        "termin": "",
        "ausgaben": list(ausgaben),
        "slides": [
            {"typ": "haken", "titel": "Der Satz, der zum Anhalten bringt.",
             "unterzeile": "Eine Zeile, die ihn schaerft."},
            {"typ": "inhalt", "kopf": "Worum es geht",
             "text": "Ein Absatz.\n\nEin zweiter, durch eine Leerzeile getrennt.",
             "quelle": ""},
            {"typ": "ende", "merksatz": "Der Satz, der haengen bleibt."},
        ],
        "caption": "",
        "ton": {"stimme": True, "musik": True},
        "video": {"slidedauer": 4.0},
    }
    ziel = Path(args.ziel or (WURZEL / "jobs")) / f"{args.id}.json"
    if ziel.exists() and not args.ueberschreiben:
        print(f"{ziel} gibt es schon. Mit --ueberschreiben erzwingen.")
        return 1
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(geruest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"Angelegt: {ziel}")
    print(f"Formate:  {', '.join(ausgaben)}")
    return 0


def befehl_suchen(args) -> int:
    treffer = quellen.suchen(args.begriff, args.anbieter, args.anzahl, args.quer)
    if not treffer:
        print("Nichts gefunden. Ohne PEXELS_API_KEY und PIXABAY_API_KEY bleibt nur "
              "Wikimedia Commons - und das braucht andere Suchworte (englisch, sachlich).\n"
              "Ein Schluessel ist aber nur zum Suchen noetig: wer ein Bild anderswo "
              "aussucht, traegt dessen Adresse einfach als \"bild\" ein. Heruntergeladen "
              "wird sie ohne jedes Zugangsdatum.")
        return 1
    for t in treffer:
        print(f"\n  {t.anbieter}:{t.kennung}")
        print(f"    {t.url}")
        if t.urheber:
            print(f"    {t.urheber} - {t.lizenz}")
        if t.fundstelle:
            print(f"    {t.fundstelle}")

    erster = treffer[0]
    print("\nDie gewaehlte Adresse gehoert als \"bild\" in die Slide, der Rest als"
          "\n\"bildnachweis\" daneben - sonst steht am Ende kein Urheber im Nachweis:\n")
    print(json.dumps({
        "bild": erster.url,
        "bildnachweis": {k: v for k, v in
                         (("anbieter", erster.anbieter), ("kennung", erster.kennung),
                          ("urheber", erster.urheber), ("lizenz", erster.lizenz),
                          ("fundstelle", erster.fundstelle)) if v},
    }, ensure_ascii=False, indent=2))
    return 0


def befehl_marken(_args) -> int:
    for name in marke.alle():
        m = marke.laden(name)
        print(f"  {name:16} {m.anzeigename:16} Vorlage {m.vorlage:12} "
              f"-> {', '.join(m.standardformate)}")
    return 0


def befehl_formate(_args) -> int:
    for name in formate.alle_namen():
        f = formate.hole(name)
        print(f"  {name:12} {f.breite:>5} x {f.hoehe:<5} {f.art:8} .{f.endung}")
        print(f"               {f.zweck}")
    return 0


def befehl_aufraeumen(args) -> int:
    lager = Lager(args.lager)
    vorher = lager.groesse()
    frei = lager.leeren(args.abteilung)
    print(f"Zwischenlager: {vorher / 1e6:.1f} MB -> {(vorher - frei) / 1e6:.1f} MB "
          f"({frei / 1e6:.1f} MB frei)")
    return 0


# ------------------------------------------------------------------- Aufbau
def bauen() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="media-kit",
        description="Medien fuer Social Media aus einer Job-Datei.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    unter = p.add_subparsers(dest="befehl", required=True)

    def mit_jobs(sp):
        sp.add_argument("jobs", nargs="*", help="Job-Dateien oder ein Ordner")
        sp.add_argument("--alle", action="store_true", help="alle Jobs unter jobs/")
        return sp

    pr = mit_jobs(unter.add_parser("pruefen", help="Jobs pruefen, ohne zu rendern"))
    pr.set_defaults(funktion=befehl_pruefen)

    re = mit_jobs(unter.add_parser("rendern", help="Medien erzeugen"))
    re.add_argument("--nur", nargs="+", metavar="FORMAT",
                    help=f"nur diese Formate ({', '.join(formate.alle_namen())})")
    re.add_argument("--ziel", default="ergebnisse", help="Ausgabeordner")
    re.add_argument("--lager", default=None, help="Ordner des Zwischenlagers")
    re.add_argument("--neu", action="store_true",
                    help="Zwischenlager uebergehen und alles neu aufnehmen")
    re.set_defaults(funktion=befehl_rendern)

    ne = unter.add_parser("neu", help="Geruest fuer einen Job anlegen")
    ne.add_argument("--marke", required=True)
    ne.add_argument("--id", required=True, help="z.B. 2026-09-20-testeffekt")
    ne.add_argument("--format", nargs="+", metavar="FORMAT")
    ne.add_argument("--ziel", default=None)
    ne.add_argument("--ueberschreiben", action="store_true")
    ne.set_defaults(funktion=befehl_neu)

    su = unter.add_parser("suchen", help="freie Bilder suchen")
    su.add_argument("begriff")
    su.add_argument("--anbieter", default="",
                    choices=[""] + sorted(quellen.ANBIETER), help="sonst der Reihe nach")
    su.add_argument("--anzahl", type=int, default=5)
    su.add_argument("--quer", action="store_true", help="Querformat statt Hochformat")
    su.set_defaults(funktion=befehl_suchen)

    unter.add_parser("marken", help="vorhandene Marken").set_defaults(funktion=befehl_marken)
    unter.add_parser("formate", help="vorhandene Formate").set_defaults(funktion=befehl_formate)

    au = unter.add_parser("aufraeumen", help="Zwischenlager leeren")
    au.add_argument("--abteilung", default=None,
                    help="nur eine Abteilung, z.B. seiten")
    au.add_argument("--lager", default=None)
    au.set_defaults(funktion=befehl_aufraeumen)

    return p


def haupt(argumente: list[str] | None = None) -> int:
    args = bauen().parse_args(argumente)
    return args.funktion(args)


if __name__ == "__main__":
    sys.exit(haupt())
