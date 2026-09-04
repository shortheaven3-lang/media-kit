#!/usr/bin/env python3
"""Aus HTML werden Standbilder. Ein Browser fuer alles.

Der Browserstart ist der teuerste Einzelposten im ganzen Lauf - rund eine
Sekunde, und er kostet mehrere hundert Megabyte. Deshalb wird genau einer
gestartet und alle Slides aller Formate laufen durch dieselbe Seite. Bei einem
Beitrag mit sieben Slides in vier Formaten sind das 28 Aufnahmen und ein
Browserstart statt 28.

Die zweite Sparmassnahme steht in `aufnehmen`: das Ergebnis geht durch das
Zwischenlager. Wer nur die Bildunterschrift aendert, rendert kein Bild neu.
"""
from __future__ import annotations

import os
from pathlib import Path

from .formate import Format


class Kamera:
    """Ein laufender Chromium mit einer Seite. Als Kontext benutzen.

        with Kamera(arbeit) as kamera:
            kamera.aufnehmen(html, format, ziel)
    """

    def __init__(self, arbeit: Path, schriftfamilien: list[str] | None = None):
        self.arbeit = Path(arbeit)
        self.arbeit.mkdir(parents=True, exist_ok=True)
        self.schriftfamilien = schriftfamilien or []
        self._playwright = None
        self._browser = None
        self._seite = None
        self._masse: tuple[int, int, float] | None = None
        self.aufnahmen = 0
        self.uebersprungen = 0

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as fehler:
            raise SystemExit(
                "Playwright fehlt. Installieren mit:\n"
                "    pip install playwright && playwright install --with-deps chromium"
            ) from fehler

        self._playwright = sync_playwright().start()
        # In vorkonfigurierten Umgebungen (Container, CI-Abbilder) liegt oft
        # schon ein Chromium bereit, dessen Bauart nicht zu der von Playwright
        # erwarteten passt. Statt 170 MB nachzuladen, laesst er sich hierueber
        # benennen.
        eigener = os.environ.get("MEDIA_KIT_CHROMIUM")
        self._browser = self._playwright.chromium.launch(
            executable_path=eigener or None,
            args=[
                # Ohne das laeuft Chromium in engen Containern (Actions, Docker)
                # gegen ein zu kleines /dev/shm und stirbt mitten im Lauf.
                "--disable-dev-shm-usage",
                "--font-render-hinting=none",   # gleiches Schriftbild auf jeder Maschine
                "--disable-lcd-text",           # kein Subpixel-Farbsaum auf JPEG
                # Der Renderlauf braucht kein Netz. Ohne diese drei fragt
                # Chromium beim Start nach Komponenten-Aktualisierungen und
                # Sicherheitslisten - in einer abgeschotteten Action laeuft das
                # in Zeitueberschreitungen und kostet Sekunden fuer nichts.
                "--disable-background-networking",
                "--disable-component-update",
                "--no-first-run",
            ]
        )
        return self

    def __exit__(self, *_):
        for teil in (self._browser, self._playwright):
            try:
                teil.close() if teil is self._browser else teil.stop()
            except Exception:
                pass
        return False

    # ------------------------------------------------------------------ intern
    def _seite_fuer(self, breite: int, hoehe: int, skalierung: float):
        """Haelt die Seite; baut sie nur neu, wenn sich die Masse aendern.

        Ein neuer Kontext je Aufnahme waere sauberer zu lesen und kostet rund
        80 ms - bei 28 Aufnahmen also zwei Sekunden fuer nichts.
        """
        masse = (breite, hoehe, skalierung)
        if self._seite is not None and self._masse == masse:
            return self._seite
        if self._seite is not None:
            self._seite.context.close()
        kontext = self._browser.new_context(
            viewport={"width": breite, "height": hoehe},
            device_scale_factor=skalierung,
        )
        self._seite = kontext.new_page()
        self._masse = masse
        return self._seite

    def _schriften_pruefen(self, seite) -> None:
        """Bricht ab, wenn eine Schrift nicht geladen ist.

        Ohne diese Pruefung faellt ein fehlgeschlagener Schriftabruf lautlos auf
        die Systemschrift zurueck. Das Bild ist dann falsch, aber fertig - und
        faellt erst auf, wenn es auf Instagram steht.
        """
        if not self.schriftfamilien:
            return
        # document.fonts.check allein reicht nicht: eine @font-face-Regel, die
        # auf dieser Slide nirgends angewendet wird, laedt der Browser gar nicht
        # erst - check meldet dann "fehlt", obwohl die Datei in Ordnung ist.
        # Erst laden lassen, dann fragen. Eine leere Trefferliste heisst, dass
        # die Familie wirklich nicht da ist.
        fehlend = seite.evaluate(
            """async (familien) => {
                const fehlt = [];
                for (const f of familien) {
                    try {
                        const treffer = await document.fonts.load(`16px "${f}"`);
                        if (!treffer.length) fehlt.push(f);
                    } catch (e) { fehlt.push(f); }
                }
                return fehlt;
            }""",
            self.schriftfamilien,
        )
        if fehlend:
            raise SystemExit(
                "Schrift nicht geladen: " + ", ".join(fehlend)
                + "\nDas Bild waere in der Ersatzschrift gesetzt. Lauf abgebrochen."
            )

    # ------------------------------------------------------------------ oeffentlich
    def aufnehmen(
        self,
        quelltext: str,
        format: Format,
        ziel: Path,
        *,
        skalierung: float = 1.0,
        transparent: bool = False,
        name: str = "seite",
    ) -> Path:
        """Schreibt das HTML, laedt es und legt die Aufnahme unter `ziel` ab."""
        ziel = Path(ziel)
        ziel.parent.mkdir(parents=True, exist_ok=True)

        # Die Datei muss neben den Schriften liegen, sonst greifen die relativen
        # Pfade in den @font-face-Regeln nicht.
        datei = self.arbeit / f"{name}.html"
        datei.write_text(quelltext, encoding="utf-8")

        seite = self._seite_fuer(format.breite, format.hoehe, skalierung)
        seite.goto(datei.as_uri())
        seite.evaluate("() => document.fonts.ready")
        self._schriften_pruefen(seite)

        if ziel.suffix.lower() in (".jpg", ".jpeg"):
            seite.screenshot(path=str(ziel), type="jpeg",
                             quality=format.guete or 88, full_page=False)
        else:
            seite.screenshot(path=str(ziel), type="png",
                             omit_background=transparent, full_page=False)

        self.aufnahmen += 1
        return ziel
