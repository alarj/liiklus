# Projekt: Tallinna liikluse tuvastuse API

## Eesmärk
Luua kerge FastAPI rakendus Ubuntu ARM64 serverile, mis võtab vastu kaamerapildi ja tagastab ONNX-mudeli (`best.onnx`) põhjal tuvastatud sõidukite (auto, buss, tramm) arvud ning koordinaadid.

## Tehniline virn
- **Keel ja raamistik:** Python 3.11+, FastAPI, Uvicorn
- **Mudeli jooksutamine:** `onnxruntime` (ainult CPU, ilma PyTorchi/Ultralyticsi sõltuvusteta)
- **Pilditöötlus:** `opencv-python-headless`, `numpy`
- **Mudeli fail:** `models/best.onnx`
- **Klassid (järjekorras):** `0: car`, `1: bus`, `2: tram`

## Sisendpildi eeltöötlus (kriitiline nõue)
- Mudeli sisendmõõt on fikseeritud: **`1152 × 576`** (laius × kõrgus).
- **Ei tohi skaleerida** pilte, mis mahuvad `1152 × 576` sisse (nt `1150 × 550`).
- Väiksemad pildid paigutatakse ülemisse vasakusse nurka `(0, 0)` ja täidetakse paremalt ning alt halli taustaga (`RGB 114, 114, 114`) kuni mõõduni `1152 × 576`.
- Ainult juhul, kui sisendpilt on suurem kui `1152 × 576`, skaleeritakse see kuvasuhet hoides alla ja täidetakse ülejäänud servad halliga.

## API otspunktid
1. **`POST /detect`**
   - **Sisend:** `multipart/form-data` (`file`: pildifail), valikuline query-parameeter `conf` (vaikimisi `0.45`).
   - **Töötlus:** eeltöötlus -> ONNX inferents -> NMS (`iou=0.5`) -> koordinaatide teisendus algse pildi pikslitesse.
   - **Väljund (JSON):**
     ```json
     {
       "image_size": {"width": 1150, "height": 550},
       "counts": {"car": 0, "bus": 0, "tram": 0},
       "total": 0,
       "detections": [
         {"class": "tram", "confidence": 0.91, "bbox_xyxy": [412, 310, 895, 425]}
       ]
     }
     ```
2. **`POST /detect/image`**
   - **Sisend:** sama mis `/detect`.
   - **Väljund:** JPEG-pilt (`image/jpeg`), kuhu on joonistatud tuvastatud kastid, klassinimed ja usaldusväärsus.
3. **`GET /health`**
   - Tagastab `{"status": "ok"}`.

## Swagger api kasutamiseks
- paigalda kohe ka swagger api kasutamiseks

## URL
- paigaldame rakenduse aadressile liiklus.fun-o.eu/api/... 
- DNS seadistus ei ole selle projekti osa
- fun-o.eu nginx tuleb seadistada eraldi (tuleb eraldi luba küsida)
- olemasolev fun-o.eu ssl sert tuleb uuendada ja lisada sinna uus alamdomeen liiklus. Küsi luba, ilma otsese korralduse ja loata ei tohi teha.

## Failistruktuur ja tarnitavad failid
- `app.py` – kogu rakenduse loogika
- `requirements.txt` – minimaalsed teegid
- `Dockerfile` – kerge `python:3.11-slim` ARM64 konteiner
- `README.md` – käivitamise ja `curl` testimise juhend