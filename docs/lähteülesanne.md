# Projekt: Tallinna liikluse tuvastuse API

## Dokumendi päritolu

Dokumendi koostas algselt inimene. OpenAI Codex täiendas dokumenti 23. novembril
2026 kasutajaga kokku lepitud tehniliste otsuste põhjal.

## Sisukord

- [Eesmärk](#eesmärk)
- [Tehniline virn](#tehniline-virn)
- [Sisendpildi eeltöötlus](#sisendpildi-eeltöötlus-kriitiline-nõue)
- [Sisendi piirangud ja säilitamine](#sisendi-piirangud-ja-säilitamine)
- [API otspunktid](#api-otspunktid)
- [Docker-konteiner](#docker-konteiner)
- [Swagger](#swagger-api-kasutamiseks)
- [UI](#ui)
- [Autentimine](#autentimine)
- [Tarnitavad failid](#failistruktuur-ja-tarnitavad-failid)

## Eesmärk
Luua kerge FastAPI rakendus Ubuntu ARM64 serverile, mis võtab vastu kaamerapildi ja tagastab ONNX-mudeli (`best.onnx`) põhjal tuvastatud sõidukite (auto, buss, tramm) arvud ning koordinaadid.

## Tehniline virn
- **Keel ja raamistik:** Python 3.11+, FastAPI, Uvicorn
- **Mudeli jooksutamine:** `onnxruntime` (ainult CPU, ilma PyTorchi/Ultralyticsi sõltuvusteta)
- **Pilditöötlus:** `opencv-python-headless`, `numpy`
- **UI:** staatiline HTML, eraldi CSS ja vanilla JavaScript eraldi nginx-konteineris
- **Mudeli fail:** `models/best.onnx`
- **Klassid:** loetakse käivitamisel ONNX-metaandmetest; praeguse mudeli
  järjestus on `0: bus`, `1: car`, `2: tram`.

## Sisendpildi eeltöötlus (kriitiline nõue)
- Mudeli sisendmõõt on fikseeritud: **`1152 × 576`** (laius × kõrgus).
- **Ei tohi skaleerida** pilte, mis mahuvad `1152 × 576` sisse (nt `1150 × 550`).
- Väiksemad pildid paigutatakse ülemisse vasakusse nurka `(0, 0)` ja täidetakse paremalt ning alt halli taustaga (`RGB 114, 114, 114`) kuni mõõduni `1152 × 576`.
- Ainult juhul, kui sisendpilt on suurem kui `1152 × 576`, skaleeritakse see kuvasuhet hoides alla ja täidetakse ülejäänud servad halliga.

## Sisendi piirangud ja säilitamine

- Lubatud vormingud on JPEG (`image/jpeg`) ja PNG (`image/png`).
- Pildifaili maksimaalne suurus on 5 MiB ehk 5 242 880 baiti.
- Pildi laius korrutatud kõrgusega võib olla kuni 10 000 000 pikslit.
- Mõõt kontrollitakse kodeeritud pildi päisest enne OpenCV-ga dekodeerimist.
- Tavaline tuvastuspäring pilti ei säilita. Kasutaja kinnitatud
  treeningukandidaat salvestatakse `TRAINING_POOL_DIR` kataloogi; Oracle'is
  hoitakse metaandmed ja analüüsi JSON.
- Treeningukandidaadi kustutamisel eemaldatakse pilt ja YOLO märgend kettalt,
  kuid Oracle'i kirje suletakse soft delete'iga.

## API otspunktid
1. **`POST /api/detect`**
   - **Sisend:** `multipart/form-data` (`file`: pildifail), valikuline
     query-parameeter `conf`. See on mudeli tuvastuse minimaalne
     usalduslävend ja selle vaikeväärtus on `0.45`.
   - **Töötlus:** eeltöötlus -> ONNX inferents -> NMS (`iou=0.5`) -> koordinaatide teisendus algse pildi pikslitesse.
   - **Väljund (JSON):**
     ```json
     {
       "request_received_at": "2026-11-23T19:42:07.123Z",
       "processing_duration_ms": 612.4,
       "filename": "kaamera.jpg",
       "conf": 0.45,
       "image_size": {"width": 1150, "height": 550},
       "counts": {"bus": 0, "car": 0, "tram": 0},
       "total": 0,
       "detections": [
         {"class": "tram", "confidence": 0.91, "bbox_xyxy": [412, 310, 895, 425]}
       ]
     }
     ```
2. **`POST /api/detect/image`**
   - **Sisend:** sama mis `/api/detect`.
   - **Väljund:** sama JSON mis `/api/detect`, millele lisandub
     `annotated_image`. Selle `media_type` on `image/jpeg` ja `base64` sisaldab
     tuvastuskastide, klassinimede ja usaldusväärtustega JPEG-pilti.
   - Sisendpilt saadetakse tavalise `multipart/form-data` failina. Mudel
     käivitatakse ühe päringu jooksul ainult üks kord.
   - Mõlema tuvastusotspunkti `request_received_at` on UTC-s ISO 8601
     ajatempel, `processing_duration_ms` on valideerimise, eeltöötluse,
     inferentsi ja järeltöötluse kestus millisekundites ning `filename` on
     kliendi saadetud failinime basename või selle puudumisel `null`. Väli
     `conf` näitab päringus tegelikult kasutatud usalduslävendit, sealhulgas
     `.env` vaikeväärtust, kui query-parameeter puudub.
3. **`GET /api/health`**
   - Tagastab `{"status": "ok"}`.
4. **Treeningupildi otspunktid**
   - `/api/training-pool` haldab kandidaate ja nende algpilte.
   - `/api/training-packages` haldab pakke, piltide seoseid ja ZIP-eksporti.
   - Täpne andmemudel on failis [`../db/erd.md`](../db/erd.md).

## Docker-konteiner

- Rakendus töötab teenuses ja konteineris `liiklus-api`.
- Uvicorn kasutab ühte worker'it.
- ONNX Runtime kasutab `.env` väärtuse `ORT_INTRA_OP_NUM_THREADS=3` järgi
  kolme operaatorite arvutuslõime. Eraldi Docker CPU-piirangut ei rakendata.
- Mudeli usalduslävendi vaikeväärtus tuleb `.env` muutujast
  `MODEL_CONFIDENCE_THRESHOLD=0.45`; päringu `conf` võib selle üle kirjutada.
- Mudelifail ühendatakse konteinerisse read-only mount'ina.
- Kohalik ligipääs on `http://127.0.0.1:8010`.
- Konteiner ühendatakse olemasolevasse välisesse `funo_net` võrku.

## Swagger api kasutamiseks

- Swagger UI asub `/api/docs` ja OpenAPI skeem `/api/openapi.json`.

## UI

- Kavandatav avalik API asub aadressil `https://liiklus.fun-o.eu/api/...`.
- `liiklus.fun-o.eu` DNS-kirje on olemas.
- `fun_o/nginx/default.conf` sisaldab `liiklus.fun-o.eu` `/api/` proxy
  seadistust, selle süntaks on kontrollitud ning konfiguratsioon on aktiivne.
- `fun-o.eu` Let's Encrypt sertifikaat sisaldab `liiklus.fun-o.eu` nime ja
  kehtib 21. veebruarini 2027. Renewal kasutab hosti Certboti webroot-meetodit.
- UI töötab eraldi `liiklus-ui` nginx-konteineris; UI-d ei ühendata API
  rakenduse ega API Docker image'iga.
- Avalik nginx suunab `/` UI-le ja `/api/` API-le.
- UI võtab vastu ühe JPEG- või PNG-pildi korraga ja saadab selle otspunktile
  `POST /api/detect/image`. Brauser ei korda tuvastus-, loendus-, pilditöötlus-
  ega sisendi piirangute äriloogikat.
- UI kuvab API tagastatud märgendatud pildi, loendused, metaandmed ja
  tuvastused. API JSON-vastust saab vaadata eraldi modalis; kuvamiseks loodud
  koopiast eemaldatakse lennult `annotated_image.base64`, sest pilt kuvatakse
  eraldi tavavaates. Modali ikoonnupust saab sama JSON-i ilma Base64-väljata
  `.json` failina alla laadida.
- UI CSS asub eraldi failis ja kasutab TTÜ-loengu projekti olemasolevat
  kujunduskeelt. Kasutajaliidese tekstid tulevad eestikeelsest tõlkefailist.
- UI kuvab tuvastuslävendi seletuses API vaikeväärtuse. Väärtus antakse UI
  konteinerile Compose'i kaudu samast `MODEL_CONFIDENCE_THRESHOLD`
  keskkonnamuutujast ega ole brauseri äriloogikas eraldi määratud.
- Kolme taseme režiimis teeb UI kolm `/api/detect/image` päringut lävenditega
  `default`, `max(0.01, default - 0.20)` ja
  `max(0.01, default - 0.40)` ning kuvab kolm tulemust kõrvuti.
- UI võimaldab märkida pildi treeningukandidaadiks ning koostada kandidaatidest
  enne esimest allalaadimist muudetavaid treeningpakke.

## Autentimine

- UI kasutab Google'i autentimist ja serveripoolset sessiooniküpsist.
- Esmakordsel sisselogimisel luuakse `APP_USERS` kirje rolliga `USER`;
  praeguses etapis roll tegevusi ei piira.
- `GET /api/health` ning autentimise alustamise otspunktid on avalikud, muud
  API otspunktid nõuavad sessiooni.
- Välise API Basic- või Bearer-autentimine lisatakse hiljem.

## Failistruktuur ja tarnitavad failid
- `app.py` – API ja tuvastusloogika
- `database.py` – Oracle'i andmekiht
- `db/schema/001_core_schema.sql` – käivitatav skeemi loomise skript
- `db/erd.md` – andmemudel
- `requirements.txt` – minimaalsed teegid
- `Dockerfile` – kerge `python:3.11-slim` ARM64 konteiner
- `ui/` – eraldi staatiline UI, CSS, tõlked ja nginx-konteiner
- `docker-compose.yml` – API ja UI konteinerite käitus, mudeli mount ja `funo_net` võrk
- `.env.example` – käituskeskkonna seadistuse näidis
- `README.md` – käivitamise ja `curl` testimise juhend
- `docs/testid.md` – enne käivitamist ülevaadatav minimaalne testiplaan
