"""Prueft Tonspur und Standzeiten - die Teile, die ohne Netz laufen.

Der Piper-Abruf selbst ist hier nicht geprueft: er holt ein Sprachmodell aus
dem Netz. Was geprueft wird, ist alles, was danach damit passiert - Mischung,
Absenkung, Standzeiten -, denn dort steckt die Logik.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from media_kit import ton


def test_musik_hat_genau_die_verlangte_laenge():
    for dauer in (3.0, 7.5, 16.0):
        spur = ton.musik(dauer, seed=1)
        assert spur.shape[1] == 2
        assert spur.shape[0] / ton.SR == pytest.approx(dauer, abs=0.001)


def test_musik_ist_bei_gleichem_seed_reproduzierbar():
    # Sonst klaenge jeder erneute Renderlauf anders und das Zwischenlager
    # waere wertlos.
    assert np.array_equal(ton.musik(4.0, seed=42), ton.musik(4.0, seed=42))


def test_musik_uebersteuert_nicht():
    spur = ton.musik(6.0, seed=3)
    assert np.isfinite(spur).all()
    assert np.abs(spur).max() <= 1.0


def test_tiefpass_daempft_oben_und_laesst_unten_durch():
    t = np.arange(ton.SR).astype(np.float32) / ton.SR
    tief = np.sin(2 * np.pi * 200 * t).astype(np.float32)
    hoch = np.sin(2 * np.pi * 12000 * t).astype(np.float32)
    assert np.abs(ton._tiefpass(tief, 1100)).max() > 0.9
    assert np.abs(ton._tiefpass(hoch, 1100)).max() < 0.05


def test_umtasten_behaelt_die_dauer():
    x = np.sin(2 * np.pi * 440 * np.arange(22050) / 22050).astype(np.float32)
    y = ton._umtasten(x, 22050)
    assert len(y) / ton.SR == pytest.approx(len(x) / 22050, abs=0.001)


def test_standzeiten_ohne_stimme_nehmen_den_vorgabewert():
    assert ton.standzeiten(None, 3, 4.0) == [4.0, 4.0, 4.0]


def test_standzeiten_mit_stimme_richten_sich_nach_der_sprechdauer():
    # Sonst wechselt das Bild mitten im Satz.
    clips = [np.zeros(int(2.0 * ton.SR), np.float32),
             np.zeros(int(5.0 * ton.SR), np.float32)]
    dauern = ton.standzeiten(clips, 2, 4.0)
    assert dauern[1] > dauern[0]
    assert dauern[1] == pytest.approx(5.0 + ton.PAUSE_NACH_SATZ, abs=0.01)


def test_kurze_saetze_fallen_nicht_unter_die_mindeststandzeit():
    clips = [np.zeros(int(0.3 * ton.SR), np.float32)]
    assert ton.standzeiten(clips, 1, 4.0)[0] == ton.MINDESTSTAND


def test_mischen_senkt_die_musik_unter_der_stimme_ab():
    """Ohne Absenkung kaempfen Bordun und Stimme im selben Frequenzbereich."""
    bett = np.ones((ton.SR * 4, 2), np.float32) * 0.5
    rede = np.ones(ton.SR, np.float32) * 0.5          # eine Sekunde Sprache
    misch = ton.mischen(bett, [rede], [1.0])

    # Die Sprachspur wird auf 0,62 Spitze normiert. Was im Mischsignal darueber
    # hinaus steht, ist der verbliebene Musikanteil.
    musik_unter_stimme = float(misch[int(1.4 * ton.SR), 0]) - 0.62
    musik_daneben = float(misch[int(0.2 * ton.SR), 0])

    assert musik_unter_stimme < musik_daneben * 0.6, (
        f"Musik unter der Stimme {musik_unter_stimme:.3f}, "
        f"daneben {musik_daneben:.3f} - zu wenig abgesenkt"
    )
    assert np.abs(misch).max() <= 0.985


def test_die_absenkung_laeuft_weich_an_und_pumpt_nicht():
    """Ein harter Schnitt in der Absenkung waere als Pumpen hoerbar.

    Gemessen wird der Musikanteil, nicht das Mischsignal: das Testsignal fuer
    die Stimme setzt schlagartig ein, und dieser Sprung gehoert zur Stimme,
    nicht zur Huellkurve.
    """
    bett = np.ones((ton.SR * 4, 2), np.float32) * 0.5
    rede = np.ones(ton.SR, np.float32) * 0.5
    spur = ton.mischen(bett, [rede], [1.0])[:, 0]

    # Die Sprachspur liegt nach der Normierung bei genau 0,62 zwischen 1 s und 2 s.
    stimme = np.zeros_like(spur)
    stimme[ton.SR:2 * ton.SR] = 0.62
    musikanteil = spur - stimme

    groesster_sprung = float(np.abs(np.diff(musikanteil)).max())
    assert groesster_sprung < 0.01, f"Sprung von {groesster_sprung:.4f} - das pumpt"

    # Und die Absenkung setzt vor dem ersten Wort ein, nicht erst danach.
    assert musikanteil[int(0.95 * ton.SR)] < musikanteil[int(0.2 * ton.SR)]


# --------------------------------------------------------------- Prosodie
def test_saetze_werden_einzeln_getrennt():
    """Piper erzeugt je Aufruf eine Sprechmelodie. Ein ganzer Absatz bekommt
    davon nur eine - und genau das klingt nach Maschine."""
    teile = ton.saetze_aus("Du bist nicht müde. Du bist unentschieden! Und jetzt?")
    assert teile == ["Du bist nicht müde.", "Du bist unentschieden!", "Und jetzt?"]


def test_leerer_text_ergibt_keine_saetze():
    assert ton.saetze_aus("") == []
    assert ton.saetze_aus("   \n  ") == []


def test_nach_einer_frage_wird_laenger_geschwiegen():
    """Eine Frage will nachhallen, ein Aussagesatz nicht."""
    assert ton._pause_nach("Und jetzt?") > ton._pause_nach("Das war es.")
    assert ton._pause_nach("Dazu drei Punkte:") != ton._pause_nach("Das war es.")


def test_das_tempo_schwankt_aber_bleibt_im_rahmen():
    tempi = [ton._tempo(s) for s in
             ("Ein Satz.", "Noch einer.", "Und ein dritter, laenger diesmal.")]
    assert len(set(tempi)) > 1, "gleichmaessiges Tempo klingt maschinell"
    for t in tempi:
        assert ton.TEMPO_GRUND * 0.9 < t < ton.TEMPO_GRUND * 1.1


def test_das_tempo_ist_ueber_prozessgrenzen_hinweg_gleich():
    """Nicht hash(): Pythons Zeichenketten-Hash ist je Prozess zufaellig
    gesalzen. Derselbe Satz bekaeme dann jedes Mal ein anderes Tempo, das
    Zwischenlager waere wertlos und zwei Renderlaeufe klaengen verschieden."""
    import subprocess
    import sys as _s
    ruf = ('import sys; sys.path.insert(0, %r)\n'
           'from media_kit import ton; print(round(ton._tempo("Ein Satz."), 9))'
           % str(Path(__file__).resolve().parent.parent))
    laeufe = {subprocess.run([_s.executable, "-c", ruf], capture_output=True,
                             text=True, env={"PYTHONHASHSEED": str(n),
                                             "PATH": "/usr/bin:/bin"}).stdout.strip()
              for n in (0, 1, 2)}
    assert len(laeufe) == 1, f"Tempo haengt am Zufall: {laeufe}"
