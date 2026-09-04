"""Prueft den Filtergraphen - und die Laengenrechnung an echtem ffmpeg.

Der Test auf die Gesamtlaenge steht hier, weil genau dort ein Fehler war: die
erste Fassung schlug eine Ueberblende auf die Summe der Standzeiten. Das Video
war real 9,0 Sekunden lang, die Rechnung sagte 9,6, und eine daraus erzeugte
Tonspur haette ins Leere gespielt. So etwas faellt ohne Nachmessen nicht auf -
das Video sieht ja richtig aus.
"""
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from media_kit import video


def _png(pfad: Path, breite: int, hoehe: int, farbe=(30, 40, 60)) -> Path:
    """Ein einfarbiges PNG, ohne Pillow - der Test soll ohne Extras laufen."""
    roh = b"".join(b"\x00" + bytes(farbe) * breite for _ in range(hoehe))

    def block(art, daten):
        return (struct.pack(">I", len(daten)) + art + daten
                + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF))

    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + block(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 2, 0, 0, 0))
        + block(b"IDAT", zlib.compress(roh))
        + block(b"IEND", b"")
    )
    return pfad


def _einstellungen(dauern):
    return [video.Einstellung(hintergrund=Path("hg.png"), text=Path("tx.png"), dauer=d)
            for d in dauern]


# ------------------------------------------------------------------ Rechnung
def test_gesamtlaenge_ist_die_summe_der_standzeiten():
    assert video.gesamtlaenge(_einstellungen([3.0, 3.0, 3.0])) == pytest.approx(9.0)
    assert video.gesamtlaenge(_einstellungen([4.0])) == pytest.approx(4.0)


def test_gesamtlaenge_haengt_nicht_an_der_ueberblende():
    # Weil jede Ueberblende aus dem Zuschlag der vorangehenden Slide bestritten
    # wird. Eine laengere Blende macht das Video nicht laenger, nur weicher.
    einst = _einstellungen([3.0, 3.0])
    assert (video.gesamtlaenge(einst, ueberblende=0.2)
            == video.gesamtlaenge(einst, ueberblende=1.2))


# --------------------------------------------------------------- Filtergraph
def test_graph_hat_je_slide_eine_hintergrund_und_eine_textebene():
    graph, ausgang = video.filtergraph(_einstellungen([2.0, 2.0, 2.0]), 1080, 1920)
    assert ausgang == "v"
    for i in range(3):
        assert f"[bg{i}]" in graph
        assert f"[tx{i}]" in graph
        assert f"[s{i}]" in graph


def test_versatz_der_ueberblenden_waechst_kumulativ():
    graph, _ = video.filtergraph(_einstellungen([3.0, 4.0, 5.0]), 1080, 1920,
                                 ueberblende=0.6)
    # Erste Blende nach 3 s, zweite nach 3+4 = 7 s.
    assert "offset=3.000" in graph
    assert "offset=7.000" in graph


def test_ohne_textebene_bleibt_der_hintergrund_stehen():
    einst = [video.Einstellung(hintergrund=Path("a.png"), text=None, dauer=2.0)]
    graph, _ = video.filtergraph(einst, 1080, 1920)
    assert "[bg0]null[s0]" in graph
    assert "overlay" not in graph


def test_zoom_laeuft_ueber_die_framenummer_nicht_ueber_akkumulation():
    # zoom+0.0005 ist die verbreitete Schreibweise, verlaesst sich aber auf den
    # Wert des Vorframes. Bei d=1 kennt zoompan den nicht zuverlaessig, und der
    # Zug bleibt stehen oder ruckelt.
    graph, _ = video.filtergraph(_einstellungen([2.0]), 1080, 1920)
    assert "on/" in graph
    assert "zoom+" not in graph


def test_leere_liste_wird_abgelehnt():
    with pytest.raises(ValueError):
        video.filtergraph([], 1080, 1920)


# ------------------------------------------------------- gegen echtes ffmpeg
def _ffmpeg_da():
    try:
        video.ffmpeg_pfad()
        return True
    except video.KeinFfmpeg:
        return False


@pytest.mark.skipif(not _ffmpeg_da(), reason="ffmpeg fehlt")
def test_gebautes_video_ist_so_lang_wie_berechnet(tmp_path):
    hg = _png(tmp_path / "hg.png", 320, 568, (30, 40, 60))
    tx = _png(tmp_path / "tx.png", 256, 456, (200, 180, 150))
    einst = [video.Einstellung(hg, tx, dauer=d) for d in (1.5, 2.0, 1.0)]

    ziel = video.bauen(einst, tmp_path / "p.mp4", 256, 456, fps=15)
    assert ziel.exists()

    lauf = subprocess.run(
        [video.ffmpeg_pfad(), "-hide_banner", "-i", str(ziel)],
        capture_output=True, text=True,
    )
    zeile = next(z for z in lauf.stderr.splitlines() if "Duration" in z)
    zeit = zeile.split("Duration:")[1].split(",")[0].strip()
    st, mi, se = zeit.split(":")
    gemessen = int(st) * 3600 + int(mi) * 60 + float(se)

    erwartet = video.gesamtlaenge(einst)          # 4.5
    assert gemessen == pytest.approx(erwartet, abs=0.15), (
        f"berechnet {erwartet} s, gemessen {gemessen} s"
    )
