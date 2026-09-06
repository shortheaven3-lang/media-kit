"""Aufraeumen des Ausgabeordners.

Der Ordner wird beim Rendern nur angelegt, nie geleert. Ohne das Aufraeumen
bleibt beim Schrumpfen eines Karussells die hoechste Nummer liegen - eine
Datei, die aussieht wie ein gueltiges Bild, mit eingecheckt wird und beim
Hochladen im Beitrag landet.
"""

from media_kit.werk import Ergebnis, _altlasten_raeumen


def _lege_an(ordner, *namen):
    ordner.mkdir(parents=True, exist_ok=True)
    dateien = []
    for name in namen:
        pfad = ordner / name
        pfad.write_bytes(b"x")
        dateien.append(pfad)
    return dateien


def test_uebrige_datei_wird_entfernt(tmp_path):
    ordner = tmp_path / "karussell"
    _lege_an(ordner, "01.jpg", "02.jpg", "03.jpg")
    gebaut = [ordner / "01.jpg", ordner / "02.jpg"]

    ergebnis = Ergebnis(job="probe")
    _altlasten_raeumen(ordner, gebaut, ergebnis)

    assert sorted(p.name for p in ordner.iterdir()) == ["01.jpg", "02.jpg"]
    assert any("03.jpg" in h for h in ergebnis.hinweise)


def test_gebaute_dateien_bleiben_unangetastet(tmp_path):
    ordner = tmp_path / "karussell"
    gebaut = _lege_an(ordner, "01.jpg", "02.jpg")

    ergebnis = Ergebnis(job="probe")
    _altlasten_raeumen(ordner, gebaut, ergebnis)

    assert sorted(p.name for p in ordner.iterdir()) == ["01.jpg", "02.jpg"]
    assert ergebnis.hinweise == []


def test_video_ordner_behaelt_nur_den_film(tmp_path):
    ordner = tmp_path / "reel"
    _lege_an(ordner, "probe.mp4", "probe.mp4.teil")
    gebaut = [ordner / "probe.mp4"]

    ergebnis = Ergebnis(job="probe")
    _altlasten_raeumen(ordner, gebaut, ergebnis)

    assert [p.name for p in ordner.iterdir()] == ["probe.mp4"]


def test_unterordner_bleiben_stehen(tmp_path):
    # Nur Dateien werden geraeumt. Ein Unterordner ist nie ein Ueberbleibsel
    # des Renderers, und ihn zu loeschen waere nicht mehr rueckgaengig zu machen.
    ordner = tmp_path / "karussell"
    _lege_an(ordner, "01.jpg")
    (ordner / "roh").mkdir()

    ergebnis = Ergebnis(job="probe")
    _altlasten_raeumen(ordner, [ordner / "01.jpg"], ergebnis)

    assert (ordner / "roh").is_dir()


def test_bericht_nennt_das_weggeraeumte(tmp_path):
    # Eine still geloeschte Datei sieht im Nachhinein wie ein Fehler aus.
    ordner = tmp_path / "karussell"
    _lege_an(ordner, "01.jpg", "05.jpg")

    ergebnis = Ergebnis(job="probe")
    _altlasten_raeumen(ordner, [ordner / "01.jpg"], ergebnis)
    ergebnis.dateien = [ordner / "01.jpg"]

    assert "05.jpg" in ergebnis.bericht()
