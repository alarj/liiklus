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
- [URL ja hilisem UI](#url-ja-hilisem-ui)
- [Tarnitavad failid](#failistruktuur-ja-tarnitavad-failid)

## Eesmärk
Luua kerge FastAPI rakendus Ubuntu ARM64 serverile, mis võtab vastu kaamerapildi ja tagastab ONNX-mudeli (`best.onnx`) põhjal tuvastatud sõidukite (auto, buss, tramm) arvud ning koordinaadid.

## Tehniline virn
- **Keel ja raamistik:** Python 3.11+, FastAPI, Uvicorn
- **Mudeli jooksutamine:** `onnxruntime` (ainult CPU, ilma PyTorchi/Ultralyticsi sõltuvusteta)
- **Pilditöötlus:** `opencv-python-headless`, `numpy`
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
- Pilte ei salvestata projekti, andmebaasi ega püsivasse Docker-volume'isse.
  FastAPI võib päringu ajal kasutada ajutist puhvrit, mis päringu lõpus
  suletakse.
- API esimeses etapis autentimist ei kasuta.

## API otspunktid
1. **`POST /api/detect`**
   - **Sisend:** `multipart/form-data` (`file`: pildifail), valikuline
     query-parameeter `conf`. See on mudeli tuvastuse minimaalne
     usalduslävend ja selle vaikeväärtus on `0.45`.
   - **Töötlus:** eeltöötlus -> ONNX inferents -> NMS (`iou=0.5`) -> koordinaatide teisendus algse pildi pikslitesse.
   - **Väljund (JSON):**
     ```json
     {
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
   - **Väljund:** JPEG-pilt (`image/jpeg`), kuhu on joonistatud tuvastatud kastid, klassinimed ja usaldusväärsus.
3. **`GET /api/health`**
   - Tagastab `{"status": "ok"}`.

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

## URL ja hilisem UI

- Kavandatav avalik API asub aadressil `https://liiklus.fun-o.eu/api/...`.
- `liiklus.fun-o.eu` DNS-kirje on olemas.
- `fun_o/nginx/default.conf` sisaldab `liiklus.fun-o.eu` `/api/` proxy
  seadistust, selle süntaks on kontrollitud ning konfiguratsioon on aktiivne.
- `fun-o.eu` Let's Encrypt sertifikaat sisaldab `liiklus.fun-o.eu` nime ja
  kehtib 21. veebruarini 2027. Renewal kasutab hosti Certboti webroot-meetodit.
- Hilisem UI töötab eraldi `liiklus-ui` konteineris ja kasutab sama API-t.
  Avalik nginx suunab `/` UI-le ja `/api/` API-le.

## Failistruktuur ja tarnitavad failid
- `app.py` – kogu rakenduse loogika
- `requirements.txt` – minimaalsed teegid
- `Dockerfile` – kerge `python:3.11-slim` ARM64 konteiner
- `docker-compose.yml` – konteineri käitus, mudeli mount ja `funo_net` võrk
- `.env.example` – käituskeskkonna seadistuse näidis
- `README.md` – käivitamise ja `curl` testimise juhend
- `docs/testid.md` – enne käivitamist ülevaadatav minimaalne testiplaan
