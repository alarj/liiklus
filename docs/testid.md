# Tallinna liikluse tuvastuse API ja UI minimaalne testiplaan

## 1. Dokumendi päritolu

Dokumendi koostas OpenAI Codex 23. novembril 2026 kasutaja nõudel ja täiendas
26. novembril 2026 klassideülese duplikaadifiltri ning 27. novembril 2026
kaameraprofiilide aluskihi kontrollidega. Testiplaan on teadlikult minimaalne
ja vajab enne käivitamist kasutaja heakskiitu.

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
   tegelikult kasutatud `conf` ja `model` väärtust, klassinimesid, koordinaate,
   `model_sha256` välja ja `X-Model-SHA256` päist. Kontrollida vaikemudelit,
   teise lubatud mudeli valikut ja tundmatu mudeli tagasilükkamist.
4. **Pärispildi visualiseering.** Saata sama pilt otspunktile
   `POST /api/detect/image`; kontrollida, et vastus sisaldab sama tuvastuse
   JSON-i ning `annotated_image.base64` dekodeerub avatavaks JPEG-iks, mille
   kastid vastavad vastuse tuvastustele. Kontrollida, et API JPEG ei sisalda
   ROI joont ega tumendust. ROI-maskiga profiili korral kontrollida UI-s, et
   maski polügooni piir on nähtav punase katkendjoonena ja välisala on veidi
   tumendatud; lüliti peab peitma mõlemad ning uue pildi valik need taastama.
   ROI-polügoonita profiili korral ei kuvata lülitit. Kontrollida, et päringu jooksul
   tehakse ainult üks mudeli inferents. Võrrelda ligikaudu 1152 px ja 4000 px
   laiust pilti ning kontrollida, et UI-s vähendatud pildil säilivad kastide ja
   klassitekstide võrreldav loetavus.
5. **Klassideülene duplikaadifilter.** Kontrollida, et peaaegu identsest eri
   klassi kastipaarist jääb alles kõrgema confidence'iga kast, madala IoU-ga
   eri klassi kastid ja sama klassi kastid jäävad alles ning täpselt lävendiga
   võrdne kattuvus eemaldatakse. Kontrollida filtri välja lülitamist, `.env`
   vaikeväärtusi, ainult `0` ja `1` lubavat API sisendit, lävendi tingimuslikku
   sisendit ja väljundit ning sama lepingu kasutamist treeningukandidaadil.
6. **UI staatilised kontrollid.** Kontrollida HTML-i, CSS-i, JavaScripti,
   eestikeelse tõlkefaili ja UI nginx-konfiguratsiooni süntaksit ning kinnitada,
   et UI Docker image ehitub eraldi `liiklus-ui` konteineriks. Kontrollida, et
   duplikaadifiltri lüliti ja tingimuslik lävendiväli on olemas ning mõlemad
   väärtused edastatakse analüüsi- ja treeningukandidaadi päringutesse.
7. **UI põhitöövoog.** Avada UI laua- ja mobiilivaates, valida ning lohistada
   pilt, teha päring API vaike-lävendiga ja kasutaja antud lävendiga ning
   kontrollida laadimis-, vea- ja tulemusolekuid. Kinnitada, et tulemus kasutab
   API tagastatud märgendatud pilti ja loendusi. Kontrollida mudelivaliku
   püsimist uue pildi valimisel, kolme taseme linnukese lähtestamist ning seda,
   et treeningukandidaat märgendatakse valitud mudeliga.
   Kontrollida, et Oracle'i UTC-ajatemplid kuvatakse brauseri kohalikus
   ajavööndis. Kontrollida, et väljalülitatud duplikaadifilter peidab lävendi
   sisendi ja tulemuste lävendi rea, sisselülitatud filter kuvab mõlemad ning
   tulemuste leht kasutab API vastuses tagastatud väärtusi. Kontrollida, et
   analüüsi väljad, lülitid ja tegevusnupud ei kattu laua-, kitsas- ega
   mobiilivaates. Kontrollida switch'ide klaviatuurifookust ja oleku muutumist,
   tegevusnuppude paiknemist pildiala kohal ning IoU välja ilmumist vahetult
   duplikaadifiltri switch'i järel.
8. **JSON-modal.** Avada tulemuse JSON-modal ja kinnitada, et ülejäänud API
   vastus on vormindatult nähtav, kuid `annotated_image.base64` puudub.
   Kinnitada, et märgendatud pilt on samal ajal põhitulemuses nähtav.
9. **Proxy ja avalik health.** Kontrollida, et avalik nginx suunab `/` UI-le,
   `/api/` API-le ning `GET /api/health` jääb avalikult kättesaadavaks.
10. **Kaameraprofiilide aluskiht.** Kontrollida, et profiilide mudelijärjestus
    säilib, täpselt üks aktiivne profiil peab olema vaikimisi ning mudeli
    fikseeritud kõrgus ja laius loetakse ONNX sisendkujust. Kontrollida, et
    dünaamiline kõrgus või laius lükatakse tagasi, ROI-mask täidab polügooni
    välise ala määratud värviga ja `1280 × 720` pilt moodustab `1280 × 736`
    lõuendil koos maski ning alumise halli täitega õige tensori. Kontrollida ka
    olemasoleva vaikeprofiili API regressiooni.

Automatiseeritud testid katavad punktid 1 ja 2, punktide 3 ja 4 API lepingu
sünteetilise pildiga ning punkti 5 järeltöötluse ja API lepingu. Staatilised
UI-testid katavad punkti 6 struktuuri ja päringuparameetrid. Punktid 7–9
kontrollivad UI-d ja selle liidestust.
Pärispildi sisuline tulemus kontrollitakse eraldi pärast kasutajalt testpildi
saamist. Punkti 10 automatiseeritud ühiktestid ei ühendu Oracle'iga ega muuda
andmeid. Migratsiooniskripti ei käivitata testide osana.

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

### 27. november 2026 — profiilivalik ja kahe profiili pärispildid

- Staatilised Python-, JavaScripti- ja diffikontrollid läbisid kontrolli.
- Värske test-image'iga läbisid kõik 22 automatiseeritud testi kontrolli
  2,31 sekundiga. Testiväljundis oli kaks mittekriitilist
  deprekatsioonihoiatust.
- API ja UI image'id ehitati uuesti ning konteinerid loodi värske koodiga.
- Päris Oracle'i JSON-väärtused tagastusid `Decimal` arvudena. Profiili
  validaatorit täiendati neid korrektselt normaliseerima ja regressioonitest
  lisati.
- Kasutaja antud `1280 × 720` `cam217` pilt saadeti töötavale otspunktile
  `POST /api/detect/image?profile=cam217`. Vastus oli HTTP 200, kasutas
  profiili `cam217`, mudelit `cam217 v2.onnx` ja lävendit 0,45 ning tagastas
  ühe bussi ja kuus autot. Annoteeritud pilt dekodeerus ja kastid paiknesid
  visuaalselt sõidukitel.
- Kasutaja antud `1150 × 550` Pärnu pilt saadeti nii profiiliparameetrita kui
  `profile=parnu-mnt-karja` parameetriga. Mõlemad HTTP 200 vastused kasutasid
  mudelit `best v3.onnx` ja tagastasid identselt kolm autot ning ühe trammi.
  Annoteeritud pilt dekodeerus ja kastid paiknesid visuaalselt sõidukitel.
- Testpilte ei lisatud projekti ega andmebaasi. API konteinerisse loodud
  ajutised koopiad olid ainult testi sisend- ja väljundfailid.

### 27. november 2026 — kaameraprofiilide aluskiht

- Kasutaja loal käivitati
  `docker compose --profile testing run --build --rm testing`.
- Kõik 21 testi läbisid kontrolli 2,68 sekundiga.
- Uued kontrollid hõlmasid vaikeprofiili nõuet, profiili mudelijärjestust,
  ROI-polügoonmaski, maski ja alumise halli täite moodustamist samal
  `1280 × 736` lõuendil ning ONNX-mudeli fikseeritud sisendmõõdu lugemist ja
  dünaamilise kõrguse või laiuse tagasilükkamist.
- Testid kasutasid fake-repository't. Oracle'iga ei ühendutud ja
  `db/schema/002_camera_profiles.sql` migratsiooni ei käivitatud.
- Testiväljundis oli kolm deprekatsioonihoiatust: üks FastAPI TestClienti
  `httpx` integratsiooni ja kaks Starlette'i HTTP 422 konstandi kohta.
  Hoiatused ei põhjustanud testide ebaõnnestumist.

### 26. november 2026 — klassideülene duplikaadifilter

- Esimene käsk `docker compose --profile testing run --rm testing` kasutas
  varasemat test-image'it ja käivitas ainult seitse vana testi; kõik seitse
  läbisid kontrolli.
- Värske koodi kontrollimiseks käivitati
  `docker compose --profile testing run --build --rm testing`.
- Kõik 14 testi läbisid kontrolli 2,03 sekundiga. Need hõlmasid
  klassideülese filtri järeltöötlust, API vaike- ja valideerimisreegleid ning
  UI staatilist lepingut.
- Testiväljundis oli kolm deprekatsioonihoiatust: üks FastAPI TestClienti
  `httpx` integratsiooni kohta ja kaks Starlette'i HTTP 422 konstandi kohta.
  Hoiatused ei põhjustanud testide ebaõnnestumist.

### 26. november 2026 — duplikaadifilter pärispildiga

- Sisend: kasutaja antud `IMG_20261126_102055.jpg`, `4000 × 2250`.
- Sisendi SHA-256:
  `9f23b70273fd8aded3bfecda50d641d0c0bceda1e3dc89411131f3b1de0d9165`.
- Mudel: `best v3.onnx`; confidence'i lävend `0.45`; klassideülese filtri
  IoU lävend `0.80`.
- Väljalülitatud filtriga tuvastati üks buss, üks auto ja kaks trammi.
- Sisselülitatud filtriga tuvastati null bussi, üks auto ja kaks trammi.
- Eemaldatud bussikast `[878, 826, 1510, 1126]` confidence'iga `0.692708`
  kattus trammikastiga `[876, 816, 1509, 1131]` confidence'iga `0.776678`;
  kastide standardne IoU oli ligikaudu `0.948`. Filter eemaldas madalama
  confidence'iga bussituvastuse ootuspäraselt.

### 26. november 2026 — API ja UI konteinerite uuendamine

- `liiklus-api` ja `liiklus-ui` image'id ehitati uuesti ning konteinerid loodi
  värske koodiga uuesti.
- Mõlemad konteinerid käivitusid olekus `Up`.
- API kohalik `GET /api/health` vastas `{"status":"ok"}` ja UI konteineri
  `GET /health` vastas `ok`.

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
