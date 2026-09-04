"""Prueft das Zwischenlager - den Hebel fuer die Ressourcenfrage."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from media_kit.zwischenlager import Lager, schluessel


def test_gleiche_eingabe_gleicher_schluessel():
    assert schluessel({"a": 1, "b": 2}) == schluessel({"a": 1, "b": 2})


def test_reihenfolge_im_woerterbuch_aendert_den_schluessel_nicht():
    # Sonst waere der Cache nach einem Umsortieren der Job-Datei wertlos.
    assert schluessel({"a": 1, "b": 2}) == schluessel({"b": 2, "a": 1})


def test_andere_eingabe_anderer_schluessel():
    assert schluessel({"a": 1}) != schluessel({"a": 2})
    assert schluessel("x", 1) != schluessel("x", 2)


def test_gebaut_ruft_den_bauer_nur_beim_ersten_mal(tmp_path):
    lager = Lager(tmp_path)
    laeufe = []

    def bauer(ziel):
        laeufe.append(1)
        ziel.write_bytes(b"inhalt")

    erst = lager.gebaut("seiten", "a.png", bauer)
    zweit = lager.gebaut("seiten", "a.png", bauer)
    assert erst == zweit
    assert len(laeufe) == 1, "Der zweite Aufruf haette nichts bauen duerfen"


def test_ein_abgebrochener_bau_hinterlaesst_nichts(tmp_path):
    """Der unangenehmste Cache-Fehler: eine halbe Datei, die als fertig gilt.

    Sie tarnt sich als kaputtes Ergebnis statt als Fehler - deshalb wird ueber
    eine Nebendatei gebaut und erst danach umbenannt.
    """
    lager = Lager(tmp_path)

    def scheitert(ziel):
        ziel.write_bytes(b"halb")
        raise RuntimeError("mittendrin abgebrochen")

    with pytest.raises(RuntimeError):
        lager.gebaut("seiten", "b.png", scheitert)
    assert not lager.ablage("seiten", "b.png").exists()

    # Und danach laesst sich sauber neu bauen.
    fertig = lager.gebaut("seiten", "b.png", lambda z: z.write_bytes(b"ganz"))
    assert fertig.read_bytes() == b"ganz"


def test_ein_bauer_der_nichts_erzeugt_gilt_als_fehler(tmp_path):
    lager = Lager(tmp_path)
    with pytest.raises(RuntimeError):
        lager.gebaut("seiten", "c.png", lambda z: None)


def test_leeren_gibt_platz_frei(tmp_path):
    lager = Lager(tmp_path)
    lager.gebaut("seiten", "d.png", lambda z: z.write_bytes(b"x" * 5000))
    assert lager.groesse() >= 5000
    frei = lager.leeren()
    assert frei >= 5000
    assert lager.groesse() == 0
