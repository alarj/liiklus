# Tallinna liikluse tuvastuse API

## 1. Dokumendi päritolu

Dokumendi koostas OpenAI Codex 23. novembril 2026 kasutaja lähteülesande ja
tehniliste otsuste põhjal.

## 2. Sisukord

- [3. Ülevaade](#3-ülevaade)
- [4. Eeldused](#4-eeldused)
- [5. Seadistus ja käivitamine](#5-seadistus-ja-käivitamine)
- [6. API kasutamine](#6-api-kasutamine)
- [7. Sisendi piirangud](#7-sisendi-piirangud)
- [8. Piltide ja mudeli säilitamine](#8-piltide-ja-mudeli-säilitamine)
- [9. Keskkonnamuutujad](#9-keskkonnamuutujad)
- [10. Testid](#10-testid)
- [11. Praegune kontrollimise seis](#11-praegune-kontrollimise-seis)

## 3. Ülevaade

FastAPI rakendus loendab JPEG- või PNG-pildilt ONNX-mudeliga busse, autosid
ja tramme. API tagastab JSON-vastuse; visualiseeringu otspunkt lisab samasse
vastusesse Base64-kujul tuvastuskastidega JPEG-pildi.

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

Kohalik API aadress on `http://127.0.0.1:8010`. Avaliku nginxi proxy ja
SSL-sertifikaat on aktiivsed; pärast `liiklus-api` konteineri käivitamist on API
kättesaadav ka aadressil `https://liiklus.fun-o.eu/api/...`.

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

## 7. Sisendi piirangud

- Lubatud MIME-tüübid: `image/jpeg` ja `image/png`.
- Maksimaalne failisuurus: 5 MiB ehk 5 242 880 baiti.
- Maksimaalne pikslite arv: 10 000 000.
- `conf` on mudeli tuvastuse minimaalne usalduslävend. Selle lubatud vahemik
  on `0.0` kuni `1.0` ja vaikeväärtus `0.45`.

## 8. Piltide ja mudeli säilitamine

Üleslaetud pilte ei kirjutata projekti, andmebaasi ega püsivasse volume'isse.
Päringu ajal võib FastAPI kasutada operatsioonisüsteemi ajutist puhvrit, mis
suletakse päringu lõppedes. Märgendatud vastus kodeeritakse mälus.

Mudelifail ühendatakse konteinerisse kirjutuskaitstud failina:
`./models/best.onnx:/app/models/best.onnx:ro`.

## 9. Keskkonnamuutujad

| Muutuja | Vaikeväärtus | Tähendus |
| --- | ---: | --- |
| `MODEL_PATH` | `/app/models/best.onnx` | ONNX-mudeli asukoht konteineris |
| `ORT_INTRA_OP_NUM_THREADS` | `3` | ONNX Runtime'i operaatorite arvutuslõimed |
| `MODEL_CONFIDENCE_THRESHOLD` | `0.45` | Mudeli usalduslävendi vaikeväärtus |
| `MAX_UPLOAD_BYTES` | `5242880` | Pildifaili maksimaalne suurus baitides |
| `MAX_IMAGE_PIXELS` | `10000000` | Pildi maksimaalne pikslite arv |

## 10. Testid

Automatiseeritud testid asuvad failis `tests/test_app.py`. Testid ei kuulu
tootmisimage'isse ega käivitu API ehitamisel või käivitamisel. Pärast kasutaja
eraldi luba saab need käivitada käsuga:

```bash
docker compose --profile testing run --rm testing
```

## 11. Praegune kontrollimise seis

Tootmisimage on ARM64 serveris ehitatud ja `liiklus-api` konteiner töötab.
Käivituslogi kinnitab Uvicorni ja ONNX-mudeli startup'i õnnestumist.
Automatiseeritud teste ei ole veel käivitatud. Minimaalne testiplaan on failis
[`docs/testid.md`](docs/testid.md); testide käivitamine vajab kasutaja eraldi
luba.
