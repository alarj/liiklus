# Tallinna liikluse tuvastuse API ja UI

## 1. Dokumendi päritolu

Dokumendi koostas OpenAI Codex 23. novembril 2026 kasutaja lähteülesande ja
tehniliste otsuste põhjal ning täiendas 24. ja 27. novembril 2026 mitme mudeli
ja andmebaasipõhiste kaameraprofiilide kirjeldusega.

## 2. Sisukord

- [3. Ülevaade](#3-ülevaade)
- [4. Eeldused](#4-eeldused)
- [5. Seadistus ja käivitamine](#5-seadistus-ja-käivitamine)
- [6. API kasutamine](#6-api-kasutamine)
- [7. UI kasutamine](#7-ui-kasutamine)
- [8. Sisendi piirangud](#8-sisendi-piirangud)
- [9. Piltide ja mudeli säilitamine](#9-piltide-ja-mudeli-säilitamine)
- [10. Autentimine](#10-autentimine)
- [11. Keskkonnamuutujad](#11-keskkonnamuutujad)
- [12. Testid](#12-testid)
- [13. Kontrollimine](#13-kontrollimine)

## 3. Ülevaade

FastAPI rakendus loendab JPEG- või PNG-pildilt ONNX-mudeliga busse, autosid
ja tramme. API tagastab JSON-vastuse; visualiseeringu otspunkt lisab samasse
vastusesse Base64-kujul tuvastuskastidega JPEG-pildi.

„Kaamerate live view“ laadib URL-iga kaameraprofiili pilti sekundilise
intervalliga. Backend jätab sama SHA-256 räsiga pildi töötlemata ning saadab
muutunud pildi olemasolevasse `POST /api/detect/image` teenusesse.

Eraldi `liiklus-ui` konteiner serveerib Google'i sisselogimisega staatilist
liidest. UI kasutab sama FastAPI JSON API-t tuvastuseks, treeningukandidaatideks
ja treeningpakkideks.

Otspunktid:

- `GET /api/health`
- `POST /api/detect`
- `POST /api/detect/image`
- `GET /api/camera-profiles/{profile_code}/live-frame`
- `POST /api/camera-profiles/{profile_code}/live-viewers/{viewer_id}/pause`
- `POST /api/camera-profiles/{profile_code}/live-viewers/{viewer_id}/heartbeat`
- `POST /api/training-pool/live-frame`
- `/api/training-pool...`
- `/api/training-packages...`
- `GET /api/docs`

## 4. Eeldused

- Docker koos Compose'i toega.
- Olemasolev väline Docker-võrk `funo_net`.
- Andmebaasi aktiivsetes kaameraprofiilides nimetatud ONNX-mudelifailid;
  mudelifaile Git-is ei hoita.
- Oracle'i skeem on loodud skriptiga `db/schema/001_core_schema.sql`.
- Olemasoleva skeemi uuendamisel tuleb kasutaja loal rakendada
  `db/schema/002_camera_profiles.sql` ning live-vaate jaoks
  `db/schema/003_camera_profile_capture_interval.sql`.
- `TRAINING_POOL_DIR` kataloog on API konteineri kasutajale kirjutatav.

Kasutatava mudeli failinimi ja SHA-256 kontrollsumma tagastatakse iga
tuvastuspäringu vastuses.

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

Muud otspunktid nõuavad Google'i sisselogimisel loodud sessiooni. API leping
on OpenAPI vaates `/api/docs`.

Mõlemad tuvastusotspunktid tagastavad UTC-välja `request_received_at`,
millisekundites `processing_duration_ms`, kliendi antud failinime `filename`,
tegelikult kasutatud usalduslävendi `conf`, mudeli failinime `model`, mudeli
kontrollsumma `model_sha256`, pildi mõõdud, klasside loendused ja tuvastused.
Valikuline query-parameeter `profile` valib kaameraprofiili koodi järgi;
puudumisel kasutatakse andmebaasi aktiivset vaikeprofiili. Valikuline
`model` valib profiili mudelifaili; puudumisel kasutatakse profiili esimest
mudelit. Vastuse `profile` objekt näitab tegelikult kasutatud profiili.
`/api/detect/image` lisab
objekti `annotated_image`, mille `media_type` on `image/jpeg` ja `base64`
sisaldab tuvastuskastidega JPEG-i. ROI-polügooni ega piirkonna tumendust API
pildi pikslitesse ei lisata. Sisendpilt saadetakse mõlemale otspunktile
tavalise `multipart/form-data` failina, mitte Base64-kujul. Ühe päringu jooksul
käivitatakse mudel üks kord.

`GET /api/camera-profiles/{profile_code}/live-frame` laadib profiili
`source_image_url` pildi ja võrdleb selle SHA-256 räsi `previous_hash`
parameetriga. Muutumata pildi korral tagastatakse `204 No Content`. Muutunud
pilt saadetakse sisemiselt muutmata `POST /api/detect/image` lepingusse ning
vastusele lisatakse lähtepildi `image_sha256`. `viewer_id` seob puhta
originaali brauserivahekaardi kahe kaadri puhvriga. Sama profiili, räsi ja
tuvastusseadetega samaaegsed päringud jagavad ühte inferentsi.

Oracle'is on ajatemplite autoriteetne ajavöönd UTC. API märgib kõik Oracle'ist
loetud ajatemplid JSON-is UTC-na (`+00:00`); UI teisendab need brauseri
kohalikku ajavööndisse.

## 7. UI kasutamine

UI võimaldab valida aktiivse kaameraprofiili ja selle järjestatud nimekirjast
mudeli ning analüüsida pilti ühe lävendiga või kolme profiili vaikeväärtusest
tuletatud lävendiga. Kolme taseme tulemused kuvatakse kõrvuti ja kasutavad
sama valitud profiili ning mudelit.

Kui profiilis on ROI-polügoon, näitab UI tulemuspildil vaikimisi selle piiri
punase katkendjoonega ja tumendab veidi polügoonist väljapoole jäävat ala.
„Näita tuvastuspiirkonda“ lüliti peidab või kuvab mõlemad UI kuvakihid ilma
uut API päringut tegemata. Uue pildi valimisel lülitub kuvamine uuesti sisse;
ROI-polügoonita profiili korral lülitit ei näidata.

UI nimetab parameetrit tuvastuslävendiks ja kuvab selgituses API
vaikeväärtuse. `liiklus-ui` konteiner saab väärtuse Compose'i kaudu samast
`MODEL_CONFIDENCE_THRESHOLD` keskkonnamuutujast; brauser ei otsusta ise API
vaikeväärtust.

Uue pildi valimine eemaldab kolme taseme valiku, kuid säilitab kasutaja valitud
mudeli. Treeningukandidaadi eelmärgendus kasutab samuti kasutaja valitud mudelit.
Üksiktulemuses kuvatakse kasutatud mudel failinime ja muude metaandmete juures;
kolme taseme vaates kuvatakse see võrdlustabeli pealkirjas.

Treeninguvaates saab kandidaate otsida, kustutada, lisada unikaalse nimega
pakki ning paki Roboflow jaoks ZIP-ina alla laadida. Esimene allalaadimine
lukustab paki koosseisu. Kitsal ekraanil paigutuvad treeninguvaate filtrid,
pakivalikud ja tegevusnupud üksteise alla.

„Kaamerate live view“ vaates kuvatakse ainult `source_image_url` väärtusega
profiilid. Positiivse intervalliga seire uuendab annotatsioonipilti
automaatselt. `NULL` või 0 intervalli korral seire ei käivitu enne, kui kasutaja
sisestab positiivse täisarvu. ROI kasutab sama brauseripoolset SVG-overlayd
nagu ühe pildi vaade ja seda saab ilma uue API-päringuta näidata või peita.
Peatatud seire korral kuvatakse „Saada treeningusse“ nupp. Backend leiab
ekraanil oleva kaadri räsi järgi puhta originaali; brauser ei saada pilti
serverile tagasi.

## 8. Sisendi piirangud

- Lubatud MIME-tüübid: `image/jpeg` ja `image/png`.
- Maksimaalne failisuurus: 5 MiB ehk 5 242 880 baiti.
- Maksimaalne pikslite arv: 10 000 000.
- `conf` lubatud vahemik on `0.01` kuni `1.0`.

## 9. Piltide ja mudeli säilitamine

Tavalist tuvastuspilti ei säilitata. Kinnitatud treeningukandidaadi kastideta
pilt ja YOLO `.txt` salvestatakse `TRAINING_POOL_DIR` kataloogi; metadata ja
analüüsi JSON salvestatakse Oracle'isse.

Live-vaate puhtaid pilte ja viimase kaadri tuvastustulemusi hoitakse ajutiselt
API protsessi mälus. Vaatajapõhised lease'id säilitavad pausil oleva kaadri
treeningusse saatmiseni; aegunud ja viideteta kirjed koristatakse ning cache'i
mahtu piirab `LIVE_CACHE_MAX_MB`. Püsivalt salvestatakse ainult kasutaja
kinnitatud treeningukandidaat.

Mudelite kataloog ühendatakse konteinerisse kirjutuskaitstult:
`./models:/app/models:ro`. Kõik aktiivsetes kaameraprofiilides nimetatud
unikaalsed mudelid laaditakse API käivitamisel mällu üks kord.

## 10. Autentimine

UI kasutab Google'i ID-tokenit ainult sisselogimiseks. API kontrollib tokenit,
loob `USER` rolliga `APP_USERS` kirje ja kasutab edaspidi turvalist
sessiooniküpsist. `GET /api/health` jääb avalikuks.

## 11. Keskkonnamuutujad

| Muutuja | Vaikeväärtus | Tähendus |
| --- | ---: | --- |
| `MODEL_DIR` | `/app/models` | ONNX-mudelite kataloog konteineris |
| `ORT_INTRA_OP_NUM_THREADS` | `3` | ONNX Runtime'i operaatorite arvutuslõimed |
| `MODEL_CONFIDENCE_THRESHOLD` | `0.45` | Mudeli usalduslävendi vaikeväärtus |
| `MAX_UPLOAD_BYTES` | `5242880` | Pildifaili maksimaalne suurus baitides |
| `MAX_IMAGE_PIXELS` | `10000000` | Pildi maksimaalne pikslite arv |
| `LIVE_CACHE_MAX_MB` | `128` | Live-cache'i maksimaalne mälumaht megabaitides |
| `LIVE_HOT_CACHE_TTL_SECONDS` | `15` | Viimase tulemuse varu-TTL ja viideteta originaali hot-cache |
| `LIVE_PAUSE_HEARTBEAT_SECONDS` | `60` | Pausil live-vaate heartbeat'i intervall sekundites |
| `LIVE_PAUSE_LEASE_SECONDS` | `300` | Pausil kaadri lease sekundites |
| `TRAINING_POOL_DIR` | `/srv/liiklus/training_pool` | Treeningfailide kataloog |
| `TRAINING_LABEL_CONFIDENCE` | `0.25` | YOLO eelmärgenduse lävend |
| `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DSN` | puudub | Oracle'i ühendus |
| `GOOGLE_CLIENT_ID`, `SESSION_SECRET` | puudub | Google'i sisselogimine ja sessioon |

## 12. Testid

Automatiseeritud testid asuvad failis `tests/test_app.py`. Testid ei kuulu
tootmisimage'isse ega käivitu API ehitamisel või käivitamisel. Neid
käivitatakse ainult siis, kui kasutaja või väline vastuvõtukriteerium seda
sõnaselgelt nõuab. Nõutud testide käsk on:

```bash
docker compose --profile testing run --rm testing
```

## 13. Kontrollimine

Kontrollimise ajalugu ja enne järgmist testikäivitust kooskõlastatav plaan on
failis [`docs/testid.md`](docs/testid.md).
