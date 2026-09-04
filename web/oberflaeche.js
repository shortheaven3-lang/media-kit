/* Oberflaeche des media-kit.
 *
 * Zwei Dinge, die hier absichtlich so sind:
 *
 * 1. Kein Server und kein Zugangstoken. Die Seite baut die Job-Datei und
 *    uebergibt sie an GitHubs eigenen Dateieditor. Angemeldet ist man dort
 *    ohnehin; ein Token im Browser waere ein Zugangsdatum an der falschen
 *    Stelle.
 *
 * 2. Formatmasse, Sicherheitszonen und Marken stehen nicht hier, sondern in
 *    daten.json - erzeugt aus den Python-Quellen. Sonst zeigt die Vorschau
 *    irgendwann etwas anderes, als die Action liefert.
 */
'use strict';

const REPO = 'shortheaven3-lang/media-kit';
const SCHRIFTQUELLE = 'https://fonts.googleapis.com/css2'
  + '?family=Archivo:wght@400..700&family=Inter:wght@400..700'
  + '&family=JetBrains+Mono:wght@400..600'
  + '&family=EB+Garamond:ital,wght@0,400..600;1,400..500&display=swap';
const ZWEIG = 'main';

let DATEN = null;
let stand = {
  marke: '', kennung: '', rubrik: '', termin: '',
  ausgaben: [], caption: '',
  slides: [
    { typ: 'haken', titel: 'Der Satz, der zum Anhalten bringt.', unterzeile: '' },
    { typ: 'inhalt', kopf: 'Worum es geht', text: 'Ein Absatz.', quelle: '' },
    { typ: 'ende', merksatz: 'Der Satz, der hängen bleibt.' },
  ],
};

const $ = (kennung) => document.getElementById(kennung);

// ------------------------------------------------------------------ Textsatz
const ERLAUBT = ['b', 'strong', 'i', 'em', 'mark', 'br', 'span', 'small'];

function sicher(text) {
  // Dieselbe Regel wie in layout.py: erst alles unschaedlich machen, dann die
  // Handvoll erlaubter Auszeichnungen gezielt zuruecknehmen.
  const roh = String(text ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;');
  return roh.replace(
    new RegExp(`&lt;(/?)(${ERLAUBT.join('|')})\\s*(/?)&gt;`, 'gi'),
    '<$1$2$3>');
}

function absaetze(text) {
  return String(text ?? '').trim().split(/\n\s*\n/)
    .filter((t) => t.trim()).map((t) => `<p>${sicher(t)}</p>`).join('');
}

// -------------------------------------------------------------- Slide-Rumpf
function rumpf(slide, nummer, gesamt, marke) {
  const typ = slide.typ || 'inhalt';
  let block = '';

  if (typ === 'haken') {
    block = `<h1>${sicher(slide.titel)}</h1>`;
    if (slide.unterzeile) block += `<div class="unterzeile">${sicher(slide.unterzeile)}</div>`;
  } else if (typ === 'ende') {
    const abbinder = slide.abbinder || (marke.abbinder ? `Folge <span>${marke.abbinder}</span>` : '');
    block = `<div class="merksatz">${sicher(slide.merksatz)}</div>`;
    if (abbinder) block += `<div class="abbinder">${sicher(abbinder)}</div>`;
  } else if (typ === 'zitat') {
    block = `<div class="fliess">${absaetze(slide.text)}</div>`;
    if (slide.herkunft) block += `<div class="herkunft">${sicher(slide.herkunft)}</div>`;
  } else {
    if (slide.kopf) block += `<div class="kopf">${sicher(slide.kopf)}</div>`;
    block += `<div class="fliess">${absaetze(slide.text)}</div>`;
    if (slide.quelle) block += `<div class="quelle">${sicher(slide.quelle)}</div>`;
  }

  let zaehler = '';
  if (gesamt > 1 && typ !== 'ende') {
    zaehler = `<div class="zaehler">${String(nummer).padStart(2, '0')} / ${String(gesamt).padStart(2, '0')}</div>`;
  }
  return { typ, block: zaehler + block };
}

// Google Fonts statt der TTF-Dateien aus dem Zwischenlager: die Vorschau soll
// nichts herunterladen muessen, und es sind dieselben Schnitte.
const WEBSCHRIFT = {
  Archivo: 'Archivo', Inter: 'Inter', JetBrainsMono: 'JetBrains Mono',
  EBGaramond: 'EB Garamond', Lora: 'Lora', Cormorant: 'Cormorant Garamond',
  SpaceGrotesk: 'Space Grotesk',
};

async function vorschauSeite(slide, nummer, gesamt, markenName, formatName, massstab) {
  const marke = DATEN.marken[markenName];
  const format = DATEN.formate[formatName];
  const [oben, unten] = format.sicher;
  const grundgroesse = (format.breite / 1080) * 16;
  const quer = format.breite > format.hoehe ? 'quer' : 'hoch';

  const [basis, stil] = await Promise.all([
    hole('vorlagen/basis.css'), hole(`vorlagen/${marke.vorlage}.css`),
  ]);

  let variablen = '';
  for (const [k, v] of Object.entries(marke.farben)) {
    if (!k.startsWith('_')) variablen += `--${k}:${v};`;
  }
  for (const [rolle, familie] of Object.entries(marke.schriften)) {
    variablen += `--schrift-${rolle}:'${WEBSCHRIFT[familie] || familie}';`;
  }

  const { typ, block } = rumpf(slide, nummer, gesamt, marke);
  const stempel = (nummer === 1 && ['widerlegt', 'belegt', 'neu'].includes((stand.rubrik || '').toLowerCase()))
    ? `<div class="stempel">${sicher(stand.rubrik.toUpperCase())}</div>` : '';

  // Der Schriftverweis darf den ersten Anstrich nicht aufhalten. Ein
  // gewoehnliches <link rel=stylesheet> tut genau das - und wenn die Adresse
  // nicht erreichbar ist (Firmennetz, Werbeblocker, kein Netz), bleibt die
  // Vorschau dauerhaft leer, ohne dass jemand erfaehrt warum. Ueber
  // media="print" laedt der Browser die Datei, ohne auf sie zu warten; das
  // onload schaltet sie danach scharf. Bis dahin steht der Text in der
  // Ersatzschrift - sichtbar falsch ist besser als unsichtbar richtig.
  const schriftverweis =
    '<link rel="stylesheet" media="print" onload="this.media=\'all\'" href="' + SCHRIFTQUELLE + '">';

  return `<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
${schriftverweis}
<style>
:root{${variablen}--breite:${format.breite}px;--hoehe:${format.hoehe}px;
--sicher-oben:${oben}px;--sicher-unten:${unten}px;}
html{font-size:${grundgroesse.toFixed(4)}px;}
${basis}
${stil}
/* Verkleinert wird im Dokument, nicht am iframe. Ein per transform skaliertes
   iframe malt Chromium unter Umstaenden gar nicht mehr - der Rahmen steht dann
   in der richtigen Groesse da und bleibt leer. zoom skaliert dagegen die
   Layoutberechnung selbst, das Satzbild bleibt also proportionsgleich. */
html{zoom:${massstab};}
</style></head>
<body class="fmt-${formatName} ${quer} typ-${typ} schicht-voll">
<div class="grund"></div><div class="schleier"></div>${stempel}
<div class="blatt">${block}</div></body></html>`;
}

const zwischenlager = new Map();

/* Die veroeffentlichte Seite hat vorlagen/ neben sich liegen; wer web/index.html
 * direkt aus dem Arbeitsverzeichnis oeffnet, findet sie eine Ebene hoeher.
 * Beide Faelle sollen funktionieren, ohne dass man daran denken muss. */
async function hole(pfad) {
  if (!zwischenlager.has(pfad)) {
    zwischenlager.set(pfad, (async () => {
      for (const versuch of [pfad, `../${pfad}`]) {
        try {
          const antwort = await fetch(versuch);
          if (antwort.ok) return antwort.text();
        } catch { /* naechster Versuch */ }
      }
      throw new Error(`${pfad} nicht gefunden`);
    })());
  }
  return zwischenlager.get(pfad);
}

// ------------------------------------------------------------------- Aufbau
function zeichneAusgaben() {
  const behaelter = $('ausgaben');
  behaelter.innerHTML = '';
  for (const [name, f] of Object.entries(DATEN.formate)) {
    const label = document.createElement('label');
    label.title = f.zweck;
    const kasten = document.createElement('input');
    kasten.type = 'checkbox';
    kasten.value = name;
    kasten.checked = stand.ausgaben.includes(name);
    kasten.addEventListener('change', () => {
      stand.ausgaben = [...behaelter.querySelectorAll('input:checked')].map((k) => k.value);
      neuZeichnen();
    });
    label.append(kasten, document.createTextNode(` ${name} (${f.breite}×${f.hoehe})`));
    behaelter.append(label);
  }
}

const FELDER = {
  haken: [['titel', 'Titel', 3], ['unterzeile', 'Unterzeile', 2]],
  inhalt: [['kopf', 'Kopfzeile', 1], ['text', 'Text', 5], ['quelle', 'Quelle', 1]],
  frage: [['kopf', 'Kopfzeile', 1], ['text', 'Frage', 3]],
  zitat: [['text', 'Zitat', 4], ['herkunft', 'Herkunft', 1]],
  ende: [['merksatz', 'Merksatz', 3], ['abbinder', 'Abbinder', 1]],
};

function zeichneSlides() {
  const behaelter = $('slides');
  behaelter.innerHTML = '';
  stand.slides.forEach((slide, i) => {
    const karte = document.createElement('div');
    karte.className = 'slide';

    const kopf = document.createElement('div');
    kopf.className = 'slide-kopf';
    kopf.innerHTML = `<span class="nummer">${String(i + 1).padStart(2, '0')}</span>`;

    const wahl = document.createElement('select');
    for (const typ of Object.keys(FELDER)) {
      const o = document.createElement('option');
      o.value = typ; o.textContent = typ; o.selected = (slide.typ || 'inhalt') === typ;
      wahl.append(o);
    }
    wahl.addEventListener('change', () => {
      stand.slides[i] = { typ: wahl.value };
      neuZeichnen(); zeichneSlides();
    });

    const fueller = document.createElement('span');
    fueller.className = 'fuellen';

    const hoch = knopf('↑', () => tauschen(i, i - 1));
    const runter = knopf('↓', () => tauschen(i, i + 1));
    const weg = knopf('✕', () => {
      if (stand.slides.length > 1) { stand.slides.splice(i, 1); neuZeichnen(); zeichneSlides(); }
    });
    kopf.append(wahl, fueller, hoch, runter, weg);
    karte.append(kopf);

    for (const [feld, beschriftung, zeilen] of FELDER[slide.typ || 'inhalt']) {
      const label = document.createElement('label');
      label.textContent = beschriftung;
      const eingabe = document.createElement('textarea');
      eingabe.rows = zeilen;
      eingabe.value = slide[feld] || '';
      eingabe.addEventListener('input', () => {
        stand.slides[i][feld] = eingabe.value;
        neuZeichnen();
      });
      label.append(eingabe);
      karte.append(label);
    }
    behaelter.append(karte);
  });
}

function knopf(zeichen, tun) {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'leise'; b.textContent = zeichen;
  b.addEventListener('click', tun);
  return b;
}

function tauschen(a, b) {
  if (b < 0 || b >= stand.slides.length) return;
  [stand.slides[a], stand.slides[b]] = [stand.slides[b], stand.slides[a]];
  neuZeichnen(); zeichneSlides();
}

// -------------------------------------------------------------- Job-Ausgabe
function jobDatei() {
  const daten = {
    id: stand.kennung || 'ohne-kennung',
    marke: stand.marke,
    ausgaben: stand.ausgaben.length ? stand.ausgaben
      : (DATEN.marken[stand.marke]?.standardformate || ['karussell']),
    slides: stand.slides.map((s) => {
      const sauber = { typ: s.typ || 'inhalt' };
      for (const [feld] of FELDER[s.typ || 'inhalt']) {
        if (s[feld] && String(s[feld]).trim()) sauber[feld] = s[feld];
      }
      return sauber;
    }),
  };
  if (stand.rubrik) daten.rubrik = stand.rubrik;
  if (stand.termin) daten.termin = `${stand.termin}:00`;
  if (stand.caption) daten.caption = stand.caption;
  return JSON.stringify(daten, null, 2);
}

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function neuZeichnen() {
  const text = jobDatei();
  $('ausgabe').value = text;

  const klagen = [];
  if (!stand.kennung) klagen.push('Es fehlt die Kennung.');
  else if (!SLUG.test(stand.kennung)) klagen.push('Die Kennung muss klein und mit Bindestrichen sein, ohne Umlaute.');
  if (!stand.ausgaben.length) klagen.push('Kein Format gewählt — es gilt die Vorgabe der Marke.');

  const ziel = `https://github.com/${REPO}/new/${ZWEIG}?` + new URLSearchParams({
    filename: `jobs/${stand.kennung || 'neuer-job'}.json`, value: text,
  });
  const knopfAnlegen = $('anlegen');
  knopfAnlegen.href = ziel;

  // GitHubs Editor nimmt die Vorbelegung ueber die Adresse entgegen, und
  // Adressen haben eine praktische Obergrenze. Bei langen Beitraegen bleibt
  // der Weg ueber die Zwischenablage.
  const zuLang = ziel.length > 7500;
  knopfAnlegen.setAttribute('aria-disabled', String(zuLang || !SLUG.test(stand.kennung || '')));

  const hinweis = $('hinweis');
  if (zuLang) {
    klagen.push('Der Beitrag ist zu lang für den Weg über die Adresse — nimm die Zwischenablage und lege die Datei unter jobs/ an.');
  }
  hinweis.textContent = klagen.join(' ');
  hinweis.className = 'hinweis' + (klagen.length ? ' warnung' : '');

  zeichneVorschau();
}

// ---------------------------------------------------------------- Vorschau
/* Die Vorschau wird bei jedem Tastendruck neu gebaut. Ein einfacher Riegel
 * ("laeuft schon, also nichts tun") wuerde den jeweils letzten Aufruf
 * verschlucken - und genau der traegt den zuletzt getippten Buchstaben.
 * Deshalb wird stattdessen gebuendelt: waehrend eines Laufs eingehende
 * Anforderungen setzen eine Marke, die am Ende einen Nachlauf ausloest. */
let vorschauLaeuft = false;
let nochmal = false;
async function zeichneVorschau() {
  if (vorschauLaeuft) { nochmal = true; return; }
  vorschauLaeuft = true;
  try {
    const formatName = $('format').value;
    const format = DATEN.formate[formatName];
    if (!format) return;

    const welche = $('welche');
    const vorher = Number(welche.value) || 1;
    welche.innerHTML = '';
    stand.slides.forEach((_, i) => {
      const o = document.createElement('option');
      o.value = String(i + 1); o.textContent = `Slide ${i + 1}`;
      welche.append(o);
    });
    const nummer = Math.min(Math.max(vorher, 1), stand.slides.length);
    welche.value = String(nummer);

    const rahmen = $('rahmen');
    const buehne = rahmen.parentElement;
    const platz = buehne.clientWidth - 24;
    const massstab = Math.min(platz / format.breite, 620 / format.hoehe);

    const quelltext = await vorschauSeite(
      stand.slides[nummer - 1], nummer, stand.slides.length,
      stand.marke, formatName, massstab);

    rahmen.style.width = `${Math.round(format.breite * massstab)}px`;
    rahmen.style.height = `${Math.round(format.hoehe * massstab)}px`;
    rahmen.srcdoc = quelltext;
  } finally {
    vorschauLaeuft = false;
    if (nochmal) { nochmal = false; zeichneVorschau(); }
  }
}

// ------------------------------------------------------------------- Start
async function start() {
  DATEN = await (await fetch('daten.json')).json();

  const markenWahl = $('marke');
  for (const name of Object.keys(DATEN.marken)) {
    const o = document.createElement('option');
    o.value = name; o.textContent = `${name} — ${DATEN.marken[name].anzeigename}`;
    markenWahl.append(o);
  }
  stand.marke = markenWahl.value;
  stand.ausgaben = [...(DATEN.marken[stand.marke].standardformate || [])];

  const formatWahl = $('format');
  for (const name of Object.keys(DATEN.formate)) {
    const o = document.createElement('option');
    o.value = name; o.textContent = name;
    formatWahl.append(o);
  }
  formatWahl.value = stand.ausgaben[0] || 'karussell';

  markenWahl.addEventListener('change', () => {
    stand.marke = markenWahl.value;
    stand.ausgaben = [...(DATEN.marken[stand.marke].standardformate || [])];
    zeichneAusgaben(); neuZeichnen();
  });
  formatWahl.addEventListener('change', zeichneVorschau);
  $('welche').addEventListener('change', zeichneVorschau);

  for (const [kennung, feld] of [['kennung', 'kennung'], ['rubrik', 'rubrik'],
                                 ['termin', 'termin'], ['caption', 'caption']]) {
    $(kennung).addEventListener('input', (e) => { stand[feld] = e.target.value; neuZeichnen(); });
  }

  $('slide-dazu').addEventListener('click', () => {
    stand.slides.splice(stand.slides.length - 1, 0,
      { typ: 'inhalt', kopf: '', text: '' });
    neuZeichnen(); zeichneSlides();
  });

  $('kopieren').addEventListener('click', async () => {
    await navigator.clipboard.writeText($('ausgabe').value);
    const b = $('kopieren');
    const alt = b.textContent;
    b.textContent = 'Kopiert';
    setTimeout(() => { b.textContent = alt; }, 1400);
  });

  window.addEventListener('resize', zeichneVorschau);

  zeichneAusgaben();
  zeichneSlides();
  neuZeichnen();
}

start().catch((fehler) => {
  document.body.insertAdjacentHTML('afterbegin',
    `<p class="hinweis warnung" style="padding:16px">Die Oberfläche konnte nicht starten: ${fehler.message}</p>`);
});
