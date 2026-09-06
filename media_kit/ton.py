#!/usr/bin/env python3
"""Stimme und Musik. Beides ohne Konto, ohne Schluessel, ohne Kontingent.

Warum selbst erzeugt statt zugekauft
------------------------------------
Ein Beitrag, der morgens um halb sechs am Kontingent eines Anbieters scheitert,
ist ein ausgefallener Beitrag. Deshalb gilt hier fuer beides dieselbe Regel:

  Stimme  Piper, quelloffen (MIT), Sprachmodell `de_DE-thorsten-medium` aus dem
          Thorsten-Voice-Datensatz unter CC0 - der Sprecher hat seine Stimme
          ausdruecklich freigegeben, also auch fuer kommerzielle Nutzung.
          Geprueft und verworfen: ElevenLabs, HeyGen, LMNT, Typecast (Konto und
          monatliches Freikontingent) sowie edge-tts (spricht ueber einen
          undokumentierten Microsoft-Endpunkt - jederzeit abschaltbar und fuer
          ein Konto mit Umsatzabsicht eine Grauzone).

  Musik   hier erzeugt, aus Sinusschichten, Rauschen und Hall. Kein fremdes
          Recht im Spiel, und Instagrams Tonerkennung findet nichts zum
          Anschlagen.

Nichts zweimal sprechen
-----------------------
Piper ist nicht deterministisch. Das VITS-Modell wuerfelt die Silbenlaengen
(stochastic duration predictor), derselbe Satz kommt bei jedem Aufruf ein paar
Hundertstel laenger oder kuerzer heraus. Hoerbar ist das nicht - aber es
verschiebt die Standzeiten der Slides, damit die Videolaenge und damit die
ganze Datei. Ein unveraenderter Beitrag wurde so bei jedem Lauf neu geschnitten
und mit rund 6 MB neu eingecheckt, und zwei Fassungen desselben Reels waren nie
gleich lang.

Deshalb liegt jeder gesprochene Satz im Zwischenlager, und zwar als das WAV,
das Piper geliefert hat - vor Umtasten, Pausen und Mischung. Aus derselben
Eingabe kommt seitdem dieselbe Datei heraus. Ein Lauf ohne Textaenderung
spricht keinen Satz mehr und laedt nicht einmal das Sprachmodell.

Ohne scipy
----------
Der Vorlaeufer im Autoposter benutzte scipy fuer vier Filteraufrufe. scipy
bringt rund 40 MB mit, die in jedem Actions-Lauf neu installiert werden. Die
vier Aufrufe sind hier mit numpy nachgebaut: Tiefpass und Hall laufen ueber die
FFT statt ueber ein rekursives Filter. Das ist nicht nur kleiner, es ist auch
phasenfrei - eine Butterworth-Kaskade verschiebt tiefe Anteile gegen hohe, was
man einem Bordun bei genauem Hinhoeren anmerkt.
"""
from __future__ import annotations

import io
import os
import wave
from pathlib import Path

import numpy as np

from .zwischenlager import schluessel

SR = 44100
PAUSE_NACH_SATZ = 0.75      # Sekunden Stille hinter jeder gesprochenen Slide
MINDESTSTAND = 2.4          # so lange steht eine Slide mindestens

# Prosodie. Piper erzeugt je Aufruf genau eine Sprechmelodie. Wirft man ihm
# einen ganzen Absatz hin, bekommt man einen einzigen, gleichmaessig
# durchlaufenden Bogen - und genau das klingt nach Maschine. Satz fuer Satz
# erzeugt bekommt jeder Satz seine eigene Melodie, und dazwischen darf
# geschwiegen werden.
PAUSE_SATZ = 0.40           # Stille zwischen zwei Saetzen
PAUSE_FRAGE = 0.55          # nach einer Frage laenger - sie will nachhallen
PAUSE_DOPPELPUNKT = 0.28    # ein Doppelpunkt kuendigt an, das braucht Luft
VORLAUF = 0.12              # Stille am Anfang, sonst klemmt der erste Laut
TEMPO_STREUUNG = 0.07       # +/- 7 % Sprechtempo je Satz
TEMPO_GRUND = 1.18          # etwas langsamer als die Voreinstellung

# Rauschanteile der Synthese. Sie stehen hier und nicht im Aufruf, weil sie in
# den Schluessel des Zwischenlagers eingehen: wer daran dreht, will neue
# Aufnahmen und soll sie auch bekommen.
RAUSCHEN = 0.6
RAUSCHEN_W = 0.75


# ------------------------------------------------------------------ Werkzeug
def _tiefpass(x: np.ndarray, grenze: float, ordnung: int = 2) -> np.ndarray:
    """Butterworth-Betragsgang ueber die FFT. Nullphasig und ohne scipy."""
    n = len(x)
    if n == 0:
        return x
    spektrum = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    gang = 1.0 / np.sqrt(1.0 + (f / grenze) ** (2 * ordnung))
    return np.fft.irfft(spektrum * gang, n).astype(np.float32)


def _falten(x: np.ndarray, kern: np.ndarray) -> np.ndarray:
    """Faltung ueber die FFT - der Ersatz fuer scipy.signal.fftconvolve."""
    n = len(x) + len(kern) - 1
    schnell = 1 << (n - 1).bit_length()
    ergebnis = np.fft.irfft(np.fft.rfft(x, schnell) * np.fft.rfft(kern, schnell), schnell)
    return ergebnis[: len(x)].astype(np.float32)


def _umtasten(x: np.ndarray, von: int, nach: int = SR) -> np.ndarray:
    """Abtastrate wechseln, bandbegrenzt, ueber die FFT.

    Piper liefert je nach Modell 16 000 oder 22 050 Hz, die Tonspur laeuft auf
    44 100. Lineare Interpolation waere billiger, holt sich beim Hochtasten aber
    Spiegelfrequenzen ins Band - bei Zischlauten deutlich hoerbar.
    """
    if von == nach or len(x) == 0:
        return x.astype(np.float32)
    n_alt = len(x)
    n_neu = int(round(n_alt * nach / von))
    spektrum = np.fft.rfft(x)
    ziel = np.zeros(n_neu // 2 + 1, dtype=complex)
    uebernehmen = min(len(spektrum), len(ziel))
    ziel[:uebernehmen] = spektrum[:uebernehmen]
    return (np.fft.irfft(ziel, n_neu) * (n_neu / n_alt)).astype(np.float32)


def _halbton(grund: float, n: int) -> float:
    return grund * 2 ** (n / 12)


def _hall(x: np.ndarray, rng, sekunden: float = 2.2, anteil: float = 0.34) -> np.ndarray:
    """Faltungshall aus abklingendem, gefiltertem Rauschen."""
    n = int(sekunden * SR)
    t = np.linspace(0, sekunden, n, dtype=np.float32)
    ir = rng.normal(0, 1, n).astype(np.float32) * np.exp(-t * 2.6)
    ir = _tiefpass(ir, 2600)
    ir /= np.abs(ir).max() + 1e-9
    nass = _falten(x, ir)
    nass /= np.abs(nass).max() + 1e-9
    return ((1 - anteil) * x + anteil * nass).astype(np.float32)


# -------------------------------------------------------------------- Musik
STANDARD_STIMMUNG = {"grund": 65.41, "stufen": [0, 7, 10, 12, 15],
                     "glocken": 0.75, "luft": 0.45}


def musik(dauer: float, stimmung: dict | None = None, seed: int = 0) -> np.ndarray:
    """Ambient-Bett in Stereo, float32, exakt `dauer` Sekunden lang."""
    st = {**STANDARD_STIMMUNG, **(stimmung or {})}
    rng = np.random.default_rng(seed or 1)
    n = max(int(dauer * SR), SR // 10)
    t = np.arange(n, dtype=np.float32) / SR
    links = np.zeros(n, np.float32)
    rechts = np.zeros(n, np.float32)
    grund = float(st["grund"])
    stufen = list(st["stufen"])

    # 1) Bordun: Grundton und Quinte, leicht verstimmt, damit es atmet
    for f, amp in ((grund, 0.34), (grund * 1.4983, 0.22), (grund * 2, 0.20),
                   (grund * 3, 0.11), (grund * 4, 0.07)):
        for kanal, versatz in ((links, -1.0), (rechts, 1.0)):
            ff = f * (1 + versatz * rng.uniform(0.0006, 0.0022))
            lfo = 0.72 + 0.28 * np.sin(2 * np.pi * rng.uniform(0.03, 0.075) * t
                                       + rng.uniform(0, 6.28))
            kanal += np.sin(2 * np.pi * ff * t).astype(np.float32) * lfo * amp

    # 2) Flaeche: Tonleiterstufen, jede mit eigener langsamer Schwelle
    for stufe in stufen:
        f = _halbton(grund, stufe) * 2
        periode = rng.uniform(9.0, 17.0)
        # Untergrenze 0.42: die Flaeche verschwindet nie ganz, sonst reisst
        # zwischen den Schwellen ein Loch auf.
        h = 0.42 + 0.58 * np.clip(np.sin(2 * np.pi * t / periode + rng.uniform(0, 6.28)),
                                  0, 1) ** 1.4
        vers = 1 + rng.uniform(0.0015, 0.0035)
        kern = (np.sin(2 * np.pi * f * t) * 0.62
                + np.sin(2 * np.pi * f * vers * t) * 0.38
                + np.sin(2 * np.pi * f * 2.002 * t) * 0.22
                + np.sin(2 * np.pi * f * 3.001 * t) * 0.12
                + np.sin(2 * np.pi * f * 4.004 * t) * 0.06).astype(np.float32)
        amp = rng.uniform(0.10, 0.17)
        pan = rng.uniform(0.28, 0.72)
        links += kern * h * amp * (1 - pan)
        rechts += kern * h * amp * pan

    # 3) Einzelne Toene, sparsam gesetzt, wie etwas Entferntes
    for _ in range(max(0, int(dauer * float(st["glocken"]) / 3.4))):
        start = rng.uniform(1.5, max(2.0, dauer - 4.0))
        i0 = int(start * SR)
        laenge = min(int(rng.uniform(3.4, 6.0) * SR), n - i0)
        if laenge <= 0:
            continue
        tt = np.arange(laenge, dtype=np.float32) / SR
        f = _halbton(grund, int(rng.choice(stufen)) + 24)
        ton = (np.sin(2 * np.pi * f * tt) * 0.70
               + np.sin(2 * np.pi * f * 2.01 * tt) * 0.20
               + np.sin(2 * np.pi * f * 3.02 * tt) * 0.10).astype(np.float32)
        ton *= (np.exp(-tt * rng.uniform(1.0, 1.7)).astype(np.float32)
                * np.clip(tt / 0.06, 0, 1) * rng.uniform(0.08, 0.13))
        pan = rng.uniform(0.2, 0.8)
        links[i0:i0 + laenge] += ton * (1 - pan)
        rechts[i0:i0 + laenge] += ton * pan

    # 4) Schimmer: hohe Teiltoene, sehr leise. Traegt die Zeichnung oben.
    for stufe in stufen[:4]:
        f = _halbton(grund, stufe) * 8
        beweg = 0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(0.02, 0.06) * t
                                   + rng.uniform(0, 6.28))
        kern = np.sin(2 * np.pi * f * t).astype(np.float32) * beweg
        pan = rng.uniform(0.25, 0.75)
        links += kern * 0.016 * (1 - pan)
        rechts += kern * 0.016 * pan

    # 5) Luft: sehr leises, tiefpassgefiltertes Rauschen
    for kanal in (links, rechts):
        rausch = _tiefpass(rng.normal(0, 1, n).astype(np.float32), 1100)
        rausch /= np.abs(rausch).max() + 1e-9
        atem = 0.6 + 0.4 * np.sin(2 * np.pi * 0.045 * t + rng.uniform(0, 6.28))
        kanal += rausch * atem * 0.030 * float(st["luft"])

    # 6) Waerme, Hall, Blenden, Pegel
    links = _hall(_tiefpass(links, 6200), np.random.default_rng(seed + 11))
    rechts = _hall(_tiefpass(rechts, 6200), np.random.default_rng(seed + 12))

    ein = np.clip(t / 2.6, 0, 1) ** 1.5
    aus = np.clip((dauer - t) / 3.2, 0, 1) ** 1.4
    stereo = np.stack([links * ein * aus, rechts * ein * aus], axis=1)

    # Erst auf das RMS-Ziel bringen - das darf ausdruecklich auch anheben.
    # Danach die Spitzen weich begrenzen statt alles herunterzuskalieren: sonst
    # bestimmt der lauteste Einzelton die Lautheit des ganzen Stuecks.
    rms = np.sqrt((stereo ** 2).mean()) + 1e-9
    stereo *= (10 ** (-19.5 / 20)) / rms
    grenze = 10 ** (-5 / 20)
    return np.clip(grenze * np.tanh(stereo / grenze), -1, 1).astype(np.float32)


# ------------------------------------------------------------------- Stimme
import re    # noqa: E402  - erst hier gebraucht
import zlib  # noqa: E402

# Trennt an Satzzeichen, laesst das Zeichen aber am Satz. Abkuerzungen wie
# "z. B." oder "Dr." wuerden hier faelschlich trennen; sie kommen in diesen
# Texten nicht vor, und ein halber Satz mehr Pause waere das kleinere Uebel
# gegenueber einem Regelwerk, das niemand mehr durchschaut.
SATZTRENNER = re.compile(r"(?<=[.!?\u2026])\s+")


def saetze_aus(text: str) -> list[str]:
    return [t.strip() for t in SATZTRENNER.split(text or "") if t.strip()]


def _pause_nach(satz: str) -> float:
    """Wie lange nach diesem Satz geschwiegen wird."""
    ende = satz.rstrip()[-1:] if satz.strip() else ""
    if ende == "?":
        return PAUSE_FRAGE
    if ende == ":":
        return PAUSE_DOPPELPUNKT
    return PAUSE_SATZ


def _tempo(satz: str) -> float:
    """Sprechtempo fuer diesen Satz, leicht schwankend.

    Gleichmaessiges Tempo ueber alle Saetze ist das zweite, was maschinell
    klingt. Die Schwankung haengt am Satz selbst und nicht am Zufall - sonst
    bekaeme derselbe Satz bei jedem Lauf einen anderen Schluessel im
    Zwischenlager und wuerde jedes Mal neu gesprochen.
    """
    # Nicht hash(): Pythons Zeichenketten-Hash ist je Prozess zufaellig
    # gesalzen. Derselbe Satz bekaeme bei jedem Lauf ein anderes Tempo, das
    # Zwischenlager waere wertlos und zwei Renderlaeufe klaengen verschieden.
    stelle = zlib.crc32(satz.encode("utf-8")) % 1000 / 1000.0
    return TEMPO_GRUND * (1 + (stelle - 0.5) * 2 * TEMPO_STREUUNG)


BESTAND = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def modell(name: str, lager: Path) -> tuple[Path, Path] | None:
    """Holt Sprachmodell und Konfiguration. None heisst: es gibt keine Stimme.

    Faellt der Abruf aus, laeuft das Video ohne Stimme weiter. Stumm ist
    besser als gar nicht.
    """
    import urllib.request

    ordner = lager / "stimmen"
    ordner.mkdir(parents=True, exist_ok=True)
    guete = name.rsplit("-", 1)[-1] if "-" in name else "medium"
    sprecher = name.split("-")[1] if name.count("-") >= 2 else "thorsten"
    quelle = f"{BESTAND}/de/de_DE/{sprecher}/{guete}/"

    pfade = []
    for endung in (".onnx", ".onnx.json"):
        ziel = ordner / f"{name}{endung}"
        if not ziel.exists() or ziel.stat().st_size == 0:
            try:
                anfrage = urllib.request.Request(
                    f"{quelle}{name}{endung}?download=true",
                    headers={"User-Agent": "media-kit/1.0"},
                )
                with urllib.request.urlopen(anfrage, timeout=180) as antwort:
                    roh = antwort.read()
                neben = ziel.with_suffix(ziel.suffix + ".teil")
                neben.write_bytes(roh)
                neben.replace(ziel)
            except Exception as fehler:
                print(f"  Stimmmodell {name} nicht geladen "
                      f"({type(fehler).__name__}: {fehler})")
                return None
        pfade.append(ziel)
    return pfade[0], pfade[1]


def _stimme_laden(namen: list[str], lager: Path):
    """Probiert die Modelle der Reihe nach und nimmt das erste, das laedt.

    Ein hoeher aufgeloestes Modell klingt besser, ist aber groesser und nicht
    fuer jeden Sprecher vorhanden. Ohne Rueckfall bekaeme man fuer einen
    Tippfehler im Modellnamen ein stummes Reel - und wuerde lange suchen,
    warum.
    """
    try:
        from piper import PiperVoice
    except Exception as fehler:
        print(f"  piper nicht verfuegbar ({type(fehler).__name__}: {fehler})")
        return None, ""

    for name in namen:
        dateien = modell(name, lager)
        if not dateien:
            continue
        try:
            return PiperVoice.load(str(dateien[0]), str(dateien[1])), name
        except Exception as fehler:
            print(f"  {name} nicht ladbar ({type(fehler).__name__}: {fehler})")
    return None, ""


# --------------------------------------------------------- Satz im Lager
_FASSUNG = ""


def fassung() -> str:
    """Fassung von Piper. Gehoert in den Schluessel des Zwischenlagers.

    Eine neue Fassung spricht denselben Satz anders. Ohne sie im Schluessel
    bekaeme ein Reel nach dem Aktualisieren zwei Stimmlagen: die unveraenderten
    Saetze aus dem Lager, die geaenderten frisch gesprochen.
    """
    global _FASSUNG
    if not _FASSUNG:
        from importlib.metadata import PackageNotFoundError, version
        for name in ("piper-tts", "piper"):
            try:
                _FASSUNG = version(name)
                break
            except PackageNotFoundError:
                continue
        else:
            _FASSUNG = "ohne"
    return _FASSUNG


def _ablage(satz: str, stimmname: str, lager: Path) -> Path:
    """Wo dieser Satz, in dieser Stimme, unter diesen Einstellungen liegt."""
    name = schluessel(satz, stimmname, fassung(),
                      round(_tempo(satz), 6), RAUSCHEN, RAUSCHEN_W)
    ordner = Path(lager) / "saetze"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner / f"{name}.wav"


def _aus_lager(satz: str, stimmname: str, lager: Path) -> np.ndarray | None:
    ablage = _ablage(satz, stimmname, lager)
    if ablage.exists() and ablage.stat().st_size > 0:
        return _aus_wav(ablage.read_bytes())
    return None


def _hinlegen(ziel: Path, roh: bytes) -> None:
    """Erst daneben schreiben, dann umbenennen.

    Ein abgebrochener Lauf soll kein halbes WAV hinterlassen, das beim
    naechsten Mal als fertige Aufnahme durchgeht - der unangenehmste
    Cache-Fehler, weil er sich als Ergebnis tarnt und nicht als Fehler.
    """
    neben = ziel.with_suffix(f".teil{os.getpid()}")
    try:
        neben.write_bytes(roh)
        neben.replace(ziel)
    finally:
        if neben.exists():
            neben.unlink()


def _aus_wav(roh: bytes) -> np.ndarray:
    """WAV-Bytes zu mono float32 bei 44 100 Hz."""
    with wave.open(io.BytesIO(roh), "rb") as w:
        daten = w.readframes(w.getnframes())
        kanaele, rate = w.getnchannels(), w.getframerate()
    x = np.frombuffer(daten, np.int16).astype(np.float32) / 32768.0
    if kanaele > 1:
        x = x.reshape(-1, kanaele).mean(axis=1)
    return _umtasten(x, rate)


# ------------------------------------------------------------------ Sprechen
def _zusammensetzen(zerlegt: list[list[str]], hole) -> list[np.ndarray] | None:
    """Ein Clip je Slide, aus den Saetzen und der Stille dazwischen.

    `hole(satz)` liefert die Aufnahme oder None; None bricht alles ab. Die
    Zerlegung steht hier nur einmal, damit der Weg aus dem Lager und der Weg
    ueber Piper nicht auseinanderlaufen koennen - sonst klaenge ein Reel aus
    dem Lager anders als dasselbe Reel frisch gesprochen.
    """
    clips = []
    for teile in zerlegt:
        if not teile:
            clips.append(np.zeros(0, np.float32))
            continue
        stueck = [np.zeros(int(VORLAUF * SR), np.float32)]
        for i, satz in enumerate(teile):
            gesprochen = hole(satz)
            if gesprochen is None:
                return None
            stueck.append(gesprochen)
            if i < len(teile) - 1:
                stueck.append(np.zeros(int(_pause_nach(satz) * SR), np.float32))
        clips.append(np.concatenate(stueck))
    return clips


def sprechen(saetze: list[str], stimmname: str, lager: Path,
             rueckfall: list[str] | None = None) -> list[np.ndarray] | None:
    """Ein Sprachclip je Slide, mono float32 bei 44 100 Hz.

    Jede Slide wird nicht am Stueck gesprochen, sondern Satz fuer Satz, und
    dazwischen wird geschwiegen. Das ist der ganze Unterschied zwischen
    "vorgelesen" und "abgespielt": Piper erzeugt je Aufruf eine Sprechmelodie,
    und ein ganzer Absatz bekommt davon nur eine einzige.

    Jeder Satz liegt danach im Zwischenlager. Steht schon alles da, wird Piper
    gar nicht geladen - siehe den Abschnitt oben im Modul.

    None heisst: keine Stimme, das Reel laeuft stumm weiter.
    """
    zerlegt = [saetze_aus(t) for t in saetze]
    gesamt = sum(len(t) for t in zerlegt)

    # Erst nachsehen, ob schon alles dasteht. Alles oder nichts: einen Teil aus
    # dem Lager zu nehmen und fuer den Rest ein Modell zu laden, das vielleicht
    # ein anderes ist als das von damals, mischte zwei Stimmen in einem Reel.
    fertig = _zusammensetzen(zerlegt, lambda s: _aus_lager(s, stimmname, lager))
    if fertig is not None:
        if gesamt:
            print(f"  Stimme: alle {gesamt} Saetze aus dem Zwischenlager")
        return fertig

    try:
        from piper import SynthesisConfig
    except Exception as fehler:
        print(f"  piper nicht verfuegbar ({type(fehler).__name__}: {fehler})")
        return None

    kandidaten = [stimmname] + [n for n in (rueckfall or []) if n != stimmname]
    voice, genommen = _stimme_laden(kandidaten, lager)
    if voice is None:
        return None
    if genommen != stimmname:
        print(f"  Stimme {stimmname} nicht verfuegbar - genommen wird {genommen}")

    # Unter `genommen` ablegen, nicht unter dem gewuenschten Namen: ein
    # Rueckfall soll die Aufnahmen der eigentlichen Stimme weder ueberschreiben
    # noch spaeter als solche ausgegeben bekommen.
    gezaehlt = [0]

    def hole(satz: str) -> np.ndarray | None:
        schon = _aus_lager(satz, genommen, lager)
        if schon is not None:
            gezaehlt[0] += 1
            return schon
        roh = _einen_satz(voice, satz, SynthesisConfig)
        if roh is None:
            return None
        _hinlegen(_ablage(satz, genommen, lager), roh)
        return _aus_wav(roh)

    clips = _zusammensetzen(zerlegt, hole)
    if clips is not None:
        print(f"  Stimme: {gesamt - gezaehlt[0]} von {gesamt} Saetzen gesprochen, "
              f"{gezaehlt[0]} aus dem Zwischenlager")
    return clips


def _einen_satz(voice, satz: str, SynthesisConfig) -> bytes | None:
    """Einen Satz sprechen und das WAV zurueckgeben, wie Piper es liefert.

    Bewusst unbearbeitet: was ins Lager geht, ist genau das Ergebnis der
    Synthese. Aendert sich spaeter etwas am Umtasten oder an den Pausen, gelten
    die Aufnahmen weiter - und ein Blick ins Lager laesst sich abspielen.
    """
    konf = SynthesisConfig(length_scale=_tempo(satz),
                           noise_scale=RAUSCHEN, noise_w_scale=RAUSCHEN_W)
    puffer = io.BytesIO()
    try:
        with wave.open(puffer, "wb") as w:
            voice.synthesize_wav(satz, w, syn_config=konf)
    except Exception as fehler:
        print(f"  Satz nicht gesprochen ({type(fehler).__name__}: {fehler})")
        return None
    return puffer.getvalue()


# ------------------------------------------------------------------ Mischen
def mischen(bett: np.ndarray, clips: list[np.ndarray], starts: list[float]) -> np.ndarray:
    """Sprache ueber die Musik legen und die Musik darunter zurueckziehen.

    Ohne Absenkung kaempfen Bordun und Stimme im selben Frequenzbereich und man
    versteht die Haelfte nicht. Die Absenkung laeuft ueber ein 0,35-Sekunden-
    Fenster weich an und wieder aus, damit kein Pumpen hoerbar wird.
    """
    laenge = bett.shape[0]
    rede = np.zeros(laenge, np.float32)
    for clip, start in zip(clips, starts):
        a = int(start * SR)
        b = min(laenge, a + clip.shape[0])
        if b > a:
            rede[a:b] += clip[: b - a]

    spitze = float(np.max(np.abs(rede))) or 1.0
    rede *= 0.62 / spitze

    aktiv = (np.abs(rede) > 0.004).astype(np.float32)
    fenster = int(0.35 * SR)
    aktiv = np.clip(np.convolve(aktiv, np.ones(fenster, np.float32) / fenster,
                                mode="same") * 3.0, 0, 1)
    huelle = 1.0 - 0.62 * aktiv

    return np.clip(bett * huelle[:, None] + rede[:, None], -0.985, 0.985).astype(np.float32)


def schreiben(ziel: Path, stereo: np.ndarray) -> Path:
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ziel), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(stereo, -1, 1) * 32767).astype("<i2").tobytes())
    return ziel


def standzeiten(clips: list[np.ndarray] | None, anzahl: int,
                voreinstellung: float) -> list[float]:
    """Wie lange jede Slide steht.

    Mit Stimme richtet sich das nach der Sprechdauer plus einer Atempause -
    sonst wechselt das Bild mitten im Satz, was schlimmer aussieht als eine zu
    lange Standzeit. Ohne Stimme gilt der Wert aus der Job-Datei.
    """
    if not clips:
        return [voreinstellung] * anzahl
    dauern = []
    for i in range(anzahl):
        clip = clips[i] if i < len(clips) else np.zeros(0, np.float32)
        gesprochen = len(clip) / SR
        dauern.append(round(max(gesprochen + PAUSE_NACH_SATZ, MINDESTSTAND), 3))
    return dauern
