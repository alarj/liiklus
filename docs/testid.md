# Tallinna liikluse tuvastuse API minimaalne testiplaan

## 1. Dokumendi päritolu

Dokumendi koostas OpenAI Codex 23. novembril 2026 kasutaja nõudel. Testiplaan
on teadlikult minimaalne ja vajab enne käivitamist kasutaja heakskiitu.

## 2. Sisukord

- [3. Käivitamise tingimus](#3-käivitamise-tingimus)
- [4. Testide teostuse seis](#4-testide-teostuse-seis)
- [5. Kavandatud kontrollid](#5-kavandatud-kontrollid)
- [6. Käivitamise sagedus](#6-käivitamise-sagedus)
- [7. Tulemuste talletamine](#7-tulemuste-talletamine)
- [8. Käivitatud kontrollid](#8-käivitatud-kontrollid)

## 3. Käivitamise tingimus

Ühtegi allpool kirjeldatud käsku, testi ega testpäringut ei käivitata enne,
kui kasutaja on selle dokumendi üle vaadanud ja andnud eraldi selgesõnalise
loa. Testid ei tohi muuta andmebaasi ega muid püsivaid andmeid.

## 4. Testide teostuse seis

Automatiseeritud testikood asub failis `tests/test_app.py`. Testid ehitatakse
eraldi Docker image'i sihtmärki ja neid saab käivitada ainult Compose'i
`testing` profiiliga. Tootmis-API ehitamine või käivitamine teste automaatselt
ei käivita. Automatiseeritud testikomplekti pole veel käivitatud. Kasutaja
loal tehtud pärispildi kontroll on kirjas jaotises 8.

## 5. Kavandatud kontrollid

1. **Konteiner ja health.** Ehitada ning käivitada `liiklus-api`; kontrollida,
   et `GET /api/health` vastab HTTP 200 ja `{"status":"ok"}`.
2. **Eeltöötlus ja sisendi piirid.** Kontrollida, et mudeli sisendmõõtu mahtuv
   pilt säilitab algse mõõdu ning saab täite ainult paremale ja alla. Kontrollida,
   et suurem pilt skaleeritakse kuvasuhet hoides mõõtu `1152 × 576` mahtuvaks.
   Kontrollida ühe näitega ka seda, et vale failivorming, üle 5 MiB fail ja üle
   10 000 000 piksliga pilt lükatakse tagasi.
3. **Pärispildi JSON.** Saata kasutaja antud JPEG- või PNG-pilt otspunktile
   `POST /api/detect`; kontrollida UTC ajatemplit, töötluskestust, failinime,
   tegelikult kasutatud `conf` väärtust, klassinimesid, koordinaate ja
   `X-Model-SHA256` päist.
4. **Pärispildi visualiseering.** Saata sama pilt otspunktile
   `POST /api/detect/image`; kontrollida, et vastus sisaldab sama tuvastuse
   JSON-i ning `annotated_image.base64` dekodeerub avatavaks JPEG-iks, mille
   kastid vastavad vastuse tuvastustele. Kontrollida, et päringu jooksul
   tehakse ainult üks mudeli inferents.

Automatiseeritud testid katavad punktid 1 ja 2 ning punktide 3 ja 4 API lepingu
sünteetilise pildiga. Pärispildi sisuline tulemus kontrollitakse eraldi pärast
kasutajalt testpildi saamist.

## 6. Käivitamise sagedus

Teste ei käivitata automaatselt pärast iga muudatust. Iga muudatuse järel
valitakse ainult selle muudatusega seotud kontrollid. Kogu testiplaan on
mõeldud esimese tervikliku juurutuse kontrolliks või olukorraks, kus muutub
inferents, pildi eeltöötlus, API leping või konteineri käitus. Iga testide
käivitamine vajab kasutaja eraldi luba.

## 7. Tulemuste talletamine

Pärast loa saamist märgitakse iga kontrolli juurde kuupäev, kasutatud sisend,
tulemus ja võimalik kõrvalekalle. Pärispilte Git-i ega andmebaasi ei lisata.

## 8. Käivitatud kontrollid

### 23. november 2026 — pärispildi API kontroll

- Sisend: kasutaja antud JPEG, `1150 × 550`, 205 016 baiti.
- Sisendi SHA-256:
  `be0181040b8dce1b5e3c104090ebad6cb608ec09d7e37fc40394a9398475c68f`.
- Käivituskeskkond: avalik API `https://liiklus.fun-o.eu`, mudeli
  vaike-lävend `conf=0.45`.
- `POST /api/detect`: HTTP 200, JSON-i pildimõõt vastas sisendile ning
  tuvastati kolm autot; kõik kolm kasti paiknesid visuaalselt autodel.
- `POST /api/detect/image`: HTTP 200, vastus oli avatav `1150 × 550` JPEG ja
  selle kolm märgendatud kasti vastasid JSON-vastusele.
- Mõlema vastuse `X-Model-SHA256` oli
  `9675b647b2a7e27480a08e97574eb76a04bb0e3af74fa5de8de0cf782f8cc3cb`.
- Kõrvalekalle: pildil nähtav tramm jäi mudelil vaike-lävendiga tuvastamata;
  API tagastas `tram: 0`. See ei ole API-lepingu viga, kuid vajab mudeli
  täpsuse hindamisel eraldi arvestamist.
- Märkus: see kontroll tehti enne `/api/detect/image` vastuse muutmist
  JSON-iks, mis sisaldab märgendatud JPEG-i Base64-kujul. Uue lepingu
  testikood on lisatud, kuid seda pole veel käivitatud.

### 23. november 2026 — pärispilt lävendiga 0.25

- Sama testpilt saadeti ühe päringuga avalikule otspunktile
  `POST /api/detect/image?conf=0.25`.
- Pärast `conf` vastusevälja lisamist korratud päring vastas HTTP 200; API
  mõõdetud töötluskestus oli 540,781 ms ja JSON tagastas `"conf": 0.25`.
- JSON tagastas kolm autot ja ühe trammi. Trammi usaldusväärtus oli
  `0.272187` ning kast `[365, 310, 784, 450]` paiknes visuaalselt trammil.
- `annotated_image.base64` dekodeerus kehtivaks `1150 × 550` JPEG-pildiks.
- Vastuse `Content-Type` oli `application/json` ja `X-Model-SHA256` oli
  `9675b647b2a7e27480a08e97574eb76a04bb0e3af74fa5de8de0cf782f8cc3cb`.
