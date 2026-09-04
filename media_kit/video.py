#!/usr/bin/env python3
"""Aus Standbildern wird ein Video. Ein ffmpeg-Aufruf, kein Frame in Python.

Der Kniff dieses Programms
--------------------------
Der naheliegende Weg, ein Reel zu bauen, ist eine Schleife: fuer jeden der
24 x 30 = 720 Frames ein Bild in Python zeichnen und an ffmpeg schieben. Genau
so macht es der bestehende Autoposter, und es funktioniert - kostet aber pro
Reel einige Minuten CPU und sehr viel Speicher.

Hier laeuft es andersherum. Je Slide entstehen genau zwei Standbilder:

  * die Hintergrundebene, in 1,25-facher Aufloesung (Reserve fuer den Zug)
  * die Textebene, transparent, in Zielaufloesung

Die Bewegung macht ffmpeg: `zoompan` zieht den Hintergrund, `xfade` blendet
zwischen den Slides, `overlay` legt den Text darueber. Fuer ein Reel aus sieben
Slides sind das 14 Aufnahmen statt 720 gezeichneter Frames.

Der zweite, wichtigere Gewinn ist die Bildguete: die Textebene wird nie
skaliert. Beim Frame-fuer-Frame-Weg zoomt der Text mit und wird dabei weich.
Hier zieht nur das Foto darunter, die Schrift steht pixelgenau still.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

FPS = 30
UEBERBLENDE = 0.6       # Sekunden Kreuzblende zwischen zwei Slides
TEXT_AUF = 0.45         # Sekunden, in denen der Text aufblendet
ZUG = 0.10              # 10 % Zoom ueber die Standzeit einer Slide
RESERVE = 1.25          # so viel groesser wird die Hintergrundebene aufgenommen


class KeinFfmpeg(RuntimeError):
    pass


def ffmpeg_pfad() -> str:
    """Systemweites ffmpeg bevorzugt, sonst das Binary aus imageio-ffmpeg.

    In GitHub Actions ist ffmpeg da. Auf einem Rechner ohne ist die Alternative
    ein pip-Paket statt einer Systeminstallation - das erspart sudo und macht
    den Lauf auf jeder Maschine gleich.

    Ausdruecklich nicht genommen wird das ffmpeg, das Playwright mitbringt: es
    ist auf VP8 und WebM zusammengestrichen, kann kein H.264 und keinen der
    Filter, auf denen dieses Programm beruht.
    """
    eigen = os.environ.get("MEDIA_KIT_FFMPEG")
    if eigen:
        return eigen
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as fehler:
        raise KeinFfmpeg(
            "ffmpeg fehlt. Entweder systemweit installieren (apt-get install ffmpeg)\n"
            "oder das mitgelieferte Binary holen: pip install imageio-ffmpeg"
        ) from fehler


@dataclass
class Einstellung:
    """Eine Slide im Video."""
    hintergrund: Path        # PNG/JPG, groesser als das Ziel (siehe RESERVE)
    text: Path | None        # PNG mit Alpha, in Zielaufloesung
    dauer: float             # Standzeit in Sekunden, ohne die Ueberblende
    richtung: str = "rein"   # "rein" zoomt hinein, "raus" heraus


def _zoom_ausdruck(richtung: str, frames: int, zug: float) -> str:
    """Der Zoomverlauf als ffmpeg-Ausdruck.

    Ueber `on` (die Nummer des Ausgabeframes) statt ueber `zoom+0.0005`. Die
    aufaddierende Schreibweise ist verbreitet, verlaesst sich aber darauf, dass
    zoompan den Wert des Vorframes kennt - bei d=1 tut es das nicht zuverlaessig,
    und der Zug wird dann ruckelig oder bleibt stehen. Der Ausdruck ueber `on`
    ist von der Frame-Nummer abhaengig und damit exakt reproduzierbar.
    """
    letzter = max(frames - 1, 1)
    if richtung == "raus":
        return f"{1 + zug:.4f}-{zug:.4f}*on/{letzter}"
    return f"1+{zug:.4f}*on/{letzter}"


def filtergraph(
    einstellungen: list[Einstellung],
    breite: int,
    hoehe: int,
    *,
    fps: int = FPS,
    ueberblende: float = UEBERBLENDE,
    zug: float = ZUG,
    mit_ton: bool = False,
) -> tuple[str, str]:
    """Baut den Filtergraphen. Liefert (Graph, Name des Bildausgangs).

    Als eigene Funktion, damit ein Test den Graphen pruefen kann, ohne ffmpeg
    zu starten. Ein falsch gerechneter Versatz in der xfade-Kette ist der
    Fehler, der hier am ehesten passiert und am schwersten auffaellt - das
    Video ist dann einfach zu kurz und niemand rechnet nach.
    """
    if not einstellungen:
        raise ValueError("Ohne Einstellungen kein Video.")

    teile: list[str] = []
    anzahl = len(einstellungen)

    # Jede Slide muss die Ueberblende zur naechsten mittragen, sonst laeuft
    # xfade in das Ende des Materials und friert das letzte Bild ein.
    for i, e in enumerate(einstellungen):
        laenge = e.dauer + (ueberblende if i < anzahl - 1 else 0.0)
        frames = max(int(round(laenge * fps)), 2)
        z = _zoom_ausdruck(e.richtung, frames, zug)
        teile.append(
            f"[{i}:v]scale={int(breite * RESERVE)}:{int(hoehe * RESERVE)}"
            f":force_original_aspect_ratio=increase,"
            f"crop={int(breite * RESERVE)}:{int(hoehe * RESERVE)},"
            f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s={breite}x{hoehe}:fps={fps},"
            f"format=yuv420p,setsar=1[bg{i}]"
        )

    # Textebenen daruebersetzen. Sie blenden auf und wieder ab, damit die
    # Kreuzblende nicht zwei Saetze gleichzeitig zeigt.
    for i, e in enumerate(einstellungen):
        eingang = f"[bg{i}]"
        if e.text is None:
            teile.append(f"{eingang}null[s{i}]")
            continue
        quelle = anzahl + i
        laenge = e.dauer + (ueberblende if i < anzahl - 1 else 0.0)
        aus_ab = max(laenge - TEXT_AUF, TEXT_AUF)
        teile.append(
            f"[{quelle}:v]format=rgba,"
            f"fade=t=in:st=0:d={TEXT_AUF}:alpha=1,"
            f"fade=t=out:st={aus_ab:.3f}:d={TEXT_AUF}:alpha=1[tx{i}]"
        )
        teile.append(
            f"{eingang}[tx{i}]overlay=0:0:format=auto,format=yuv420p[s{i}]"
        )

    # Kreuzblende. Der Versatz ist kumulativ: jede weitere Slide beginnt um
    # ihre Standzeit spaeter, und die schon verbrauchten Ueberblenden fallen
    # nicht doppelt an.
    if anzahl == 1:
        letzter = "s0"
    else:
        versatz = einstellungen[0].dauer
        letzter = "s0"
        for i in range(1, anzahl):
            ziel = f"x{i}"
            teile.append(
                f"[{letzter}][s{i}]xfade=transition=fade"
                f":duration={ueberblende}:offset={versatz:.3f}[{ziel}]"
            )
            letzter = ziel
            versatz += einstellungen[i].dauer

    teile.append(f"[{letzter}]format=yuv420p[v]")
    return ";".join(teile), "v"


def gesamtlaenge(einstellungen: list[Einstellung],
                 ueberblende: float = UEBERBLENDE) -> float:
    """Wie lang das fertige Video wird: genau die Summe der Standzeiten.

    Nachgerechnet, weil die naheliegende Annahme falsch ist. xfade liefert
    `offset + Laenge des zweiten Eingangs`. Die Kette laeuft also auf
    `Summe der Standzeiten` hinaus - jede Ueberblende wird aus dem Zuschlag
    bestritten, den die vorangehende Slide ohnehin mitbringt, und die letzte
    Slide hat keinen Nachfolger, der noch etwas anhaengt.

    Eine erste Fassung schlug hier eine Ueberblende drauf. Das Video war dann
    real 9,0 Sekunden lang, waehrend die Rechnung 9,6 sagte - und eine daraus
    erzeugte Tonspur haette 0,6 Sekunden ins Leere gespielt. Der Wert steuert
    die Laenge von Stimme und Musik, deshalb steht hier ein Test darauf.
    """
    return sum(e.dauer for e in einstellungen)


def bauen(
    einstellungen: list[Einstellung],
    ziel: Path,
    breite: int,
    hoehe: int,
    *,
    ton: Path | None = None,
    fps: int = FPS,
    ueberblende: float = UEBERBLENDE,
    zug: float = ZUG,
    guete: int = 20,
) -> Path:
    """Ruft ffmpeg genau einmal auf."""
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)

    befehl = [ffmpeg_pfad(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin"]

    # Erst alle Hintergruende, dann alle Textebenen - der Filtergraph rechnet
    # mit genau dieser Reihenfolge.
    for i, e in enumerate(einstellungen):
        laenge = e.dauer + (ueberblende if i < len(einstellungen) - 1 else 0.0)
        befehl += ["-loop", "1", "-t", f"{laenge:.3f}", "-i", str(e.hintergrund)]
    for i, e in enumerate(einstellungen):
        laenge = e.dauer + (ueberblende if i < len(einstellungen) - 1 else 0.0)
        quelle = e.text if e.text is not None else e.hintergrund
        befehl += ["-loop", "1", "-t", f"{laenge:.3f}", "-i", str(quelle)]

    if ton is not None:
        befehl += ["-i", str(ton)]

    graph, ausgang = filtergraph(einstellungen, breite, hoehe, fps=fps,
                                 ueberblende=ueberblende, zug=zug,
                                 mit_ton=ton is not None)
    befehl += ["-filter_complex", graph, "-map", f"[{ausgang}]"]

    if ton is not None:
        befehl += ["-map", f"{2 * len(einstellungen)}:a", "-c:a", "aac", "-b:a", "160k"]

    befehl += [
        "-c:v", "libx264",
        "-preset", "veryfast",   # slower kostet Minuten und spart wenige Prozent
        "-crf", str(guete),
        "-pix_fmt", "yuv420p",   # ohne das spielen aeltere Geraete nichts ab
        "-movflags", "+faststart",
        "-r", str(fps),
        "-t", f"{gesamtlaenge(einstellungen, ueberblende):.3f}",
        str(ziel),
    ]

    lauf = subprocess.run(befehl, capture_output=True, text=True)
    if lauf.returncode != 0 or not ziel.exists():
        raise RuntimeError(
            "ffmpeg ist ausgestiegen.\n"
            + (lauf.stderr or "").strip()[-2000:]
        )
    return ziel
