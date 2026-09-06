"""Prueft, welches Angebot zu einem Beitrag findet.

Hier entsteht der Schaden, wenn etwas schiefgeht: ein unpassender Verweis ist
schlimmer als gar keiner, weil er zeigt, dass niemand hingesehen hat.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from media_kit import angebot as A
from media_kit.job import Job


DATEN = {
    "basis": "https://selbstfuehrung.example-echt.at",
    "produkte": {
        "selbsttest": {
            "name": "30 Tage Selbstfuehrung",
            "art": "eigenes",
            "einstieg": "/test",
            "einladung": "Zwoelf Aussagen, zwei Minuten.",
            "bereiche": {
                "grenzen": {"adresse": "/test/grenzen", "frage": "Sagst du Ja und meinst Nein?",
                            "schlagworte": ["nein", "grenze", "gefallen", "zusag"]},
                "handeln": {"adresse": "/test/handeln", "frage": "Weisst du es und tust es nicht?",
                            "schlagworte": ["schieb", "gewohnheit", "vorsatz", "disziplin"]},
                "loslassen": {"adresse": "/test/loslassen", "frage": "Haeltst du fest?",
                              "schlagworte": ["gruebel", "kontroll", "perfekt"]},
            },
        }
    },
}
# Die Prueflisten enthalten "example." - genau das faengt die Platzhaltersperre
# ab. Fuer die Tests muss die Basis also durchkommen.
DATEN["basis"] = "https://selbstfuehrung.test-domain.at"


def auftrag(**abweichung) -> Job:
    grund = dict(id="x", marke="shortheaven3", ausgaben=["karussell"], slides=[])
    grund.update(abweichung)
    return Job(**grund)


# ------------------------------------------------------------------ Zuordnung
def test_das_thema_bestimmt_den_bereich():
    j = auftrag(slides=[{"typ": "haken", "titel": "Du sagst zu oft Ja."},
                        {"typ": "inhalt", "text": "Jede Zusage ist eine Grenze, die du nicht ziehst."}])
    treffer = A.zuordnen(j, DATEN)
    assert treffer.bereich == "grenzen"
    assert treffer.adresse.endswith("/test/grenzen")


def test_ein_anderes_thema_ein_anderer_bereich():
    j = auftrag(slides=[{"typ": "inhalt",
                         "text": "Du schiebst es auf. Der Vorsatz haelt bis Mittwoch."}])
    assert A.zuordnen(j, DATEN).bereich == "handeln"


def test_ein_einzelnes_schlagwort_reicht_nicht():
    """Ein Streiftreffer ist Zufall - dann lieber der allgemeine Einstieg.

    Ein unpassendes Angebot ist schaedlicher als ein allgemeines: es zeigt,
    dass niemand hingesehen hat.
    """
    j = auftrag(slides=[{"typ": "inhalt", "text": "Er sagte nein und ging."}])
    treffer = A.zuordnen(j, DATEN)
    assert treffer.bereich == ""
    assert treffer.adresse.endswith("/test")


def test_ohne_passendes_thema_gibt_es_den_allgemeinen_einstieg():
    j = auftrag(slides=[{"typ": "inhalt", "text": "Ein Beitrag ueber Vogelzug und Wetter."}])
    assert A.zuordnen(j, DATEN).bereich == ""


def test_umlaute_stehen_der_zuordnung_nicht_im_weg():
    # "gruebel" im Schlagwort, "grübeln" im Beitrag - und umgekehrt.
    j = auftrag(slides=[{"typ": "inhalt",
                         "text": "Du grübelst nachts und willst die Kontrolle behalten."}])
    assert A.zuordnen(j, DATEN).bereich == "loslassen"


def test_die_job_datei_ueberstimmt_die_zuordnung():
    j = auftrag(slides=[{"typ": "inhalt", "text": "Du schiebst auf, Vorsatz, Disziplin."}])
    assert A.zuordnen(j, DATEN, bereich="loslassen").bereich == "loslassen"


def test_unbekannter_bereich_wird_benannt():
    with pytest.raises(A.AngebotFehler) as f:
        A.zuordnen(auftrag(), DATEN, bereich="fliegen")
    assert "fliegen" in str(f.value)


# ------------------------------------------------------------------ Adresse
def test_die_slide_zeigt_die_adresse_ohne_schema():
    """Auf einer Slide steht die Adresse zum Abtippen. https:// tippt niemand."""
    j = auftrag(slides=[{"typ": "inhalt", "text": "Zusage, Grenze, nein."}])
    slide = A.zuordnen(j, DATEN).als_slide()
    assert slide["adresse"].startswith("selbstfuehrung")
    assert "://" not in slide["adresse"]


@pytest.mark.parametrize("basis", ["", "https://deine-adresse.at",
                                   "http://localhost:3000", "https://example.com"])
def test_unbrauchbare_basisadressen_werden_abgewiesen(basis):
    """Eine Slide mit falscher Adresse ist schlimmer als keine - sie faellt
    erst auf, wenn der Beitrag schon steht."""
    daten = {**DATEN, "basis": basis}
    with pytest.raises(A.AngebotFehler):
        A.zuordnen(auftrag(), daten)


# ------------------------------------------------------------------- Wunsch
class Marke:
    def __init__(self, an): self.angebot = {"an": an}


def test_die_marke_gibt_vor_der_beitrag_darf_ueberstimmen():
    assert A.gewuenscht(auftrag(), Marke(True)) == (True, "")
    assert A.gewuenscht(auftrag(), Marke(False)) == (False, "")
    # Nicht jeder Beitrag vertraegt einen Verweis.
    assert A.gewuenscht(auftrag(angebot=False), Marke(True)) == (False, "")
    assert A.gewuenscht(auftrag(angebot=True), Marke(False)) == (True, "")
    assert A.gewuenscht(auftrag(angebot="grenzen"), Marke(False)) == (True, "grenzen")


def test_der_nachweis_haelt_fest_worueber_zugeordnet_wurde():
    j = auftrag(slides=[{"typ": "inhalt", "text": "Zusage, Grenze, gefallen."}])
    nachweis = A.zuordnen(j, DATEN).als_nachweis()
    assert nachweis["bereich"] == "grenzen"
    assert "grenze" in nachweis["zugeordnet_ueber"]


def test_trennbare_verben_werden_gefunden():
    """'aufschieben' steht im Satz als 'schiebst es auf'.

    Die Vollform als Schlagwort findet das nie - deshalb stehen in
    produkte.json Wortstaemme. Der Test haelt das fest, weil es beim naechsten
    Ergaenzen der Liste sonst wieder passiert.
    """
    j = auftrag(slides=[{"typ": "inhalt",
                         "text": "Du schiebst es auf. Der Vorsatz haelt bis Mittwoch."}])
    assert A.zuordnen(j, DATEN).bereich == "handeln"
