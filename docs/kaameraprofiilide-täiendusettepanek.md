# Kaameraprofiilide ja ROI-maskimise täiendusettepanek

## 1. Dokumendi päritolu

Dokumendi koostas OpenAI Codex 27. novembril 2026 kasutaja kirjeldatud
Tallinna liikluskaamerate toe, teise agendi koostatud `cam217` maskimise
lähteülesande, projekti olemasoleva koodi ja dokumentatsiooni ning kasutajaga
peetud täpsustava arutelu põhjal. Dokument on teostusettepanek; selle
koostamisel ei muudetud rakenduse koodi, andmebaasi ega käituskeskkonda.

## 2. Sisukord

- [3. Eesmärk ja ulatus](#3-eesmärk-ja-ulatus)
- [4. Olemasoleva lahenduse lähtekoht](#4-olemasoleva-lahenduse-lähtekoht)
- [5. Kaameraprofiili andmemudel](#5-kaameraprofiili-andmemudel)
- [6. Esialgsed profiilid](#6-esialgsed-profiilid)
- [7. Profiilide ja mudelite laadimine](#7-profiilide-ja-mudelite-laadimine)
- [8. Mudeli sisendi ja klasside valideerimine](#8-mudeli-sisendi-ja-klasside-valideerimine)
- [9. ROI-mask ja pildi eeltöötlus](#9-roi-mask-ja-pildi-eeltöötlus)
- [10. API leping](#10-api-leping)
- [11. Analüüsi kasutajaliides](#11-analüüsi-kasutajaliides)
- [12. Treeningpildid](#12-treeningpildid)
- [13. Treeningpakid ja maskitud ZIP](#13-treeningpakid-ja-maskitud-zip)
- [14. Olemasolevate andmete migratsioon](#14-olemasolevate-andmete-migratsioon)
- [15. Tagasiühilduvus](#15-tagasiühilduvus)
- [16. Veakäsitlus ja valideerimine](#16-veakäsitlus-ja-valideerimine)
- [17. Testimisettepanek](#17-testimisettepanek)
- [18. Dokumentatsiooni mõju](#18-dokumentatsiooni-mõju)
- [19. Soovitatav teostamise järjekord](#19-soovitatav-teostamise-järjekord)
- [20. Kinnitatud teostusotsused](#20-kinnitatud-teostusotsused)

## 3. Eesmärk ja ulatus

Täienduse eesmärk on võtta kasutusele kaameraprofiil, mis seob ühe kaamera või
kaameratüübi jaoks vajalikud omadused:

- lubatud ONNX-mudelid ja nende järjestuse;
- profiili vaikemudeli;
- mudeli sõidukiklasside koodid ja kuvatavad nimetused;
- profiili vaikimisi tuvastuslävendi;
- valikulise ROI-polügoonmaski;
- kaamera originaalpildi URL-i tulevase automaatse pildihõive jaoks;
- profiili kuvamisjärjestuse;
- vaikeprofiili tunnuse.

Esimeses etapis valib kasutaja profiili koos pildi sisestamisega. Kaamera
originaalpildi URL on ainult metadata: rakendus ei laadi sellelt ise pilte.
Hiljem saab sama andmemudelit kasutada automaatse pildihõive lisamiseks.

Olemasolev Pärnu mnt - Karja lahendus peab jääma senisel kujul tööle ja sellest
saab andmebaasi vaikeprofiil. Tallinna Liikuvusameti `cam217` profiil kasutab
eraldi mudelit ja ROI-maski.

## 4. Olemasoleva lahenduse lähtekoht

Praeguses lahenduses:

- mudelite järjestatud loend tuleb keskkonnamuutujast `MODEL_FILES_JSON`;
- loendi esimene mudel on vaikemudel;
- API ja UI lubavad valida mudelifaili otse;
- kõik mudelid laaditakse teenuse käivitamisel mällu;
- mudeli sisendmõõt on globaalselt `1152 × 576`;
- lubatud klassid on globaalselt `bus`, `car` ja `tram`;
- annotatsioon, YOLO märgendid, treeningpaki `classes.txt` ja UI võrdlusvaade
  eeldavad samu kolme klassi;
- treeningpildil ega treeningpakil ei ole kaameraprofiili seost.

`cam217` mudeli sisend on `1280 × 736` ja klassid on `bus`, `car` ning
`van-truck`. Seetõttu ei saa uut mudelit lisada ainult
`MODEL_FILES_JSON` loendisse. Mudeli mõõt, klassikaart ja eeltöötlus peavad
muutuma profiili- ja mudeliteadlikuks.

## 5. Kaameraprofiili andmemudel

Oracle'isse lisatakse tabel `camera_profiles` ja selle numbrilise primaarvõtme
sequence. Tabel järgib projekti soft delete'i ja ajatemplite reegleid.

Kavandatavad väljad:

| Väli | Tüüp põhimõtteliselt | Tähendus |
| --- | --- | --- |
| `camera_profile_id` | `NUMBER(19)` | Sisemine primaarvõti ja välisvõtmete siht |
| `profile_code` | `VARCHAR2` | Stabiilne avalik API-kood, näiteks `cam217` |
| `profile_version` | `NUMBER` | Inferentsikonfiguratsiooni versioon |
| `profile_name` | `VARCHAR2` | Kasutajale kuvatav nimi |
| `sort_order` | `NUMBER` | Profiilide kuvamisjärjestus |
| `is_default` | `NUMBER(1)` | Aktiivse vaikeprofiili tunnus `0` või `1` |
| `source_image_url` | `VARCHAR2`, nullable | Tulevase automaatse pildihõive allikas |
| `model_files_json` | `JSON` | Järjestatud ONNX-failinimede massiiv |
| `vehicle_classes_json` | `JSON` | Mudeli klassiindeksite, koodide ja nimetuste seos |
| `roi_mask_json` | `JSON`, nullable | ROI-mask ja täitevärv |
| `default_confidence` | `NUMBER` | Profiili vaikimisi tuvastuslävend |
| `start_date` | `DATE` | Kehtivuse algus |
| `end_date` | `DATE`, nullable | Soft delete või versiooni kehtivuse lõpp |
| `created` | `TIMESTAMP` | Loomise aeg |
| `last_updated` | `TIMESTAMP`, nullable | Viimase muudatuse aeg |

`public_id` veergu profiilitabelisse ei lisata. Teistes projekti tabelites
kasutatakse UUID-kujul `public_id` väärtust selleks, et API ei avaldaks
järjestikulist andmebaasi primaarvõtit. Kaameraprofiili puhul täidab avaliku
identifikaatori rolli juba inimesele arusaadav ja stabiilne `profile_code`.

Andmemudeli reeglid:

- aktiivsete profiilide hulgas on ühe `profile_code` kohta üks versioon;
- `profile_code` ja `profile_version` paar on unikaalne;
- aktiivseid vaikeprofiile saab olla maksimaalselt üks;
- rakendus kontrollib käivitamisel, et aktiivne vaikeprofiil on olemas;
- `model_files_json` peab olema mittetühi järjestatud stringimassiiv;
- loendi esimene element on profiili vaikemudel;
- mudelifaili nimi ei tohi sisaldada kataloogiteed;
- `default_confidence` peab olema vahemikus `0.01` kuni `1.0`;
- `source_image_url` ja `roi_mask_json` võivad olla `NULL`;
- inferentsi mõjutava seadistuse muutmisel luuakse uus profiiliversioon ja
  vana versioon suletakse `end_date` abil.

Andmebaasi indeks tagab, et aktiivseid vaikeprofiile ei saa olla üle ühe.
Täpselt ühe vaikeprofiili olemasolu kontrollib rakendus, sest indeks ei saa
nõuda vähemalt ühe vastava rea olemasolu.

## 6. Esialgsed profiilid

### 6.1. Pärnu mnt - Karja

```json
{
  "profile_code": "parnu-mnt-karja",
  "profile_version": 1,
  "profile_name": "Pärnu mnt - Karja",
  "sort_order": 10,
  "is_default": 1,
  "source_image_url": null,
  "model_files_json": [
    "best v3.onnx",
    "best v2.onnx",
    "best.onnx"
  ],
  "vehicle_classes_json": [
    {"model_index": 0, "code": "bus", "name": "Buss"},
    {"model_index": 1, "code": "car", "name": "Auto"},
    {"model_index": 2, "code": "tram", "name": "Tramm"}
  ],
  "roi_mask_json": null,
  "default_confidence": 0.45
}
```

Migratsiooni koostamisel tuleb `model_files_json` täita tegeliku kasutusel
oleva `MODEL_FILES_JSON` väärtusega. Ülal olev loend kirjeldab projekti
näidiskonfiguratsiooni ega asenda käituskeskkonna kontrollimist.

### 6.2. `cam217` – Laagna tee / Mustakivi

```json
{
  "profile_code": "cam217",
  "profile_version": 1,
  "profile_name": "Laagna tee / Mustakivi",
  "sort_order": 20,
  "is_default": 0,
  "source_image_url": null,
  "model_files_json": [
    "cam217 v2.onnx"
  ],
  "vehicle_classes_json": [
    {"model_index": 0, "code": "bus", "name": "Buss"},
    {"model_index": 1, "code": "car", "name": "Auto"},
    {"model_index": 2, "code": "van-truck", "name": "Kaubik/veok"}
  ],
  "roi_mask_json": {
    "type": "polygon",
    "fill_rgb": [114, 114, 114],
    "normalized_points": [
      [0.032, 0.105],
      [0.098, 0.068],
      [0.558, 0.258],
      [0.922, 0.562],
      [0.875, 0.992],
      [0.232, 0.985]
    ]
  },
  "default_confidence": 0.45
}
```

`cam217` mudelifail on `cam217 v2.onnx`.

## 7. Profiilide ja mudelite laadimine

`MODEL_DIR` jääb keskkonnamuutujaks ja mudelifailid jäävad serveri samasse
read-only kataloogi sõltumata profiilist. `MODEL_FILES_JSON` eemaldatakse
keskkonnakonfiguratsioonist pärast profiilide migratsiooni.

Teenuse käivitamisel:

1. luuakse Oracle'i ühendus;
2. laaditakse aktiivsed profiilid `sort_order` järgi;
3. valideeritakse vaikeprofiil ja profiilide konfiguratsioon;
4. kogutakse kõigi profiilide unikaalsed mudelifailinimed;
5. kontrollitakse mudelifailide olemasolu `MODEL_DIR` kataloogis;
6. iga unikaalne ONNX-mudel laaditakse mällu üks kord;
7. profiilid seotakse laaditud mudelisessioonidega.

Kui sama ONNX-faili kasutab mitu profiili, jagavad need ühte mudelisessiooni ja
sama mudeli inferentsilukku. Profiili eeltöötlus ja klassikaart ei pea selleks
olema mudelisessiooni globaalsed omadused.

## 8. Mudeli sisendi ja klasside valideerimine

Mudeli sisendtensori mõõt loetakse ONNX-mudelist. Rakendus toetab ühte pilti
ja kolme värvikanalit:

```text
1 × 3 × kõrgus × laius
```

Näited:

- olemasolev mudel: `1 × 3 × 576 × 1152`;
- `cam217`: `1 × 3 × 736 × 1280`.

Täpne valideerimisreegel:

- kanalite arv peab olema fikseeritud `3`;
- kõrgus ja laius peavad ONNX-mudelis olema positiivsete arvudena määratud;
- batch võib olla fikseeritud `1` või dünaamiline;
- rakendus saadab alati batch'i suurusega `1`;
- dünaamilise kõrguse või laiusega mudelit ei toetata, sest rakendus ei saa
  ainult mudelist tuletada nõutavat lõuendi suurust.

OpenCV dekodeerib pildi BGR-kanalijärjekorras. Enne inferentsi teisendatakse
mudeli lõuend RGB-kanalijärjekorda, nagu olemasolevas lahenduses.

Andmebaasi `vehicle_classes_json` on API klassikoodide ja kuvatavate nimetuste
autoriteetne allikas. Kui ONNX-mudeli metaandmetes on klassinimed olemas,
kontrollitakse käivitamisel, et klasside arv, indeksid ja koodid vastavad
profiili klassikaardile. Kui metaandmed puuduvad, kasutatakse profiili
klassikaarti.

Klassikaart peab:

- sisaldama vähemalt ühte klassi;
- kasutama järjestikuseid indekseid alates nullist;
- sisaldama unikaalseid koode;
- sisaldama iga koodi jaoks mittetühja kuvatavat nime;
- vastama mudeli väljundi tunnuste arvule `4 + klasside arv`.

Annotatsioonivärvid võivad jääda rakenduse esitluskihi otsuseks, kuid tundmatu
klass ei tohi põhjustada viga. Värv tuleb valida deterministlikult või
üldisest värvipaletist.

## 9. ROI-mask ja pildi eeltöötlus

### 9.1. Maski tähendus

ROI-mask jätab polügooni sisemuse muutmata ja täidab kõik polügoonist
väljapoole jäävad pikslid profiilis määratud värviga. `cam217` täitevärv on
`RGB(114, 114, 114)`. OpenCV BGR-kanalijärjekorras on halli väärtus sama, kuid
kood peab värviruumi selgelt eristama.

Normaliseeritud punkt `x, y` teisendatakse algpildi piksliks:

```text
x_px = round(x × pildi_laius)
y_px = round(y × pildi_kõrgus)
```

Koordinaadid piiratakse enne OpenCV polügooni loomist pildi lubatud
koordinaadivahemikku.

### 9.2. Eeltöötluse järjestus

Üldine eeltöötlusahel on:

```text
faili valideerimine
→ OpenCV dekodeerimine
→ algpildi säilitamine annotatsiooniks
→ ROI-mask algpildi mõõtudes
→ vajaduse korral kuvasuhet säilitav vähendamine
→ paigutamine mudeli mõõdus hallile lõuendile
→ BGR teisendamine RGB-ks
→ tensori moodustamine
→ inferents
```

Praegune skaleerimisreegel säilib:

- mudeli sisendisse mahtuvat pilti ei suurendata;
- liiga suur pilt vähendatakse kuvasuhet säilitades;
- pilt paigutatakse lõuendi vasakusse ülanurka;
- parem ja alumine vaba ala täidetakse väärtusega 114.

Mask rakendatakse enne skaleerimist, et polügoon vastaks samale algpildi
koordinaatsüsteemile, mida kasutati treeningandmete loomisel.

### 9.3. `cam217` hall lõuend

Tavaline `cam217` pilt on `1280 × 720` ja mudeli sisend on `1280 × 736`.
Pildi laiust ega kõrgust ei ole vaja skaleerida. ROI-mask ja alumine 16-piksline
hall ala saab moodustada ühe ettevalmistusetapi käigus:

1. luuakse kohe `736 × 1280` hall lõuend;
2. ROI-polügoon arvutatakse `1280 × 720` algpildi suhtes;
3. algpildist kopeeritakse lõuendile ainult ROI sisse jäävad pikslid;
4. polügoonist väljapoole jääv ala ja read 720–735 jäävad halliks.

Põhimõte:

```python
canvas = np.full((736, 1280, 3), 114, dtype=np.uint8)
canvas[:720, :1280][roi_mask] = original[roi_mask]
```

See ei pea olema kaks eraldi avalikku eeltöötlusoperatsiooni. Üldlahenduses
peab siiski säilima maskimise ja võimaliku vähendamise õige järjekord.

### 9.4. Analüüsiväljundi pilt

Mudeli inferents kasutab profiili korral maskitud pilti. API
`annotated_image` joonistab tuvastuskastid alati maskimata algpildile, et
kasutaja näeks loomulikku kaamerapilti. ROI piiri ega tumendust API pildi
pikslitesse ei lisata. Profiilide API annab UI-le normaliseeritud
ROI-polügooni punktid ning UI joonistab tulemuspildile punase katkendjoone ja
tumendab veidi polügoonist väljapoole jäävat ala. Kuvakihti saab lülitiga
peita ilma uut tuvastuspäringut tegemata. Uue pildi valimisel on kuvakiht taas
vaikimisi sees; ROI-polügoonita profiili korral lülitit ei näidata.

Esimeses etapis ei lisata API parameetrit `return_masked_image`. See tähendab,
et klient ei saa query-parameetriga valida, kas annotatsioon joonistatakse
algsele või maskitud pildile. Maskitud pilti kasutatakse inferentsil ja
treeningpaki ZIP-is, kuid tavaliseks analüüsiväljundiks jääb algpilt.

## 10. API leping

### 10.1. Profiilide loend

Lisatakse autentimist nõudev otspunkt:

```text
GET /api/camera-profiles
```

UI jaoks tagastatakse vähemalt:

- profiilikood, versioon ja nimi;
- `sort_order`;
- vaikeprofiili tunnus;
- mudelifailide järjestatud loend ja vaikemudel;
- klassikoodid ja kuvatavad nimed;
- profiili vaikimisi tuvastuslävend.

ROI-mask ja `source_image_url` ei ole praegusele analüüsi-UI-le vajalikud ning
neid ei pea selles vastuses väljastama.

### 10.2. Tuvastuspäring

Mõlemale tuvastusotspunktile lisatakse valikuline query-parameeter:

```text
profile=<profile_code>
```

Näide:

```text
POST /api/detect/image?profile=cam217&model=cam217.onnx
```

Reeglid:

- `profile` puudub: kasutatakse andmebaasi aktiivset vaikeprofiili;
- `model` puudub: kasutatakse profiili `model_files_json` esimest mudelit;
- antud `model` peab kuuluma valitud profiili mudeliloendisse;
- `conf` puudub: kasutatakse profiili `default_confidence` väärtust;
- tundmatu profiil annab `400 Bad Request` vastuse koos lubatud aktiivsete
  profiilikoodide loendiga;
- tundmatu või valitud profiili mittekuuluv mudel annab selge `400 Bad
  Request` vastuse.

Praegused `cross_class_dedup` ja `cross_class_iou_threshold` parameetrid ning
nende vaikeväärtuste loogika jäävad muutmata.

### 10.3. Tuvastusväljund

Väljundisse lisatakse tegelikult kasutatud profiil:

```json
{
  "profile": {
    "code": "cam217",
    "version": 1,
    "name": "Laagna tee / Mustakivi"
  },
  "conf": 0.45,
  "model": "cam217.onnx",
  "model_sha256": "...",
  "counts": {
    "bus": 2,
    "car": 17,
    "van-truck": 3
  }
}
```

Praegused mudeli nimi, kontrollsumma, pildi mõõdud, loendused, tuvastused,
ajatemplid ja klassideülese filtri väljad jäävad alles.

## 11. Analüüsi kasutajaliides

Pildi analüüsi juhtelemendid on järgmises loogilises järjekorras:

1. kaameraprofiil;
2. valitud profiili mudel;
3. tuvastuslävend;
4. klassideülene duplikaadifilter ja selle lävend;
5. „Näita kolme tasemega“ valik.

Profiilid kuvatakse `sort_order` järgi. Vaikimisi valitakse andmebaasi
vaikeprofiil.

Profiili vahetamisel:

- mudelivalik täidetakse valitud profiili mudelitega;
- valitakse profiili esimene ehk vaikemudel;
- tühja lävendivälja korral rakendub profiili vaikeväärtus;
- vana analüüsitulemus eemaldatakse;
- kolme taseme funktsioon jääb kasutatavaks.

Kolme taseme väärtused arvutatakse valitud profiili vaikeväärtusest:

```text
default
max(0.01, default - 0.20)
max(0.01, default - 0.40)
```

Võrdlustabeli klassiread moodustatakse profiili klassikaardist. Tulemuste
metaandmetes kuvatakse profiili nimi, versioon, kasutatud mudel ja tegelik
usalduslävend.

## 12. Treeningpildid

Tabelisse `training_images` lisatakse kohustuslik välisvõti:

```text
camera_profile_id → camera_profiles.camera_profile_id
```

Treeningkandidaadi loomise vorm ja API saavad profiili. Kandidaadi
eelmärgendus kasutab sama profiili, mudelit ja eeltöötlust nagu analüüs.

Kettale salvestatakse maskimata treeningpilt. See säilitab algse info, lubab
UI-s loomulikku pilti näidata ja võimaldab vajaduse korral hiljem uut maski
rakendada. YOLO märgendite koordinaadid jäävad salvestatud pildi mõõtude
suhtes.

`analysis_json` sisaldab auditeerimiseks vähemalt:

- profiilikoodi, versiooni ja nime;
- `camera_profile_id` väärtust;
- kasutatud ROI-maski hetkepilti või `null` väärtust;
- kasutatud klassikaardi hetkepilti;
- mudelifaili nime ja SHA-256 kontrollsummat;
- tegelikku eelmärgenduslävendit;
- klassideülese filtri tegelikke väärtusi;
- tuvastusi ja loendusi.

Hetkepilt tagab, et eksporditud treeningandmed vastavad kandidaadi loomisel
kasutatud konfiguratsioonile ka siis, kui profiilist luuakse hiljem uus
versioon.

Treeninguvaates lisatakse profiilifilter:

- vaikimisi valitakse andmebaasi vaikeprofiil;
- „Kõik profiilid“ sobib ülevaateks;
- iga kandidaadi kaardil kuvatakse profiili nimi ja versioon;
- pakitoimingud on lubatud ainult konkreetse profiili filtris;
- pakivalikus kuvatakse ainult sama profiili pakid.

## 13. Treeningpakid ja maskitud ZIP

Tabelisse `training_packages` lisatakse kohustuslik välisvõti:

```text
camera_profile_id → camera_profiles.camera_profile_id
```

Pakett luuakse ühe konkreetse profiiliversiooni jaoks. Server kontrollib iga
pildi lisamisel, et pildi ja paki `camera_profile_id` on samad. UI piirang ei
asenda serveripoolset tervikluskontrolli.

ZIP sisaldab:

```text
classes.txt
manifest.csv
maskitud pildid
YOLO .txt märgendid
```

`classes.txt` moodustatakse profiili klassikaardist `model_index` järjekorras.
Manifesti lisatakse vähemalt:

- `profile_code`;
- `profile_version`;
- mudelifail;
- mudeli SHA-256;
- pildi olemasolevad auditiväljad.

Maskitud pildi loomisel:

1. loetakse kettalt maskimata treeningpilt;
2. loetakse kandidaadi `analysis_json` sisse salvestatud maski hetkepilt;
3. mask rakendatakse pildi olemasolevas mõõdus;
4. pildi mõõtmeid ei muudeta;
5. maskitud pilt kodeeritakse ZIP-i;
6. YOLO märgend lisatakse muutmata kujul, sest mask ei muuda pildi mõõte ega
   koordinaatsüsteemi.

Pildi formaat säilib:

- PNG kodeeritakse PNG-na;
- JPEG kodeeritakse JPEG-na;
- JPEG-i kvaliteediks kasutatakse `TRAINING_JPEG_QUALITY` väärtust.

Maskita profiili korral lisatakse ZIP-i olemasolev maskimata pilt. Paketi
esimese allalaadimise lukustamise praegune loogika jääb alles.

## 14. Olemasolevate andmete migratsioon

Olemasoleva Oracle'i skeemi jaoks koostatakse eraldi migratsiooniskript.
Migratsiooni kavand:

1. luua `camera_profiles` sequence, tabel, piirangud ja indeksid;
2. lisada tegeliku praeguse mudeliloendiga „Pärnu mnt - Karja“ vaikeprofiil;
3. lisada `training_images.camera_profile_id` alguses nullable väljana;
4. siduda kõik olemasolevad treeningpildid vaikeprofiiliga;
5. lisada `training_packages.camera_profile_id` alguses nullable väljana;
6. siduda kõik olemasolevad treeningpakid vaikeprofiiliga;
7. muuta mõlemad väljad `NOT NULL` väljadeks;
8. lisada välisvõtmed ja vajalikud indeksid;
9. lisada `cam217` profiil pärast failinime, URL-i ja klassinime kinnitamist.

Värske skeemi loomiseks uuendatakse ka `db/schema/001_core_schema.sql`.
Migratsiooniskripti koostamine ei tähenda selle automaatset rakendamist.
Andmebaasi struktuuri ja andmeid muutva migratsiooni käivitamiseks tuleb saada
kasutaja eraldi luba.

## 15. Tagasiühilduvus

Olemasolev päring jääb tööle:

```text
POST /api/detect/image
```

Kui `profile` ja `model` puuduvad, kasutatakse:

- andmebaasi aktiivset vaikeprofiili;
- selle esimest mudelit;
- selle vaike-usalduslävendit;
- profiili maski, mis Pärnu mnt - Karja profiilil puudub.

Praegune mudeliparameeter jääb tööle, kui mudel kuulub vaikeprofiili:

```text
POST /api/detect/image?model=best.onnx
```

Tagasiühilduvus ei sõltu profiilinimest ega kõvakodeeritud
`parnu-mnt-karja` väärtusest, vaid andmebaasi `is_default` tunnusest.

`MODEL_DIR` jääb keskkonnamuutujaks. `MODEL_FILES_JSON` eemaldatakse alles
pärast seda, kui profiilid on andmebaasi migreeritud ja rakendus kasutab neid
autoriteetse allikana.

## 16. Veakäsitlus ja valideerimine

Rakendus ei käivitu vigase profiili- või mudelikonfiguratsiooniga. Veateade
peab nimetama profiilikoodi, versiooni ja võimaluse korral mudelifaili.

Käivitamisvea põhjustavad muu hulgas:

- aktiivse vaikeprofiili puudumine või mitu aktiivset vaikeprofiili;
- tühi või vigase kujuga `model_files_json`;
- mudelifaili puudumine või mudelikataloogist väljuv failitee;
- vigane või mittetäielik klassikaart;
- klassikaardi ja ONNX-väljundi vastuolu;
- muu kui kolme kanaliga mudelisisend;
- dünaamiline või vigane mudeli kõrgus või laius;
- vigane `default_confidence`;
- vigane ROI tüüp, täitevärv või polügoon;
- vähem kui kolm polügoonipunkti;
- normaliseeritud koordinaat väljaspool vahemikku 0 kuni 1.

Päringu ajal tagastatakse kliendiveana vähemalt:

- tundmatu profiil;
- suletud profiili kasutamine;
- valitud profiili mittekuuluv mudel;
- profiiliga vastuolus olev treeningpakk või treeningpilt.

## 17. Testimisettepanek

Enne testide käivitamist tuleb projekti tööreegli kohaselt uuendada ja
kasutajaga kooskõlastada `docs/testid.md`.

Minimaalne soovitatav automaattestide ulatus:

### 17.1. Profiilid ja mudelid

- aktiivne vaikeprofiil valitakse andmebaasi `is_default` järgi;
- null või mitu vaikeprofiili põhjustab selge käivitamisvea;
- profiilid järjestatakse `sort_order` järgi;
- mudel laaditakse ainult üks kord, kui mitu profiili kasutab sama faili;
- mudel peab kuuluma valitud profiili;
- `cam217` sisendkuju tuvastatakse kujul `1 × 3 × 736 × 1280`;
- vana mudeli sisendkuju jääb `1 × 3 × 576 × 1152`;
- dünaamiline kõrgus või laius lükatakse tagasi;
- profiili klassikaart valideeritakse ONNX-metaandmete ja väljundi vastu.

### 17.2. ROI-mask

- polügoonist väljaspool olev piksel muutub väärtuseks `(114, 114, 114)`;
- polügooni sees olev piksel jääb muutmata;
- maskita profiili pilt jääb muutmata;
- normaliseeritud punktid teisendatakse eri pildimõõtude korral õigesti;
- `1280 × 720` `cam217` pildist tekib `1280 × 736` tensor;
- ROI-väline ala ja alumised 16 pikslit on hallid;
- annotatsioon joonistatakse maskimata algpildile.

### 17.3. API

- profiili puudumisel kasutatakse andmebaasi vaikeprofiili;
- tundmatu profiil annab 400 ja lubatud profiilide loendi;
- vastus sisaldab kasutatud profiili koodi, versiooni ja nime;
- profiili vaikemudel ja vaike-usalduslävend rakenduvad;
- mudeli valimine profiili sees töötab;
- kolme lävendi päringud kasutavad sama profiili;
- vana profiili senine väljund ja klassijärjekord säilivad.

### 17.4. Treeningandmed

- igal kandidaadil on profiili välisvõti;
- UI ja API filtreerivad kandidaate profiili järgi;
- eri profiili pilti ei saa pakki lisada;
- `classes.txt` moodustatakse paki profiili klassikaardist;
- maskiga profiili ZIP-is olev pilt on maskitud;
- maskita profiili ZIP-is olev pilt jääb maskimata;
- ZIP-i mask tuleb kandidaadi salvestatud konfiguratsiooni hetkepildist;
- pildi mõõdud ja YOLO märgendi koordinaatsüsteem ekspordil ei muutu;
- olemasolevate pakkide lukustamise loogika jääb tööle.

### 17.5. UI leping

- profiilivalik on olemas ja kasutab API järjestust;
- vaikeprofiil valitakse `is_default` järgi;
- mudelivalik sõltub profiilist;
- analüüsi- ja treeningupäring saadavad profiili;
- klassiread ja nimetused tulevad profiilist;
- treeninguvaate profiilifilter ja profiilisildid on olemas;
- pakivalik ei kuva teise profiili pakke.

## 18. Dokumentatsiooni mõju

Teostuse käigus tuleb vähemalt uuendada:

- `README.md` – profiilivalik, API parameetrid, väljund ja keskkonnamuutujad;
- `docs/lähteülesanne.md` – dünaamilised mudelimõõdud, klassid ja profiilid;
- `db/erd.md` – `camera_profiles` tabel ning treeningpiltide ja -pakkide seosed;
- `db/schema/001_core_schema.sql` – värske skeemi täielik struktuur;
- `.env.example` – `MODEL_FILES_JSON` eemaldamine pärast migratsiooni;
- `docs/testid.md` – enne käivitamist kooskõlastatav testiplaan;
- OpenAPI kirjeldused – `profile` sisend ja profiili väljund;
- UI eestikeelne tõlkefail – profiili ja uute klasside tekstid.

## 19. Soovitatav teostamise järjekord

1. Koostada andmebaasi skeemimuudatus ja migratsioon, kuid mitte rakendada
   seda ilma eraldi loata.
2. Lisada repository tasemele profiilide lugemine ja valideerimine.
3. Eraldada mudelisessioon profiili eeltöötlusest ja klassikaardist.
4. Muuta mudeli sisendmõõt ONNX-mudelist loetavaks.
5. Lisada ROI-mask ja selle ühiktestid.
6. Lisada API profiilisisend ja profiiliväljund.
7. Lisada analüüsi-UI profiilivalik ja dünaamilised klassid.
8. Siduda treeningpildid ja treeningpakid profiiliga.
9. Lisada profiilipõhine treeninguvaade ja maskitud ZIP.
10. Uuendada testiplaan, käivitada ainult kinnitatud testid ning parandada
    dokumentatsioon.

## 20. Kinnitatud teostusotsused

- `cam217` originaalpildi URL on esialgu tühi ja seda kasutatakse alles
  tulevases automaatse pildihõive arenduses.
- Klassi `van-truck` eestikeelne kuvatav nimi on „Kaubik/veok“.
- Pärnu mnt - Karja vaikeprofiili migratsiooni mudeliloend võetakse serveri
  `.env` failist ning on `best v3.onnx`, `best v2.onnx`, `best.onnx`.
- „Kõik profiilid“ treeninguvaade jääb ainult ülevaateks. Pakitoimingud on
  lubatud üksnes konkreetse profiili filtris.
- `cam217` mudelifail on `cam217 v2.onnx`.
