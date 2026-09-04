#!/usr/bin/env python3
"""Schreibt web/daten.json aus den Python-Quellen.

Warum erzeugt und nicht von Hand gepflegt: die Oberflaeche braucht dieselben
Formatmasse und Sicherheitszonen wie der Renderkern. Zwei gepflegte Listen
laufen frueher oder spaeter auseinander, und dann zeigt die Vorschau etwas
anderes als die Action liefert. Hier gibt es nur eine Quelle - formate.py und
layout.py - und die Datei daneben ist ihr Abzug.

Wird vom Pages-Workflow vor jeder Veroeffentlichung ausgefuehrt.
"""
import json
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from media_kit import formate, job, layout, marke  # noqa: E402


def daten() -> dict:
    return {
        "_erzeugt_von": "web/daten_erzeugen.py - nicht von Hand aendern",
        "formate": {
            name: {
                "breite": f.breite, "hoehe": f.hoehe, "art": f.art,
                "endung": f.endung, "zweck": f.zweck,
                "sicher": list(layout.SICHERHEIT.get(name, (0, 0))),
            }
            for name, f in ((n, formate.hole(n)) for n in formate.alle_namen())
        },
        "slide_typen": {
            typ: {"pflicht": sorted(pflicht), "erlaubt": sorted(erlaubt)}
            for typ, (pflicht, erlaubt) in job.SLIDE_TYPEN.items()
        },
        "marken": {
            name: {
                "anzeigename": m.anzeigename,
                "vorlage": m.vorlage,
                "farben": m.farben,
                "schriften": m.schriften,
                "standardformate": m.standardformate,
                "abbinder": m.abbinder,
            }
            for name, m in ((n, marke.laden(n)) for n in marke.alle())
        },
    }


if __name__ == "__main__":
    ziel = Path(sys.argv[1]) if len(sys.argv) > 1 else (WURZEL / "web" / "daten.json")
    ziel.write_text(json.dumps(daten(), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"geschrieben: {ziel}")
