# Projekti vahekokkuvõte: Tallinna liikluse tuvastusmudel (`v1`)

## 1. Eesmärk ja lähtekoht

Projekti eesmärk on luua kerge, töökindel ja iseseisev masinnägemise lahendus, mis tuvastab fikseeritud liikluskaamera kaadritelt kolme tüüpi sõidukeid: **autod (`car`)**, **bussid (`bus`)** ja **trammid (`tram`)**.

Lahendus on üles ehitatud nii, et mudeli treenimine toimub pilves (GPU-kiirendusega), kuid valmis mudel on optimeeritud töötama kergel ARM64-protsessoriga serveril ilma raskete süvaõppe raamistiketa (ainult `onnxruntime`).

## 2. Andmete kogumine: kaadrite salvestamine ja lõikamine videost (PowerShell)

Treeningandmestiku loomiseks koguti kaadrid reaalsest 2K liikluskaamera videovoost kohaliku PowerShelli skripti abil:

* **Põhimõte ja intervall:** Skript loeb kaamera otsevoogu (HLS/M3U8 või RTSP) `ffmpeg` abil ja salvestab kaadri **iga 5 sekundi järel**.

* **Automaatne väljalõige (*crop* `1150 × 550`):** Kuna kaamera füüsilist asukohta ei saanud muuta, aga algne 2K kaader oli piisavalt suure resolutsiooniga, lõikas `ffmpeg` juba salvestamise hetkel kaadri keskelt automaatselt välja enam-vähem takistustevaba `1150 × 550` piksli suuruse huviala.

* **Andmete valik:** Kogutud piltide hulgast eemaldati tühjad ja korduvad kaadrid, mille tulemusel jäi alles **441** sisukat "päris" kaadrit.

### Kasutatud PowerShelli skript kaadrite kogumiseks ja lõikamiseks

```powershell
# Kaadrite salvestamine ja 1150x550 huviala väljalõige 2K voost iga 5 sekundi järel
$StreamUrl = "https://kaamera-voog.example.ee/stream.m3u8"
$OutputDir = "C:\tallinn_liiklus\raw_frames"
$IntervalSec = 5

# 2K kaadri keskelt 1150x550 ala väljalõige (laius:kõrgus:x_nihe:y_nihe)
$CropFilter = "crop=1150:550:(in_w-1150)/2:(in_h-550)/2"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

while ($true) {
    $Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutFile = Join-Path $OutputDir "frame_$Timestamp.jpg"

    ffmpeg -y -loglevel error -i $StreamUrl -vf $CropFilter -frames:v 1 -q:v 2 $OutFile

    if (Test-Path $OutFile) {
        Write-Host "Salvestatud: $OutFile"
    }

    Start-Sleep -Seconds $IntervalSec
}
```

## 3. Mudeli valik ja selle iseloom

Tuvastusmudeliks valiti **YOLOv8s** (*You Only Look Once*, versioon 8, suurus *small*):

* **Miks YOLOv8s?** Võrreldes kõige pisema (`nano`) versiooniga suudab `small` paremini eristada kaugemal asuvaid ja osaliselt varjatud objekte (nt puuokste taga olevad trammid ja bussid), jäädes samas piisavalt kompaktseks (~11,1 miljonit parameetrit, `42,8 MB` ONNX-formaadis), et joosta kiiresti ka tavalisel ARM64 CPU-l (~0,5 sekundit kaadri kohta).

* **Sisendmõõdu eripära:** Kaamera lõigatud resolutsioon (`1150 × 550`) ümardati 32-ga jaguvaks standardmõõduks **`1152 × 576`**. Piltidele lisatakse paremale ja alla vaid minimaalne 2–26 piksline neutraalne hall ääris (*padding*), mis välistab pildi moonutamise ja skaleerimisest tingitud detailikao.

* **Klasside järjestus:** Mudelisse on fikseeritud tähestikuline klassijärjekord: `0: bus`, `1: car`, `2: tram`.

## 4. Andmete eeltöötlus ja märgendamine (Google Colab & Roboflow)

Käsitsi sadade piltide märgendamise kiirendamiseks kasutati kaheastmelist töövoogu:

1. **Eelmärgendamine Google Colabis:** Kasutati eeltreenitud baasmudelit (`yolov8x.pt`), mis leidis 441 valitud kaadrilt esialgsed sõidukikastid (COCO klassid: `car`, `bus`, `train`) ja salvestas need YOLO `.txt` annotatsioonidena, mida saab otse koos piltidega Roboflow'sse üles laadida.

2. **Korrastamine, augmentatsioon ja ekspordi seadistamine Roboflow keskkonnas:**

   * Kõik automaatselt leitud kastid vaadati visuaalselt üle, parandati piirjooned ning märgendati käsitsi puuduvad sõidukid — eriti **trammid**, mida üldotstarbelised baasmudelid kipuvad sageli bussideks või rongideks liigitama.

   * **Andmestiku jaotus ja maht:** 441 algset kaadrit jagati ~80% treeningkomplektiks (`train`) ja ~20% valideerimiskomplektiks (`valid` — **88 pilti**, milles on kokku **180 märgendatud objekti**: 11 bussi, 162 autot ja 7 trammi).

   * **Augmentatsioon (*Horizontal Flip*):** Pärast käsitsi ülevaatamist lisati treeningkomplektile horisontaalse peegelduse (*Horizontal Flip*) abil juurde teine peaaegu sama suur kogus peegeldatud treeningpilte (~800 pilti kokku).

### Kasutatud Google Colabi eelmärgendamise skript

```python
!pip install -q ultralytics

import shutil
from pathlib import Path
from ultralytics import YOLO

# 1. Laadi suure täpsusega eeltreenitud baasmudel eelmärgendamiseks
model = YOLO("yolov8x.pt")

input_dir = Path("/content/raw_frames")
export_dir = Path("/content/prelabeled_dataset")
(export_dir / "images").mkdir(parents=True, exist_ok=True)
(export_dir / "labels").mkdir(parents=True, exist_ok=True)

# COCO klasside vastavus meie projektile:
# COCO: 2 = car, 5 = bus, 6 = train (trammide toorikuks)
# Meie märgendus: 0 = bus, 1 = car, 2 = tram
coco_to_custom = {
    5: 0,  # bus -> 0
    2: 1,  # car -> 1
    6: 2,  # train -> 2 (tram)
}

for img_path in sorted(input_dir.glob("*.jpg")):
    results = model.predict(source=str(img_path), conf=0.30, verbose=False)[0]
    lines = []

    for box in results.boxes:
        coco_cls = int(box.cls[0])
        if coco_cls in coco_to_custom:
            custom_cls = coco_to_custom[coco_cls]
            x_c, y_c, w, h = box.xywhn[0].tolist()
            lines.append(f"{custom_cls} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}")

    # Kopeeri pilt ja kirjuta YOLO annotatsioonifail
    shutil.copy(img_path, export_dir / "images" / img_path.name)
    label_path = export_dir / "labels" / f"{img_path.stem}.txt"
    label_path.write_text("\n".join(lines), encoding="utf-8")

# Pakime kokku Roboflow'sse üleslaadimiseks
shutil.make_archive("/content/prelabeled_for_roboflow", "zip", export_dir)
print("Valmis: /content/prelabeled_for_roboflow.zip")
```

### Roboflow andmestiku ja ekspordi seadistus (`v1`)

* **Klasside kaardistus (*Classes*):** `bus`, `car`, `tram` (tähestikulises järjekorras `0, 1, 2`).

* **Andmestiku jaotus (*Train / Valid Split*):** ~80% `train` / ~20% `valid` (88 puutumatut valideerimispilti, 180 objekti).

* **Eeltöötlus (*Preprocessing*):**

  * *Auto-Orient:* **väljas** (fikseeritud kaamera pildid olid juba õigetpidi).

  * *Resize:* **väljas** (säilitati täisformaat `1150 × 550`, et vältida detailikadu).

* **Augmentatsioonid (*Augmentations*):** *Horizontal Flip* (kahekordistas sisuliselt treeningkomplekti mahu); vertikaalne peegeldus ja pööramine välja lülitatud.

* **Ekspordi formaat (*Export Format*):** **`YOLOv8`** (laaditav alla ZIP-arhiivina või API võtmega otse Kaggle'i märkmikusse).

## 5. Mudeli treenimine (Kaggle)

Mudeli treenimine viidi läbi Kaggle'i pilvekeskkonnas **NVIDIA Tesla T4** graafikakaardil:

* **Treeningu maht ja formaat:** 60 epohhi (`yolov8s.pt` baasil) **täisformaadis piltidel** (`1152 × 576` / originaalmõõt ilma vähendamiseta), kogu treeningprotsess kestis vaid ~13,5 minutit (`0.225` tundi).

* **Eksport tootmisformaati:** Treeningu tulemusena saadud PyTorch-mudel (`best.pt`) eksporditi fikseeritud sisendkujuga `(1, 3, 576, 1152)` optimeeritud **ONNX-failiks** (`best.onnx`), mida saab käivitada otse `onnxruntime` teegiga.

### Kasutatud Kaggle'i treeningu- ja ekspordiskript

```python
# 1. Vajalike teekide paigaldamine
!pip install -q ultralytics roboflow onnx onnxslim onnxruntime

from roboflow import Roboflow
from ultralytics import YOLO

# 2. Andmestiku allalaadimine Roboflow'st
rf = Roboflow(api_key="SINU_ROBOFLOW_API_VOTI")
project = rf.workspace("sinu-workspace").project("tallinna-liiklus")
dataset = project.version(1).download("yolov8")

# 3. Mudeli treenimine täisformaadis piltidel (60 epohhi, YOLOv8s)
model = YOLO("yolov8s.pt")
model.train(
    data=f"{dataset.location}/data.yaml",
    epochs=60,
    imgsz=1152,
    rect=True,
    batch=16,
    name="tallinn_liiklus_v1",
    patience=20
)

# 4. Parima mudeli eksport fikseeritud kaamera sisendmõõdule (kõrgus=576, laius=1152)
best_model = YOLO("runs/detect/tallinn_liiklus_v1/weights/best.pt")
best_model.export(format="onnx", imgsz=(576, 1152))
```

## 6. Esimese versiooni (`v1`) tulemused ja tähelepanekud

Valideerimisandmestikul (88 pilti, 180 objekti) saavutas esimene versioon väga tugeva üldtulemuse (**`mAP50 = 92,1%`**, täpsus `93,9%`, tabavus `87,9%`):

* **Autod (`car`):** `mAP50 = 94,3%` — väga kindel tuvastus nii päeval kui ka hämaras (`confidence` tüüpiliselt `0.85–0.95`).

* **Bussid (`bus`):** `mAP50 = 90,5%` — hea eristusvõime, segiajamist autode ega trammidega ei esinenud.

* **Trammid (`tram`):** `mAP50 = 91,6%` ja 100% täpsus valideerimiskomplektis.

### Praktiline testimine päris kaamerapiltidega:

* **Päevavalguses ja selge nähtavusega:** Mudel tuvastab kõik sõidukiklassid täpselt ja kõrge enesekindlusega (vaikimisi lävega `conf = 0.45`).

* **Laternavalguses ja takistustega:** Õhtupimeduses kollase tänavavalguse käes ning raagus puuokste taga langeb trammi tuvastuse enesekindlus märgatavalt (nt väärtuseni `0.27`). Mudel tunneb trammi küll õiges kohas ära, kuid vaikimisi `0.45` läve juures jäetakse see vastusest välja.

## 7. Järgmised sammud ja mudeli edasiarendus (`v2`)

### Lühiajalised sammud (olemasoleva mudeli baasil)

1. **Klassipõhised usaldusläved:** Rakendada tuvastusteenuses erinevad läved vastavalt sõiduki tüübile (nt `car: 0.45`, `bus: 0.40`, `tram: 0.25`), et püüda kinni ka hämaras ja okste taga liikuvad trammid ilma autode hulka valepositiivseid tekitamata.

2. **Pidev andmekogumine (aktiivõpe):** Seadistada kaameravoog salvestama automaatselt need kaadrid, kus mõne sõiduki skoor jääb vahemikku `0.20 – 0.50` või kus esineb kahtlasi tuvastusi.

### Mudeli edasi treenimine (`v2`) ja "unustamise" vältimine (*Catastrophic Forgetting*)

* **Kumulatiivne andmestik:** Uusi öiseid ja keerulisi kaadreid (50–150 pilti: laternavalgus, märja asfaldi peegeldused, puuokste taga varjatud trammid/bussid ning tühjad taustapildid) **ei treenita eraldi**, vaid need lisatakse Roboflow olemasolevasse projekti **senise 441 pildi juurde**.

* **Treeningu strateegia:** `v2` treenitakse kas `yolov8s.pt` baasmudelist nullist uuesti (nüüd juba ~550–600 algpildiga + *Horizontal Flip*) või peenhäälestatakse `v1` mudelit kogu kombineeritud andmestiku peal madalama õppimiskiirusega (`lr0=0.001`). Nii näeb mudel igas epohhis nii päeva- kui ka ööpilte ning päevane täpsus säilib.

### Mitme mudeli tugi API-s ja automaatne A/B-võrdlusskript

1. **Mudeliversiooni valik API-s:**
   * Serverisse paigutatakse kõrvuti `models/v1.onnx` ja `models/v2.onnx` (mõlemad hoitakse mälus, kogumaht ~86 MB).
   * Päringutele lisatakse valikuline parameeter `model` (nt `POST /api/detect?model=v1` või `model=v2`, vaikimisi uusim) ning vastuse JSON-isse lisatakse kasutatava mudeli versioon (`"model": "v2"`).

2. **Automaatne regressiooni- ja võrdlusskript:**
   * Skript söödab läbi mõlema mudeliversiooni (`v1` ja `v2`) paarsada mitmekesist testpilti (päev, hämarus, vihm, tühi tänav).
   * Tulemustest sõelutakse automaatselt välja ainult need kaadrid, kus kahe mudeli vahel esineb erinevus:
     * **objektide arvus** (nt `v2` leidis hämaras trammi, mida `v1` ei näinud);
     * **tuvastatud klassides** (nt `car` vs `bus`);
     * **objektide asukohas** (piirdekastide kattuvus `IoU < 0.7`).
   * Väljasõelutud erisustega pildid salvestatakse kõrvuti joonistatuna (`v1` vs `v2`) eraldi kausta, mis võimaldab uue mudeli kvaliteeti ja võimalikke tagasilööke kiiresti visuaalselt hinnata enne selle vaikimisi kasutuselevõttu.