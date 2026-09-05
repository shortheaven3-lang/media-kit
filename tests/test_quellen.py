"""Prueft die Bildquellen, soweit das ohne Netz geht.

Die Abrufe selbst stehen hier nicht - sie brauchen fremde Dienste. Geprueft
wird, was davor und danach passiert: wie Angaben aufgeloest werden, wie
sortiert wird und was aus einem Bild wird. Genau dort sass der Fehler, der
den ersten Probelauf still leer ausgehen liess.
"""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from media_kit import marke, quellen
from media_kit.zwischenlager import Lager


# ------------------------------------------------------------- Ausrichtung
def test_hochformat_wird_bevorzugt_aber_querformat_nicht_verworfen():
    """Der Ausschluss war der Fehler: Commons ist ueberwiegend Querformat.

    Wer Hochformat erzwingt, bekommt fuer die meisten Suchworte gar nichts.
    Sortieren statt filtern - beschneiden kann man immer noch.
    """
    hoch = quellen._abstand(1080, 1920, quer=False)
    quadrat = quellen._abstand(1000, 1000, quer=False)
    quer = quellen._abstand(1920, 1080, quer=False)
    assert hoch < quadrat < quer


def test_querformat_dreht_die_vorliebe_um():
    assert quellen._abstand(1920, 1080, quer=True) < quellen._abstand(1080, 1920, quer=True)


# ---------------------------------------------------------------- Aufloesen
def test_datei_angabe_zeigt_auf_das_repository(tmp_path):
    (tmp_path / "bilder").mkdir()
    eigen = tmp_path / "bilder" / "eigen.jpg"
    Image.new("RGB", (40, 40), (10, 20, 30)).save(eigen)

    pfad, treffer = quellen.beschaffen("datei:bilder/eigen.jpg", Lager(tmp_path / "l"), tmp_path)
    assert pfad == eigen.resolve()
    assert treffer.anbieter == "datei"


def test_fehlende_datei_wird_benannt(tmp_path):
    with pytest.raises(quellen.KeinTreffer) as fehler:
        quellen.beschaffen("datei:gibt-es-nicht.jpg", Lager(tmp_path / "l"), tmp_path)
    assert "gibt-es-nicht.jpg" in str(fehler.value)


def test_leere_angabe_ist_kein_fehler(tmp_path):
    assert quellen.beschaffen("", Lager(tmp_path / "l"), tmp_path) == (None, None)


def test_unverstaendliche_angabe_erklaert_die_erlaubten_formen(tmp_path):
    with pytest.raises(quellen.KeinTreffer) as fehler:
        quellen.beschaffen("irgendwas", Lager(tmp_path / "l"), tmp_path)
    text = str(fehler.value)
    for form in ("datei:", "https", "pexels:", "motiv:"):
        assert form in text


# ------------------------------------------------------------- Aufbereiten
def _foto(tmp_path, breite, hoehe):
    y, x = np.mgrid[0:hoehe, 0:breite]
    roh = np.stack([x / breite * 255, y / hoehe * 255,
                    np.full_like(x, 200)], axis=-1).astype("uint8")
    pfad = tmp_path / "roh.jpg"
    Image.fromarray(roh).save(pfad, quality=95)
    return pfad


def test_querformat_wird_auf_hochformat_beschnitten_nicht_verzerrt(tmp_path):
    quelle = _foto(tmp_path, 1600, 900)
    ziel = quellen.aufbereiten(quelle, tmp_path / "z.jpg", 1080, 1920, {})
    assert Image.open(ziel).size == (1080, 1920)


def test_bildklima_zieht_das_foto_auf_den_markenton(tmp_path):
    quelle = _foto(tmp_path, 1600, 900)
    m = marke.laden("shortheaven3")
    ohne = np.asarray(Image.open(
        quellen.aufbereiten(quelle, tmp_path / "a.jpg", 540, 960, {})))
    mit = np.asarray(Image.open(
        quellen.aufbereiten(quelle, tmp_path / "b.jpg", 540, 960, m.bildklima)))

    # Der Grund der Marke ist blau: nach dem Einfaerben muss Blau ueber Rot
    # liegen, und das Bild insgesamt dunkler sein.
    r, g, b = mit.reshape(-1, 3).mean(0)
    assert b > r, f"nicht ins Markenblau gezogen (R {r:.0f} / B {b:.0f})"
    assert mit.mean() < ohne.mean(), "nicht abgedunkelt"


def test_ohne_bildklima_bleibt_das_foto_wie_es_ist(tmp_path):
    quelle = _foto(tmp_path, 1600, 900)
    m = marke.laden("denkbeleg")
    assert not m.hat_bildklima
    fertig = np.asarray(Image.open(
        quellen.aufbereiten(quelle, tmp_path / "c.jpg", 540, 675, m.bildklima)))
    r, g, b = fertig.reshape(-1, 3).mean(0)
    assert b > 150, "die Vorlage arbeitet ohne Einfaerbung, das Blau muss bleiben"


# ---------------------------------------------------------------- Lizenzen
@pytest.mark.parametrize("lizenz", [
    "CC BY-NC 4.0", "CC BY-NC-SA 3.0", "CC BY-ND 4.0", "cc by-nc-nd 2.0",
])
def test_nc_und_nd_werden_ausgeschlossen(lizenz):
    """Die Konten haben Umsatzabsicht - NC und ND scheiden aus."""
    assert quellen._eingeschraenkt(lizenz)


@pytest.mark.parametrize("lizenz", [
    "CC BY-SA 4.0", "CC0", "Public domain", "CC BY 3.0",
    "Licence Ouverte",              # L-I-C-E-N-C-E enthaelt die Folge "NC"
    "Open Government Licence v3.0",
    "GNU Free Documentation Licence 1.2",
])
def test_freie_lizenzen_bleiben_drin(lizenz):
    """Der Vorlaeufer pruefte auf die blosse Buchstabenfolge und warf damit
    jede Lizenz in britischer oder franzoesischer Schreibweise hinaus."""
    assert not quellen._eingeschraenkt(lizenz), lizenz


# ------------------------------------------------------------ Bildnachweis
def test_nachweis_aus_der_job_datei_ergaenzt_eine_feste_adresse(tmp_path):
    """Eine nackte Adresse weiss nichts ueber Urheber und Lizenz.

    Der vorgesehene Weg ist die feste Adresse, weil sie den Renderlauf
    reproduzierbar macht. Ohne dieses Feld waere er zugleich der Weg, auf dem
    der Nachweis verlorengeht - und das ausgerechnet beim empfohlenen.
    """
    from media_kit.werk import _mit_nachweis

    roh = quellen.Treffer(url="https://images.pexels.com/photos/1/x.jpeg",
                          anbieter="adresse")
    ergaenzt = _mit_nachweis(roh, {
        "anbieter": "pexels", "urheber": "Any Melnic",
        "lizenz": "Pexels-Lizenz", "kennung": "35854894",
    })
    assert ergaenzt.urheber == "Any Melnic"
    assert ergaenzt.anbieter == "pexels"
    assert ergaenzt.url == roh.url, "die Adresse darf nicht ueberschrieben werden"


def test_nachweis_ignoriert_unbekannte_felder(tmp_path):
    from media_kit.werk import _mit_nachweis
    roh = quellen.Treffer(url="https://x/y.jpg", anbieter="adresse")
    ergaenzt = _mit_nachweis(roh, {"urheber": "A", "url": "https://boese/", "quatsch": 1})
    assert ergaenzt.urheber == "A"
    assert ergaenzt.url == "https://x/y.jpg"


def test_ohne_nachweis_bleibt_der_treffer_unveraendert():
    from media_kit.werk import _mit_nachweis
    roh = quellen.Treffer(url="https://x/y.jpg", anbieter="adresse")
    assert _mit_nachweis(roh, None) is roh
    assert _mit_nachweis(None, {"urheber": "A"}) is None
