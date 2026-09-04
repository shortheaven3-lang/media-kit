"""Prueft das Erzeugen der Seite - vor allem, dass Inhalt Inhalt bleibt."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from media_kit import formate, layout, marke


def m():
    return marke.laden("denkbeleg")


def test_erlaubte_auszeichnung_bleibt_erhalten():
    assert layout.sicher("Der Median lag bei <b>66</b> Tagen.") == \
        "Der Median lag bei <b>66</b> Tagen."
    assert "<mark>" in layout.sicher("Die <mark>21 Tage</mark>")


def test_alles_andere_wird_unschaedlich_gemacht():
    # Eine Job-Datei ist Inhalt, keine Programmiersprache. Die Positivliste
    # kann man nicht unterlaufen, eine Negativliste immer.
    boese = layout.sicher("<script>alert(1)</script>")
    assert "<script>" not in boese
    assert "&lt;script&gt;" in boese


def test_bild_mit_ereignis_wird_nicht_zu_html():
    ergebnis = layout.sicher('<img src=x onerror="alert(1)">')
    assert "<img" not in ergebnis


def test_leerzeile_trennt_absaetze():
    assert layout.absaetze("Eins\n\nZwei").count("<p>") == 2
    assert layout.absaetze("Eins\nZwei").count("<p>") == 1


def test_sicherheitszonen_gelten_nur_im_hochformat_mit_ueberlagerung():
    seite_reel = layout.seite({"typ": "haken", "titel": "X"}, 1, 1, m(),
                              formate.hole("reel"), "")
    seite_kar = layout.seite({"typ": "haken", "titel": "X"}, 1, 1, m(),
                             formate.hole("karussell"), "")
    assert "--sicher-oben:140px" in seite_reel
    assert "--sicher-oben:0px" in seite_kar


def test_grundschriftgroesse_skaliert_mit_der_breite():
    # Ein 1600 Pixel breites Titelbild darf nicht mit der Schriftgroesse eines
    # 1080er Karussells gesetzt werden.
    kar = layout.seite({"typ": "haken", "titel": "X"}, 1, 1, m(),
                       formate.hole("karussell"), "")
    titel = layout.seite({"typ": "haken", "titel": "X"}, 1, 1, m(),
                         formate.hole("titelbild"), "")
    assert "font-size:16.0000px" in kar
    assert "font-size:23.7037px" in titel


def test_querformat_bekommt_die_eigene_klasse():
    quer = layout.seite({"typ": "haken", "titel": "X"}, 1, 1, m(),
                        formate.hole("og"), "")
    assert 'class="fmt-og quer' in quer


def test_zaehler_fehlt_bei_einzelbild_und_auf_der_letzten_slide():
    einzeln = layout.seite({"typ": "haken", "titel": "X"}, 1, 1, m(),
                           formate.hole("story"), "")
    letzte = layout.seite({"typ": "ende", "merksatz": "X"}, 7, 7, m(),
                          formate.hole("karussell"), "")
    mitte = layout.seite({"typ": "inhalt", "text": "X"}, 3, 7, m(),
                         formate.hole("karussell"), "")
    assert "zaehler" not in einzeln.split("<body")[1]
    assert "zaehler" not in letzte.split("<body")[1]
    assert "03 / 07" in mitte


def test_textschicht_zeigt_keinen_hintergrund():
    seite = layout.seite({"typ": "haken", "titel": "X"}, 1, 1, m(),
                         formate.hole("reel"), "", schicht="text",
                         hintergrundbild="bilder/x.jpg")
    assert "schicht-text" in seite
    assert "bilder/x.jpg" not in seite    # das Foto darf nicht mit in die Textebene
