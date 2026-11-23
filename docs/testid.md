# Tallinna liikluse tuvastuse API ja UI minimaalne testiplaan

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

Allpool kirjeldatud teste käivitatakse ainult siis, kui kasutaja või ülesande
väline vastuvõtukriteerium seda sõnaselgelt nõuab. Teste ei käivitata
automaatselt ega tavapärase muudatuse osana. Testid ei tohi muuta andmebaasi
ega muid püsivaid andmeid.

## 4. Testide teostuse seis

API automatiseeritud testikood asub failis `tests/test_app.py`. Testid ehitatakse
eraldi Docker image'i sihtmärki ja neid saab käivitada ainult Compose'i
`testing` profiiliga. Tootmis-API ehitamine või käivitamine teste automaatselt
ei käivita. API automatiseeritud testikomplekt käivitati 23. novembril 2026;
tulemus on kirjas jaotises 8. Samas jaotises on UI ehitamise,
nginx-liidestuse ja avalike HTTP-vastuste kontrollid.

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
5. **UI staatilised kontrollid.** Kontrollida HTML-i, CSS-i, JavaScripti,
   eestikeelse tõlkefaili ja UI nginx-konfiguratsiooni süntaksit ning kinnitada,
   et UI Docker image ehitub eraldi `liiklus-ui` konteineriks.
6. **UI põhitöövoog.** Avada UI laua- ja mobiilivaates, valida ning lohistada
   pilt, teha päring API vaike-lävendiga ja kasutaja antud lävendiga ning
   kontrollida laadimis-, vea- ja tulemusolekuid. Kinnitada, et tulemus kasutab
   API tagastatud märgendatud pilti ja loendusi.
7. **JSON-modal.** Avada tulemuse JSON-modal ja kinnitada, et ülejäänud API
   vastus on vormindatult nähtav, kuid `annotated_image.base64` puudub.
   Kinnitada, et märgendatud pilt on samal ajal põhitulemuses nähtav.
8. **Proxy ja avalik health.** Kontrollida, et avalik nginx suunab `/` UI-le,
   `/api/` API-le ning `GET /api/health` jääb avalikult kättesaadavaks.

Automatiseeritud testid katavad punktid 1 ja 2 ning punktide 3 ja 4 API lepingu
sünteetilise pildiga. Punktid 5–8 kontrollivad UI-d ja selle liidestust.
Pärispildi sisuline tulemus kontrollitakse eraldi pärast kasutajalt testpildi
saamist.

## 6. Käivitamise sagedus

Teste ei käivitata automaatselt pärast muudatusi. Kui testimist sõnaselgelt
nõutakse, valitakse ainult muudatusega seotud kontrollid. Kogu testiplaan on
mõeldud nõutud tervikliku juurutuse kontrolliks või olukorraks, kus tuleb
eraldi kontrollida inferentsi, pildi eeltöötlust, API lepingut või konteineri
käitust.

## 7. Tulemuste talletamine

Pärast loa saamist märgitakse iga kontrolli juurde kuupäev, kasutatud sisend,
tulemus ja võimalik kõrvalekalle. Pärispilte Git-i ega andmebaasi ei lisata.

## 8. Käivitatud kontrollid

### 23. november 2026 — UI ehitus ja juurutus

- `ui/assets/app.js` läbis Node.js-i süntaksikontrolli.
- `ui/assets/i18n/et.json` läbis JSON-süntaksikontrolli.
- `docker compose config --quiet` ja muudatuste whitespace-kontroll õnnestusid.
- `liiklus-ui` Docker image ehitus õnnestus ja konteiner käivitus.
- UI konteineri nginx-konfiguratsioon läbis `nginx -t` kontrolli ning
  konteineri `GET /health` vastas `ok`.
- Ühise avaliku nginx-konteineri konfiguratsioon läbis `nginx -t` kontrolli
  ja konfiguratsioon laaditi katkestuseta uuesti.
- `https://liiklus.fun-o.eu/`, eraldi CSS ja eestikeelne tõlkefail vastasid
  HTTPS 200-ga. Avalik `GET /api/health` vastas HTTP 200 ja
  `{"status":"ok"}`.
- Serveris polnud Chromiumit ega Playwrighti. Seetõttu ei tehtud
  automatiseeritud visuaalset laua- ja mobiilivaate kontrolli ega JSON-modali
  brauseriinteraktsiooni kontrolli; need vajavad käsitsi brauserikontrolli või
  eraldi brauserisõltuvuse paigaldamise kokkulepet.

### 23. november 2026 — API automatiseeritud testid

- Dokumenteeritud käsk `docker compose --profile testing run --rm testing`
  peatus testide kogumisel veaga `ModuleNotFoundError: No module named 'app'`,
  sest testikonteineri Python path ei sisalda püsivalt `/app` kataloogi.
- Sama testikood käivitati diagnoosimiseks muutmata kujul ajutise
  `PYTHONPATH=/app` keskkonnaga. Kõik 7 testi läbisid kontrolli 1,73 sekundiga.
- Testiväljundis oli üks FastAPI/Starlette'i `httpx` kasutuse
  deprekatsioonihoiatus. See ei põhjustanud testi ebaõnnestumist.
- Testikonteineri püsivat `PYTHONPATH` seadistust ei muudetud, sest see
  kõrvalekalle avastati UI töö käigus ja vajab enne parandamist eraldi otsust.

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
