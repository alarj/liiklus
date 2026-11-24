# Tallinna liikluse tuvastuse API ja UI

## 1. Dokumendi päritolu

Dokumendi koostas OpenAI Codex 23. novembril 2026 kasutaja lähteülesande ja
tehniliste otsuste põhjal.

## 2. Sisukord

- [3. Ülevaade](#3-ülevaade)
- [4. Eeldused](#4-eeldused)
- [5. Seadistus ja käivitamine](#5-seadistus-ja-käivitamine)
- [6. API kasutamine](#6-api-kasutamine)
- [7. UI kasutamine](#7-ui-kasutamine)
- [8. Sisendi piirangud](#8-sisendi-piirangud)
- [9. Piltide ja mudeli säilitamine](#9-piltide-ja-mudeli-säilitamine)
- [10. Autentimise kavand](#10-autentimise-kavand)
- [11. Keskkonnamuutujad](#11-keskkonnamuutujad)
- [12. Testid](#12-testid)
- [13. Praegune kontrollimise seis](#13-praegune-kontrollimise-seis)

## 3. Ülevaade

FastAPI rakendus loendab JPEG- või PNG-pildilt ONNX-mudeliga busse, autosid
ja tramme. API tagastab JSON-vastuse; visualiseeringu otspunkt lisab samasse
vastusesse Base64-kujul tuvastuskastidega JPEG-pildi.

Eraldi `liiklus-ui` konteiner serveerib staatilist HTML-, CSS- ja
JavaScript-liidest. UI saadab ühe pildi korraga olemasolevale
`POST /api/detect/image` otspunktile ning ei teosta tuvastus- ega
loendusloogikat brauseris uuesti.

Otspunktid:

- `GET /api/health`
- `POST /api/detect`
- `POST /api/detect/image`
- `GET /api/docs`

## 4. Eeldused

- Docker koos Compose'i toega.
- Olemasolev väline Docker-võrk `funo_net`.
- Mudelifail `models/best.onnx`; mudelifaile Git-is ei hoita.

Mudeli praegune SHA-256 kontrollsumma on:

```text
9675b647b2a7e27480a08e97574eb76a04bb0e3af74fa5de8de0cf782f8cc3cb
```

## 5. Seadistus ja käivitamine

Loo lokaalne keskkonnafail näidise põhjal, kui `.env` puudub:

```bash
cp .env.example .env
```

Ehita ja käivita konteiner:

```bash
docker compose up --build --detach
```

Kohalik API aadress on `http://127.0.0.1:8010`. Avalik nginx suunab
`https://liiklus.fun-o.eu/` UI konteinerile ja `/api/` API konteinerile.
Mõlemad konteinerid kasutavad välist Docker-võrku `funo_net`.

Konteineri peatamine:

```bash
docker compose down
```

## 6. API kasutamine

Health:

```bash
curl http://127.0.0.1:8010/api/health
```

JSON-tuvastus:

```bash
curl -X POST \
  "http://127.0.0.1:8010/api/detect?conf=0.45" \
  -H "accept: application/json" \
  -F "file=@/tee/pildini.jpg;type=image/jpeg"
```

JSON koos märgendatud JPEG-iga:

```bash
curl -X POST \
  "http://127.0.0.1:8010/api/detect/image?conf=0.45" \
  -H "accept: application/json" \
  -F "file=@/tee/pildini.jpg;type=image/jpeg"
```

Mõlemad tuvastusotspunktid tagastavad UTC-välja `request_received_at`,
millisekundites `processing_duration_ms`, kliendi antud failinime `filename`,
tegelikult kasutatud usalduslävendi `conf`, pildi mõõdud, klasside loendused ja
tuvastused. `/api/detect/image` lisab
objekti `annotated_image`, mille `media_type` on `image/jpeg` ja `base64`
sisaldab märgendatud JPEG-i. Sisendpilt saadetakse mõlemale otspunktile
tavalise `multipart/form-data` failina, mitte Base64-kujul. Ühe päringu jooksul
käivitatakse mudel üks kord.

## 7. UI kasutamine

UI võimaldab valida või lohistada ühe JPEG- või PNG-pildi, vaadata algpildi
eelvaadet ning saata pildi API-le. Usalduslävendi võib jätta tühjaks; sel juhul
kasutab API oma vaikeväärtust. Samuti võib sisestada väärtuse vahemikus `0`
kuni `1`.

UI nimetab parameetrit tuvastuslävendiks ja kuvab selgituses API
vaikeväärtuse. `liiklus-ui` konteiner saab väärtuse Compose'i kaudu samast
`MODEL_CONFIDENCE_THRESHOLD` keskkonnamuutujast; brauser ei otsusta ise API
vaikeväärtust.

Tulemusvaade kasutab ainult API vastust ja kuvab:

- märgendatud JPEG-pildi;
- API tagastatud klasside loendused ja koguarvu;
- pildi mõõdu, kasutatud lävendi, töötlusaja ja päringu aja;
- üksikud tuvastused koos usaldusväärtuste ja koordinaatidega;
- eraldi modalis vormindatud JSON-vastuse, millest eemaldatakse kuvamise ajaks
  `annotated_image.base64`. Märgendatud pilt kuvatakse tavavaates. Modali
  ikoonnupp laadib sama, ilma Base64-väljata JSON-i `.json` failina alla.

UI tekstid asuvad failis `ui/assets/i18n/et.json`. Kujundus lähtub
TTÜ-loengu projekti värvidest, tüpograafiast, kaartidest ja vormielementidest;
UI CSS jääb eraldi faili `ui/assets/app.css`.

## 8. Sisendi piirangud

- Lubatud MIME-tüübid: `image/jpeg` ja `image/png`.
- Maksimaalne failisuurus: 5 MiB ehk 5 242 880 baiti.
- Maksimaalne pikslite arv: 10 000 000.
- `conf` on mudeli tuvastuse minimaalne usalduslävend. Selle lubatud vahemik
  on `0.0` kuni `1.0` ja vaikeväärtus `0.45`.

## 9. Piltide ja mudeli säilitamine

Üleslaetud pilte ei kirjutata projekti, andmebaasi ega püsivasse volume'isse.
Päringu ajal võib FastAPI kasutada operatsioonisüsteemi ajutist puhvrit, mis
suletakse päringu lõppedes. Märgendatud vastus kodeeritakse mälus.

Mudelifail ühendatakse konteinerisse kirjutuskaitstud failina:
`./models/best.onnx:/app/models/best.onnx:ro`.

## 10. Autentimise kavand

Praeguses etapis ei ole API-l ega UI-l autentimist. `GET /api/health` jääb ka
pärast autentimise lisamist avalikuks.

Tulevikus lisatakse UI-le Google'i OIDC-autentimine; eraldi kasutajanime ja
parooliga sisselogimist ei tehta. Brauser kasutab serveripoolset turvalist
sessiooniküpsist. Google'i tokenit ega API mandaati ei salvestata UI
JavaScripti ega `localStorage`'isse.

UI ja väliste API klientide autentimine jäävad eraldi usalduspiirideks.
Google'iga autenditud UI päringud saab suunata serveripoolse `/ui-api/`
vahenduse kaudu samadele olemasolevatele `/api/` otspunktidele. Avaliku API
Basic- või Bearer-autentimise otsus tehakse hiljem; eelistatud suund on
Bearer, kuid seda ei rakendata käesolevas etapis.

Kõik UI API-kõned on koondatud ühte JavaScripti funktsiooni ja API baastee
ühte konstanti, et tulevane `/api` -> `/ui-api` üleminek ei mõjutaks muud UI
loogikat.

## 11. Keskkonnamuutujad

| Muutuja | Vaikeväärtus | Tähendus |
| --- | ---: | --- |
| `MODEL_PATH` | `/app/models/best.onnx` | ONNX-mudeli asukoht konteineris |
| `ORT_INTRA_OP_NUM_THREADS` | `3` | ONNX Runtime'i operaatorite arvutuslõimed |
| `MODEL_CONFIDENCE_THRESHOLD` | `0.45` | Mudeli usalduslävendi vaikeväärtus |
| `MAX_UPLOAD_BYTES` | `5242880` | Pildifaili maksimaalne suurus baitides |
| `MAX_IMAGE_PIXELS` | `10000000` | Pildi maksimaalne pikslite arv |

## 12. Testid

Automatiseeritud testid asuvad failis `tests/test_app.py`. Testid ei kuulu
tootmisimage'isse ega käivitu API ehitamisel või käivitamisel. Neid
käivitatakse ainult siis, kui kasutaja või väline vastuvõtukriteerium seda
sõnaselgelt nõuab. Nõutud testide käsk on:

```bash
docker compose --profile testing run --rm testing
```

## 13. Praegune kontrollimise seis

Tootmis-API ja eraldi `liiklus-ui` konteiner töötavad. Avalik nginx suunab
`https://liiklus.fun-o.eu/` UI-le ning `/api/` API-le; avalik health vastab
ootuspäraselt. UI image, konteineri nginx, ühine nginx ja avalikud põhifailid
on kontrollitud.

API 7 automatiseeritud testi läbisid ajutise `PYTHONPATH=/app` keskkonnaga.
Dokumenteeritud testikäsul puudub testikonteineris püsiv `PYTHONPATH`, mistõttu
see vajab enne parandamist eraldi otsust. Serveris polnud automatiseeritud
visuaalkontrolliks Chromiumit ega Playwrighti. Täpsed tulemused ja piirangud on
failis [`docs/testid.md`](docs/testid.md).
