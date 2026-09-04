"""Prueft das Job-Schema. Ein Tippfehler soll beim Einreichen auffallen,
nicht in der Action."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from media_kit import job as J


def gueltig(**abweichung):
    daten = {
        "id": "2026-09-20-ein-post",
        "marke": "denkbeleg",
        "ausgaben": ["karussell"],
        "slides": [{"typ": "haken", "titel": "Ein Satz."},
                   {"typ": "ende", "merksatz": "Noch einer."}],
    }
    daten.update(abweichung)
    return daten


def test_ein_gueltiger_job_wird_nicht_beanstandet():
    assert J.pruefen(gueltig()) == []


def test_fehlende_pflichtfelder_werden_alle_auf_einmal_gemeldet():
    # Alle, nicht nur das erste: wer eine Datei von Hand schreibt, will nicht
    # fuenfmal rendern, um fuenf Tippfehler zu finden.
    klagen = J.pruefen({})
    assert len(klagen) >= 4
    zusammen = " ".join(klagen)
    for feld in ("id", "marke", "ausgaben", "slides"):
        assert feld in zusammen


def test_id_muss_ein_slug_sein():
    for schlecht in ("Mit Leerzeichen", "Umlaut-ä", "GROSS", "-vorn", "hinten-"):
        assert any("id" in k for k in J.pruefen(gueltig(id=schlecht))), schlecht


def test_unbekanntes_format_faellt_auf():
    klagen = J.pruefen(gueltig(ausgaben=["karusell"]))   # ein L zu wenig
    assert any("karusell" in k for k in klagen)


def test_unbekannter_slide_typ_faellt_auf():
    klagen = J.pruefen(gueltig(slides=[{"typ": "hook", "titel": "x"}]))
    assert any("hook" in k for k in klagen)


def test_unbekanntes_feld_faellt_auf():
    # Sonst verschwindet ein vertippter Feldname stillschweigend im Nichts
    # und die Slide bleibt leer.
    klagen = J.pruefen(gueltig(slides=[{"typ": "haken", "titel": "x", "untertitel": "y"}]))
    assert any("untertitel" in k for k in klagen)


def test_leeres_pflichtfeld_zaehlt_als_fehlend():
    klagen = J.pruefen(gueltig(slides=[{"typ": "haken", "titel": "   "}]))
    assert any("titel" in k for k in klagen)


def test_termin_muss_ein_zeitpunkt_sein():
    assert J.pruefen(gueltig(termin="20.09.2026"))
    assert not J.pruefen(gueltig(termin="2026-09-20T06:30:00+02:00"))


def test_sprechtext_nimmt_sprich_und_wirft_auszeichnung_raus():
    auftrag = J.Job(id="x", marke="m", ausgaben=["reel"], slides=[])
    assert auftrag.sprechtext({"sprich": "So klingt es."}) == "So klingt es."
    gesprochen = auftrag.sprechtext({"text": "Der Median lag bei <b>66 Tagen</b>."})
    assert "<" not in gesprochen and "66 Tagen" in gesprochen


def test_ton_folgt_dem_format_wenn_nichts_gesagt_wird():
    # Ein Video bekommt Ton, ein Karussell nicht - ohne dass es dastehen muss.
    assert J.Job(id="x", marke="m", ausgaben=["reel"], slides=[]).will_ton()
    assert not J.Job(id="x", marke="m", ausgaben=["karussell"], slides=[]).will_ton()
