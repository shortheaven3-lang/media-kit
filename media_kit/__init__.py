"""media-kit - Medien fuer Social Media aus einer Job-Datei.

Der Weg durch das Paket:

    job.py          liest und prueft, was gemacht werden soll
    marke.py        sagt, wie es aussehen soll
    layout.py       baut daraus HTML
    bild.py         macht aus HTML Standbilder (ein Browser fuer alles)
    video.py        macht aus Standbildern ein Video (ein ffmpeg-Aufruf)
    ton.py          Stimme und Musik
    quellen.py      freie Bilder, mit Lizenznachweis
    zwischenlager.py haelt fest, was schon gebaut wurde
    werk.py         setzt das zusammen
"""

__version__ = "1.0.0"
