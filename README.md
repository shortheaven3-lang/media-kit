# media-kit

Erzeugt aus **einer** Beschreibung eines Beitrags alle Formate, die er braucht:
Reel mit Ton, Karussell, Story-Bild, Vorschaubild fürs Web. Quelle für
[shortheaven3-autoposter](https://github.com/shortheaven3-lang/shortheaven3-autoposter),
[denkbeleg-bilder](https://github.com/shortheaven3-lang/denkbeleg-bilder) und
[webapp](https://github.com/shortheaven3-lang/webapp).

Alles darin ist kostenlos und ohne Konto nutzbar. Der einzige optionale
Schlüssel ist der von Pexels, und der wird nur für die Bildersuche gebraucht.

## Warum es so gebaut ist

**Ein Job, viele Formate.** Bisher lag derselbe Text zweimal: einmal als
Karussell-Slide, einmal als Reel-Text. Zwei Stellen, die auseinanderlaufen.
Hier steht der Beitrag einmal in einer JSON-Datei, und `ausgaben` sagt, was
daraus wird.

**Layout in HTML/CSS, nicht in Zeichenbefehlen.** Zeilenumbruch, Ligaturen,
Kerning, gemischte Auszeichnung mitten im Satz — das kann ein Browser seit
Jahrzehnten richtig, und eine Zeichenschleife in Python kann es nie ganz.
Der Preis ist ein Browser als Abhängigkeit; er wird einmal je Lauf gestartet
und macht alle Slides aller Formate.

**Bewegung macht ffmpeg, nicht Python.** Der naheliegende Weg zu einem Reel ist
eine Schleife über 720 Frames. So arbeitet der bestehende Autoposter, und es
kostet pro Reel Minuten CPU. Hier entstehen je Slide genau zwei Standbilder —
Hintergrund und Text —, und `zoompan`, `xfade` und `overlay` machen daraus die
Bewegung. Für ein Reel aus sieben Slides sind das **14 Aufnahmen statt 720
gezeichneter Frames**.

Der zweite, wichtigere Gewinn ist die Bildgüte: die Textebene wird nie
skaliert. Beim Frame-für-Frame-Weg zoomt der Text mit und wird dabei weich.
Hier zieht nur das Foto darunter, die Schrift steht pixelgenau still.

**Nichts zweimal bauen.** Jede Aufnahme liegt unter einem Schlüssel aus ihrem
Inhalt im Zwischenlager. Wer nur die Bildunterschrift ändert, rendert kein Bild
neu. Gemessen: ein Beitrag mit vier Slides in zwei Formaten braucht beim ersten
Mal rund 15 Sekunden, beim zweiten **0,9 Sekunden**.

**Kein Server.** Die Oberfläche baut die Job-Datei und übergibt sie an GitHubs
eigenen Dateieditor; der Push löst den Renderlauf aus. Keine laufenden Kosten,
kein Zugangstoken im Browser.

## Aufbau

```
media_kit/
  job.py            liest und prüft, was gemacht werden soll
  marke.py          sagt, wie es aussehen soll — Farben, Schriften, Ton
  formate.py        die Ausgabemaße, an genau einer Stelle
  layout.py         baut daraus HTML
  bild.py           macht aus HTML Standbilder (ein Browser für alles)
  video.py          macht aus Standbildern ein Video (ein ffmpeg-Aufruf)
  ton.py            Stimme (Piper, CC0) und Musik (im Programm erzeugt)
  quellen.py        freie Bilder, mit Lizenznachweis
  zwischenlager.py  hält fest, was schon gebaut wurde
  werk.py           setzt das zusammen
  cli.py            Kommandozeile

vorlagen/           basis.css und je Bildsprache eine Datei
marken/             shortheaven3.json, denkbeleg.json
jobs/               die Beitragsdateien
ergebnisse/         was dabei herauskommt (wird mitcommittet)
web/                die Oberfläche, eine statische Seite
```

## Loslegen

```bash
pip install -r requirements.txt
playwright install --with-deps chromium

python3 -m media_kit.cli neu --marke denkbeleg --id 2026-09-20-testeffekt
python3 -m media_kit.cli pruefen jobs/2026-09-20-testeffekt.json
python3 -m media_kit.cli rendern jobs/2026-09-20-testeffekt.json
```

Für die Sprachausgabe zusätzlich `pip install -r requirements-stimme.txt`.
Ohne sie läuft alles weiter, die Reels bleiben nur stumm.

Gesprochen wird **Satz für Satz, nicht Absatz am Stück**. Piper erzeugt je
Aufruf genau eine Sprechmelodie; wirft man ihm einen ganzen Absatz hin, bekommt
man einen einzigen durchlaufenden Bogen, und genau das klingt nach Maschine.
Satzweise erzeugt bekommt jeder Satz seine eigene Melodie, dazwischen wird
geschwiegen — nach einer Frage länger als nach einer Aussage —, und das Tempo
schwankt um sieben Prozent. Die Schwankung hängt am Satz selbst, nicht am
Zufall: derselbe Text klingt bei jedem Lauf gleich, sonst wäre das
Zwischenlager wertlos.

Weitere Befehle:

```bash
python3 -m media_kit.cli marken            # vorhandene Marken
python3 -m media_kit.cli formate           # vorhandene Formate
python3 -m media_kit.cli suchen "leerer strand" --anbieter wikimedia
python3 -m media_kit.cli rendern --alle --nur reel
python3 -m media_kit.cli aufraeumen        # Zwischenlager leeren
```

## Die Job-Datei

```json
{
  "id": "2026-09-20-testeffekt",
  "marke": "denkbeleg",
  "rubrik": "widerlegt",
  "termin": "2026-09-20T06:30:00+02:00",
  "ausgaben": ["karussell", "og"],
  "slides": [
    { "typ": "haken",  "titel": "…", "unterzeile": "…" },
    { "typ": "inhalt", "kopf": "…", "text": "…", "quelle": "…" },
    { "typ": "ende",   "merksatz": "…" }
  ],
  "caption": "…"
}
```

Slide-Typen: `haken`, `inhalt`, `zitat`, `frage`, `ende`. Eine Leerzeile im
`text` trennt Absätze. Erlaubt sind `<b>`, `<i>`, `<em>`, `<mark>`, `<br>`,
`<span>`, `<small>` — alles andere wird als Text gesetzt, nicht als Auszeichnung.

Weitere Felder:

| Feld | Bedeutung |
|---|---|
| `slides[].bild` | `datei:…`, eine `https://`-Adresse, `pexels:<kennung>` oder `motiv:<suchwort>` |
| `slides[].bildnachweis` | Urheber, Lizenz und Fundstelle zu einer festen Adresse |
| `slides[].sprich` | was vorgelesen wird, wenn es vom Slide-Text abweichen soll |
| `ton.stimmung` | welche Tonstimmung aus der Markendatei gilt |
| `video.slidedauer` | Standzeit je Slide, wenn keine Stimme die Länge vorgibt |

Ohne Angabe bekommt ein Video Ton und ein Karussell nicht.

## Formate

| Name | Maße | Wofür |
|---|---|---|
| `karussell` | 1080 × 1350 | Instagram-Karussell, 4:5 |
| `reel` | 1080 × 1920 | Reel oder Short, mit Ton |
| `story` | 1080 × 1920 | Story-Standbild |
| `beitrag` | 1080 × 1080 | Einzelbild im Quadrat |
| `og` | 1200 × 630 | Vorschaubild für Web und Messenger |
| `titelbild` | 1600 × 900 | Titelbilder der WebApp |

Reel und Story rechnen mit Sicherheitszonen: oben rund 140 Pixel Profilzeile,
unten rund 330 Pixel Bildunterschrift und Schaltflächen. Wer sie ignoriert,
setzt den Merksatz unter den Folgen-Knopf.

## Das Angebot am Ende

Ein Beitrag, der nichts anbietet, verdient nichts. Ein Beitrag, der etwas
verkauft, wird weggewischt. Dazwischen liegt der Selbsttest: er redet über den
Leser statt über das Produkt, kostet nichts und verlangt keine E-Mail-Adresse.

Deshalb hängt das Programm an jeden Beitrag eine **Abschluss-Slide** in der
Bildsprache der Marke — nicht in der Job-Datei geschrieben, sondern angehängt,
damit sie nicht vergessen wird. Beim Redigieren denkt niemand an den Verweis.

Welcher der vier Testbereiche gilt, entscheidet das Thema: `produkte.json`
ordnet jedem Bereich Schlagworte zu, und der Beitrag landet dort, wo er die
meisten trifft.

```
2026-09-22-der-umschlag        -> handeln    (schieb, disziplin, morgen)
2026-09-24-das-ja-am-telefon   -> grenzen    (nein, ja gesagt)
2026-09-26-der-dienstag        -> sehen      (merk, erinner, auffall)
```

Ein einzelner Treffer reicht nicht — das wäre Zufall. Unter zwei Treffern gibt
es den allgemeinen Einstieg statt eines schlecht geratenen Bereichs: ein
unpassendes Angebot ist schädlicher als ein allgemeines, weil es zeigt, dass
niemand hingesehen hat.

Steuerung je Beitrag:

| `angebot` | Wirkung |
|---|---|
| fehlt | die Marke entscheidet |
| `true` | anhängen, Bereich selbst suchen |
| `"grenzen"` | anhängen, diesen Bereich nehmen |
| `false` | keins — nicht jeder Text verträgt einen Verweis |

**Die Schlagworte sind Wortstämme, keine Vollformen.** Deutsche trennbare Verben
zerfallen im Satz: „aufschieben“ steht als „schiebst es auf“ da und wird von der
Vollform nie gefunden. Bei zusammengesetzten Wendungen reicht auch der Stamm
nicht — „ja sag“ findet „Ja gesagt“ nicht, beide gehören in die Liste. Beides
ist beim Bauen aufgefallen und steht als Test fest.

Die Adresse der WebApp steht als `basis` in `produkte.json` und lautet
`https://limerence.blog`. Sie gehört dort auch in `APP_URL` — stimmen die
beiden nicht überein, zeigt die Abschluss-Slide auf eine andere Seite als die
Sitemap.

Fehlt sie oder steht ein Platzhalter dort, bleibt die Abschluss-Slide weg und
`pruefen` sagt es bei jedem Lauf. Der Rest des Beitrags entsteht trotzdem — eine
fehlende Adresse ist kein Grund, Bilder und Reels aufzuhalten. Eine falsche
Adresse dagegen verspricht eine Seite, die niemand findet, und das fällt erst
auf, wenn der Beitrag schon steht.

## Wie die Beiträge klingen sollen

Je Marke liegt eine Stimmführung daneben: `marken/shortheaven3-stimme.md` und
`marken/denkbeleg-stimme.md`. Sie halten fest, woran man merkt, dass ein Text
von einer Maschine stammt — nicht am Inhalt, an der Gleichmäßigkeit: der
Aphorismus ohne Ort, die immer gleiche Antithese, jeder Absatz auf eine Pointe
zulaufend, keine einzige zugegebene Einschränkung, Sätze von ähnlicher Länge.

Und was stattdessen trägt: eine Szene statt eines Begriffs, ein Gegenstand, den
man anfassen kann, eine zugegebene Grenze, unregelmäßiger Rhythmus, am Ende eine
Frage, deren Antwort niemand kennt.

Die Probe steht am Ende der Datei: Ließe sich derselbe Text mit ausgetauschten
Substantiven für ein Versicherungsunternehmen verwenden? Dann steht nichts drin.

## Eine neue Marke

Eine Datei unter `marken/` und eine unter `vorlagen/`. Der Renderkern kennt
keine einzige Farbe — deshalb kommen aus demselben Programm zwei so
verschiedene Bildsprachen wie @shortheaven3 (dunkel, Antiqua, mittig) und
@denkbeleg (helles Papier, Raster, Marker).

## Rechte

* **Schriften** aus dem Google-Fonts-Bestand, alle unter der SIL Open Font
  License. Kommerzielle Nutzung und Einbettung ausdrücklich erlaubt.
* **Stimme**: Piper (MIT) mit `de_DE-thorsten-medium` aus dem
  Thorsten-Voice-Datensatz unter CC0. Der Sprecher hat seine Stimme
  ausdrücklich freigegeben.
* **Musik** entsteht im Programm. Kein fremdes Recht im Spiel — und Instagrams
  Tonerkennung findet nichts zum Anschlagen.
* **Bilder** nur aus Quellen mit ausdrücklich kommerzieller Lizenz: Pexels,
  Pixabay, Wikimedia Commons (NC und ND werden dort ausgefiltert).

Zu jedem Beitrag entsteht ein `nachweis.json` mit Urheber, Lizenz und
Fundstelle. Die Pexels-Lizenz verlangt keine Namensnennung; das ist kein Grund,
sie nicht festzuhalten.

Geprüft und verworfen: **Openverse** (anonymer Zugang am 31.08.2026
geschlossen, HTTP 401), **Unsplash** (API-Bedingungen verbieten das dauerhafte
Speichern der Bilder — für ein Repository, das sie festhält, unpassend),
**ElevenLabs/HeyGen/LMNT/Typecast** (Konto und monatliches Freikontingent, das
am Posting-Morgen ausgeht), **edge-tts** (undokumentierter Microsoft-Endpunkt,
jederzeit abschaltbar).

## Der vorgesehene Weg zu einem Hintergrundbild

Nicht suchen lassen, sondern aussuchen. Die Suche im Renderlauf ist blind und
trifft oft daneben; eine feste Adresse macht den Lauf dagegen Bild für Bild
reproduzierbar.

```bash
python3 -m media_kit.cli suchen "leerer strand abenddaemmerung" --anzahl 5
```

Die Ausgabe nennt zu jedem Treffer Adresse, Urheber, Lizenz und Fundstelle.
Was davon passt, wandert in die Slide:

```json
{
  "typ": "haken",
  "titel": "…",
  "bild": "https://images.pexels.com/photos/35854894/pexels-photo-35854894.jpeg?auto=compress&cs=tinysrgb&fit=crop&w=1400&h=2100",
  "bildnachweis": {
    "anbieter": "pexels",
    "kennung": "35854894",
    "urheber": "Any Melnic",
    "lizenz": "Pexels-Lizenz (kommerziell erlaubt, Namensnennung nicht verlangt)",
    "fundstelle": "https://www.pexels.com/photo/misty-forest-path-with-solo-walker-in-early-morning-35854894/"
  }
}
```

Zwei Dinge daran sind wichtig:

**Der Schlüssel wird nur zum Suchen gebraucht, nicht zum Herunterladen.** Eine
Adresse auf `images.pexels.com` holt der Renderlauf ohne jedes Zugangsdatum.
Wer die Bilder anderswo aussucht — im Browser, über einen verbundenen Dienst —
kommt ganz ohne `PEXELS_API_KEY` aus.

**Ohne `bildnachweis` geht der Nachweis verloren.** Die Suche liefert Urheber
und Lizenz mit, eine nackte Adresse nicht. Ohne dieses Feld wäre ausgerechnet
der empfohlene Weg derjenige, auf dem nichts im `nachweis.json` landet.

## Wenn kein Bild gefunden wird

Die Meldung nennt jeden Anbieter einzeln mit Grund:

```
Slide 1: Hintergrund faellt aus - kein freies Bild zu 'fog forest' gefunden -
  pexels: 0 (kein PEXELS_API_KEY gesetzt); pixabay: 0 (kein PIXABAY_API_KEY
  gesetzt); wikimedia: 0 (HTTPError: 403 Forbidden)
```

Das ist mit Absicht so ausführlich. Ein fehlender Schlüssel, ein abgewiesener
Zugriff und ein untaugliches Suchwort sehen sonst gleich aus — nämlich wie ein
Bild, das eben fehlt. Genau das ist beim ersten Probelauf passiert: Wikimedia
verlangt einen User-Agent, der das Programm nennt und eine Kontaktmöglichkeit
angibt, und beantwortete die generische Kennung mit 403. Der Lauf lief
durch, die Beiträge waren fertig, und niemand hätte gemerkt, dass jeder
Hintergrund fehlte.

Der Lauf bricht dabei nie ab. Ein Beitrag ohne Foto ist besser als kein Beitrag.

## Was in GitHub Actions passiert

* **`rendern.yml`** — eine Job-Datei fällt ins Repository, die Action rendert
  und schreibt das Ergebnis zurück. Das Zwischenlager wird zwischen den Läufen
  aufgehoben, sonst lädt jeder Lauf 2 MB Schriften und 60 MB Sprachmodell neu.
* **`pruefung.yml`** — Tests bei jedem Push.
* **`seite.yml`** — veröffentlicht die Oberfläche über GitHub Pages.

Öffentlich ist das Repository aus einem handfesten Grund: öffentliche Repos
haben unbegrenzte Actions-Minuten, private nur 2000 im Monat — und das Rendern
läuft dort. Zugangsdaten liegen keine im Code.

Optionale Secrets: `PEXELS_API_KEY`, `PIXABAY_API_KEY`. Ohne sie bleibt
Wikimedia Commons, das keinen Schlüssel braucht.

## Tests

```bash
pip install -r requirements-pruefung.txt
python3 -m pytest -q
```

Geprüft wird das, was still kaputtgeht:

* **Das Job-Schema** — Tippfehler sollen beim Einreichen auffallen, nicht in
  der Action.
* **Die Längenrechnung des Videos**, gegen echtes ffmpeg gemessen. Dort war ein
  Fehler: eine frühere Fassung schlug eine Überblende auf die Summe der
  Standzeiten; das Video war real 9,0 Sekunden lang, die Rechnung sagte 9,6.
  So etwas fällt ohne Nachmessen nicht auf, das Video sieht ja richtig aus.
* **Die Tonspur** — Länge, Reproduzierbarkeit, und dass die Musik unter der
  Stimme weich zurückgeht statt zu pumpen.
* **Der Textsatz** — dass Inhalt Inhalt bleibt und nicht zu Markup wird.
* **Das Zwischenlager** — vor allem, dass ein abgebrochener Bau nichts
  hinterlässt. Eine halbe Datei, die als fertig gilt, ist der unangenehmste
  Cache-Fehler: sie tarnt sich als kaputtes Ergebnis statt als Fehler.

## Grenzen

* **Der Browser ist die größte Abhängigkeit.** Rund 170 MB Chromium. Dafür gibt
  es korrekten Textsatz und Layouts, die sich in CSS ändern lassen.
* **Die Vorschau im Browser ist nicht bindend.** Sie bindet dieselben
  Stilvorlagen ein, setzt den Text aber auf der Maschine des Betrachters.
  Verbindlich ist, was die Action ausgibt.
* **Die Bildersuche über `motiv:` ist blind** und trifft oft daneben. Der
  vorgesehene Weg ist, beim Redigieren eine feste Adresse unter `bild`
  einzutragen, nachdem jemand die Treffer wirklich angesehen hat. Ohne
  `PEXELS_API_KEY` kommen die Treffer von Wikimedia Commons, und das braucht
  englische, sachliche Suchworte — „nebliger Waldweg“ findet dort nichts,
  `fog forest morning` schon.
* **Kein Zeitgeber.** Wann etwas erscheint, entscheidet weiterhin der
  Autoposter. Dieses Programm erzeugt nur die Medien.
