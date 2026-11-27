# Kaamerate live view lahendus

## 1. Dokumendi päritolu

Dokumendi koostas OpenAI Codex 27. novembril 2026 kasutaja kirjeldatud
reaalajas kaameravaate ülesande, projekti olemasoleva koodi ja dokumentatsiooni
ning `cam217` kaamera tegeliku HTTP-vastuse kontrolli põhjal. Dokument kirjeldab
kinnitatud teostuslahendust; selle koostamisel ei muudetud rakenduse koodi,
andmebaasi ega käituskeskkonda.

## 2. Sisukord

- [3. Eesmärk ja ulatus](#3-eesmärk-ja-ulatus)
- [4. Kinnitatud põhiotsused](#4-kinnitatud-põhiotsused)
- [5. Kihtide vastutus](#5-kihtide-vastutus)
- [6. Andmemudeli muudatus](#6-andmemudeli-muudatus)
- [7. Kaameraprofiili API vastus](#7-kaameraprofiili-api-vastus)
- [8. Live-frame otspunkt](#8-live-frame-otspunkt)
- [9. Pildi muutuse kontroll ja töötsükkel](#9-pildi-muutuse-kontroll-ja-töötsükkel)
- [10. Olemasoleva tuvastusteenuse kasutamine](#10-olemasoleva-tuvastusteenuse-kasutamine)
- [11. Pildi ja ROI kuvamine](#11-pildi-ja-roi-kuvamine)
- [12. Seadete rakendumine ja kaadri elutsükkel](#12-seadete-rakendumine-ja-kaadri-elutsükkel)
- [13. Kasutajaliides](#13-kasutajaliides)
- [14. Loendurid](#14-loendurid)
- [15. Olek, vead ja samaaegsus](#15-olek-vead-ja-samaaegsus)
- [16. Välise kaamerapildi laadimise põhjendus](#16-välise-kaamerapildi-laadimise-põhjendus)
- [17. Mõju olemasolevale lahendusele](#17-mõju-olemasolevale-lahendusele)
- [18. Kontrollimine](#18-kontrollimine)
- [19. Teostamise järjekord](#19-teostamise-järjekord)

## 3. Eesmärk ja ulatus

Rakendusse lisatakse eraldi vahekaart **„Kaamerate live view“**. Vaade kuvab
valitud kaameraprofiili perioodiliselt uueneva pildi koos serveris joonistatud
tuvastuskastide ja brauseris kuvatava ROI-polügooniga.

Live-kiht laadib pildi profiili `source_image_url` aadressilt ja arvutab kohe
allalaaditud baitidest SHA-256 räsi. Muutumata pilti ei saadeta tuvastusse ega
brauserisse. Muutunud pilt saadetakse olemasolevasse
`POST /api/detect/image` teenusesse, mis tagastab tuvastuste JSON-i ja
kastidega JPEG-pildi. Brauser kasutab tulemuse kuvamiseks sama loogikat nagu
olemasolev ühe pildi analüüsivaade.

Lahendus ei ole videovoog ega objektide kaadritevaheline jälgimine. See on
perioodiliselt uuenevate staatiliste kaamerapiltide analüüs.

## 4. Kinnitatud põhiotsused

- Uue vahekaardi nimi on „Kaamerate live view“.
- Kaameravalikus kuvatakse ainult profiilid, mille `source_image_url` on
  määratud.
- Profiili intervall salvestatakse sekundites väljal
  `capture_interval_seconds`.
- Migratsioon määrab URL-iga olemasolevatele profiilidele intervalliks 5
  sekundit; URL-ita profiilide väärtus jääb `NULL`.
- Kasutaja saab intervalli live-vaates jooksvalt muuta.
- Pildi SHA-256 räsi arvutatakse backendis kohe pärast välisest allikast
  allalaadimist.
- Muutumata pildiga ei tehta midagi: tuvastust ei käivitata, brauserile ei
  saadeta uut tulemust ning ekraan jääb muutmata.
- Muutunud pilt saadetakse olemasolevasse `POST /api/detect/image` teenusesse.
- `POST /api/detect/image` lepingut ega vastutust ei muudeta.
- Tuvastus-API ei tea, kust pilt pärineb või miks see saadeti.
- Live-kiht vastutab laadimise, räsi võrdlemise, tuvastusteenuse kutsumise ja
  tulemuse brauserile edastamise eest.
- Brauser ei saada pilti backendile tagasi.
- Brauser kuvab olemasoleva `annotated_image` pildi ning kasutab ROI jaoks
  olemasolevat SVG-overlay loogikat.
- Canvasel tuvastuskastide joonistamist ei lisata.
- `include_image` parameetrit ei lisata.
- Eraldi JPEG-i väljastavat snapshot-otspunkti ei lisata.

## 5. Kihtide vastutus

### 5.1. Live-kiht

Live-kiht:

- võtab vastu valitud profiili ja live-vaate seaded;
- laadib välisest allikast pildi;
- arvutab lähtepildi SHA-256 räsi;
- võrdleb räsi brauseri viimati kuvatud pildi räsiga;
- jätab muutumata pildi töötlemata;
- saadab muutunud pildi olemasolevasse tuvastusteenusesse;
- lisab tuvastusteenuse vastusele lähtepildi räsi;
- tagastab tulemuse brauserile.

### 5.2. Tuvastus-API

Olemasolev `POST /api/detect/image`:

- võtab vastu JPEG- või PNG-pildi ja tuvastusparameetrid;
- valib profiili ja mudeli;
- rakendab profiili ROI-maski inferentsi sisendile;
- teeb tuvastuse;
- joonistab kastid ja sildid originaalpildile;
- tagastab loendurid, tuvastused, metaandmed ja `annotated_image` JPEG-i.

Tuvastus-API-sse ei lisata kaamera URL-i, intervalli, räsi võrdlemise ega
live-sessiooni loogikat.

### 5.3. Brauser

Brauser:

- käivitab ja peatab perioodilise live-tsükli;
- saadab live-kihile viimati edukalt kuvatud lähtepildi räsi ja valitud seaded;
- jätab `204 No Content` vastuse korral olemasoleva vaate puutumata;
- kuvab muutunud kaadri `annotated_image` pildi automaatselt;
- kuvab või peidab ROI SVG-kihi ilma uue API-päringuta;
- uuendab hetke- ja sessiooniloendureid;
- hoiab mälus ainult viimast edukat kaadrit ja sessiooni summasid.

## 6. Andmemudeli muudatus

Tabelisse `camera_profiles` lisatakse väli:

```sql
capture_interval_seconds NUMBER(10)
```

Väärtus peab olema positiivne täisarv. Selle tagamiseks lisatakse tabelile
kontrollpiirang:

```sql
CHECK (
    capture_interval_seconds IS NULL
    OR (source_image_url IS NOT NULL AND capture_interval_seconds >= 0)
)
```

Muudatus lisatakse nii uue skeemi loomise skripti kui ka eraldi migratsiooni
olemasoleva andmebaasi jaoks. Migratsiooni rakendamine muudab andmestruktuuri
ja vajab projekti tööreeglite järgi kasutaja eraldi luba.

Rakenduse `CameraProfile` andmeobjekt ja Oracle'i profiilipäring hakkavad uut
välja lugema. Väli on nullable. Migratsioon määrab väärtuse 5 ainult nendele
olemasolevatele profiilidele, millel on `source_image_url`. URL-ita profiilil
peab intervall olema `NULL`, sest seda infot ei kasutata. URL-iga profiili
`NULL` intervalli korral jääb UI väli tühjaks. URL-iga profiilil tähendab ka 0,
et automaatne seire pole seadistatud. Mõlemal juhul ei saa seiret käivitada
enne, kui kasutaja sisestab positiivse täisarvu.

## 7. Kaameraprofiili API vastus

Kaameraprofiili vastusesse lisatakse `source_image_url` ja
`capture_interval_seconds`:

```json
{
  "code": "cam217",
  "source_image_url": "https://ristmikud.tallinn.ee/last/cam217.jpg",
  "capture_interval_seconds": 5,
  "roi_polygon": [[0.032, 0.105], [0.098, 0.068]]
}
```

Näites on ROI-punktide loend lühendatud. Tegelik vastus sisaldab profiili kõiki
punkte ning juba olemasolevaid mudeli-, klassi- ja lävendiandmeid.

Live-vaade filtreerib profiilid brauseris `source_image_url` olemasolu järgi.
Kui sobivaid profiile ei ole, kuvatakse sellekohane teade ja seire käivitamise
nupp jääb keelatuks.

## 8. Live-frame otspunkt

### 8.1. Päring

```http
GET /api/camera-profiles/{profile_code}/live-frame
```

Otspunkt nõuab olemasolevat kasutajasessiooni. Päringu parameetrid on:

- `viewer_id` – ühe brauserivahekaardi juhuslik live-vaate identifikaator;
- `poll_interval_seconds` – selle vaataja pollimisintervall lease'i jaoks;
- `previous_hash` – brauseris viimati edukalt kuvatud lähtepildi SHA-256;
- `model` – valitud profiili mudel;
- `conf` – tuvastuslävend;
- `cross_class_dedup` – eri klasside duplikaatide eemaldamine, `0` või `1`;
- `cross_class_iou_threshold` – IoU lävend, kui filter on sisse lülitatud.

Brauser ei anna backendile välist URL-i. Live-kiht kasutab ainult aktiivse
kaameraprofiili andmebaasis määratud `source_image_url` väärtust.

### 8.2. Muutumata pildi vastus

Kui allalaaditud pildi räsi võrdub `previous_hash` väärtusega, vastab otspunkt:

```http
204 No Content
```

Selle vastuse korral ei kutsuta `POST /api/detect/image` teenust ja brauser ei
muuda pilti, ROI-d, loendureid ega viimase eduka analüüsi aega.

### 8.3. Muutunud pildi vastus

Muutunud pildi korral saadab live-kiht pildi `multipart/form-data` failina
olemasolevasse `POST /api/detect/image` teenusesse koos päringu mudeli-,
lävendi- ja filtriseadetega.

Mitme vaataja sama profiili, räsi ja seadekomplekti päringud kasutavad jagatud
single-flight-tuvastust ning sama cache'itud tulemust. Vaatajapõhist puhaste
kaadrite puhvrit, lease'e ja treeningusse saatmist kirjeldab eraldi dokument
[`live-view-cache-ja-treeningukaadri-lahendus.md`](live-view-cache-ja-treeningukaadri-lahendus.md).

Live-frame vastus säilitab olemasoleva `DetectionImageResult` struktuuri ja
lisab sellele lähtepildi räsi:

```json
{
  "image_sha256": "lähtepildi-sha256",
  "image_size": {"width": 1280, "height": 720},
  "counts": {"bus": 1, "car": 6, "van-truck": 0},
  "total": 7,
  "detections": [],
  "annotated_image": {
    "media_type": "image/jpeg",
    "base64": "olemasoleva-detect-image-vastuse-sisu"
  }
}
```

`annotated_image` Base64-vormingut ei lisata live-vaate jaoks: see on
olemasoleva `POST /api/detect/image` vastuse praegune vorming. Live-kiht
edastab selle tulemuse brauserile.

## 9. Pildi muutuse kontroll ja töötsükkel

Seire käivitamisel tehakse esimene päring kohe. Järgmine tsükkel algab valitud
intervalli möödumisel pärast eelmise tsükli lõppu. Tsüklid ei tohi kattuda.

Ühe tsükli töövoog on:

1. brauser saadab live-frame päringu koos viimati kuvatud pildi räsi ja tsükli
   alguses kehtivate seadetega;
2. live-kiht lisab välise pildi URL-ile cache-buster väärtuse ning laadib pildi;
3. live-kiht arvutab kohe allalaaditud baitidest SHA-256 räsi;
4. muutumata räsi korral tagastab live-kiht `204 No Content`;
5. muutunud räsi korral saadab live-kiht sama allalaaditud pildi
   `POST /api/detect/image` teenusesse;
6. tuvastusteenus tagastab JSON-i ja kastidega JPEG-i;
7. live-kiht lisab vastusele lähtepildi räsi ja tagastab tulemuse brauserile;
8. brauser kuvab `annotated_image` väärtuse automaatselt olemasoleva
   kuvamismehhanismiga;
9. brauser uuendab ROI-overlayd, hetke- ja sessiooniloendureid ning viimase
   eduka analüüsi aega;
10. pärast tsükli lõppu käivitatakse järgmise päringu taimer.

Lähtepilt liigub välisest kaamerast live-kihti ühe korra. Brauser saab ainult
valmis annotatsioonipildi ega saada seda backendile tagasi.

## 10. Olemasoleva tuvastusteenuse kasutamine

Live-kiht kasutab `POST /api/detect/image` teenust tavapärase HTTP API-na.
Pilt antakse teenusele samal viisil nagu olemasolevast UI-st tulev pilt:
`multipart/form-data` failina. Tuvastusparameetrid antakse olemasolevate query
parameetritena.

Live-kiht edastab sisemise päringu jaoks vajaliku autentitud kasutajakonteksti.
Tuvastusteenuse sisendit, väljundit ega ärireegleid live-vaate tõttu ei
muudeta. Live-kiht ei dubleeri ROI-maskimist, mudeli käivitamist,
duplikaadieemaldust ega kastide joonistamist.

## 11. Pildi ja ROI kuvamine

Olemasolev üksikpildi vaade kuvab `POST /api/detect/image` vastuse nii:

1. `annotated_image.media_type` ja `annotated_image.base64` ühendatakse
   `data:` URL-iks;
2. URL määratakse tulemuspildi `img.src` väärtuseks;
3. ROI-polügoon kuvatakse pildi peal eraldi SVG-kihina.

Live-vaade kasutab sama loogikat. Uue kaadri korral vahetatakse live-vaate
`img.src` automaatselt uue `annotated_image` vastu. Tuvastuskastid ja sildid on
juba serveri loodud JPEG-il ning frontend ei joonista neid uuesti.

ROI jääb brauseri SVG-kihiks, sest kasutaja peab saama seda ilma uue
API-päringuta kohe näidata ja peita. Live-vaate pildielemendi ja SVG-overlay
struktuur ning CSS kasutavad olemasoleva tulemuspildi lahendust.

Olemasolev ROI seadistamise funktsioon tehakse üldkasutatavaks, et nii
analüüsi- kui live-vaade annaksid sellele overlay elemendi, valitud profiili ja
ROI nähtavuse väärtuse.

Normaliseeritud `roi_polygon` punktid ja SVG `viewBox="0 0 1000 1000"`
tagavad, et sama piir skaleerub automaatselt iga uue kaadri mõõtudega. ROI
kuvamise lüliti mõjutab ainult piiri nähtavust; profiili ROI-mask rakendub
tuvastusteenuses inferentsile alati.

## 12. Seadete rakendumine ja kaadri elutsükkel

Iga live-tsükkel fikseerib käivitamise hetkel järgmised seaded:

- tuvastuslävend;
- valitud mudel;
- eri klasside duplikaatide eemaldamise lüliti;
- IoU lävend.

Kasutaja tehtud muudatused ei töötle olemasolevat kaadrit uuesti. Kui tsükkel
on juba pooleli, lõpetab see töö tsükli alguses kehtinud seadetega. Uued seaded
rakenduvad esimesele järgmisele muutunud pildile, mille tsükkel algab pärast
seadete muutmist.

Kui välise pildi räsi ei muutu, ei käivitata tuvastust üksnes seadete muutmise
tõttu. Ekraanil olev kaader ja selle tulemused jäävad samaks kuni järgmise
muutunud pildi eduka töötlemiseni.

Brauser hoiab mälus ainult:

- viimase edukalt kuvatud lähtepildi räsi;
- hetkel kuvatavat annotatsioonipilti;
- selle kaadri tuvastusvastust;
- sessiooni koondloendureid.

Vana kaader jääb nähtavale seni, kuni uus muutunud pilt on edukalt alla
laaditud, tuvastatud ja brauserisse vastu võetud. Seejärel asendatakse pilt ja
kaadri JSON ühe tervikuna ning vana kaadri andmetele viitavad mälureferentsid
eemaldatakse. Kaadrite ajalugu ei säilitata.

## 13. Kasutajaliides

Uuele vahekaardile lisatakse:

- kaameraprofiili valik ainult `source_image_url` väärtusega profiilidest;
- intervall sekundites, algväärtusega profiili
  `capture_interval_seconds`;
- mudelivalik nagu olemasoleval analüüsilehel;
- tuvastuslävend, vaikimisi valitud profiili väärtus 0,45;
- „Eemalda eri klasside duplikaadid“ lüliti, vaikimisi sees;
- IoU lävend, vaikimisi 0,8;
- ROI olemasolul „Näita tuvastuspiirkonda“ lüliti, vaikimisi sees;
- „Käivita seire“ ja „Peata seire“ nupp;
- „Värskenda kohe“ nupp;
- olekuindikaator;
- viimase eduka analüüsi aeg;
- järgmise päringuni jäänud sekundid;
- kastidega tulemuspilt ja ROI SVG-overlay;
- hetke- ja sessiooniloendurid.

Intervalli muutmine rakendub järgmise ooteperioodi arvutamisel. „Värskenda
kohe“ käivitab tsükli ilma intervalli lõppu ootamata, kuid ei tekita
paralleelpäringut.

Profiili vahetamine peatab aktiivse seire, eemaldab eelmise kaadri ja
tuvastused, nullib sessiooniloendurid ning võtab kasutusele uue profiili
vaikeintervalli, vaikemudeli ja tuvastuslävendi.

Live-tsükli päringud ei kasuta olemasolevat modaalset globaalset
laadimisindikaatorit. Vaade kuvab oma mitteblokeerivat olekut, et iga
viiesekundiline päring ei lukustaks ega vilgutaks kogu rakendust.

## 14. Loendurid

Loendurid luuakse dünaamiliselt valitud profiili `classes` loendist. Nii ei
eeldata, et kõigil profiilidel on samad klassid.

Kuvavorm on:

```text
Bussid: 1 (4)
Autod: 6 (15)
Kaubikud/veokid: 0 (2)
Kokku: 7 (21)
```

Sulgudeta arv on viimase edukalt analüüsitud pildi tulemus. Sulgudes arv on
kõigi sessiooni jooksul edukalt analüüsitud muutunud piltide tulemuste summa.

Muutumata pilt, allalaadimisviga või tuvastusviga loendureid ei suurenda.
Lehe uuesti laadimine ja profiili vahetamine nullivad sessiooniloendurid.
Seire peatamine, mudeli vahetamine, lävendi muutmine või filtriseadete muutmine
sessiooniloendureid ei nulli. Seetõttu võib sessioonisumma sisaldada eri
seadetega analüüsitud kaadreid.

Sessioonisumma ei tähenda unikaalsete sõidukite arvu. Sama sõiduk võib mitmes
järjestikuses muutunud kaadris summat mitu korda suurendada.

## 15. Olek, vead ja samaaegsus

Vaade eristab vähemalt järgmisi olekuid:

- seire peatatud;
- järgmise päringu ootamine;
- kaamerapildi laadimine;
- muutumata pilt;
- pildi analüüsimine;
- analüüs õnnestus;
- päring ebaõnnestus.

Vea korral jäävad viimane edukas pilt, ROI ja loendurid nähtavale. Kasutajale
kuvatakse vea tekst ning aktiivse seire korral jätkub järgmine plaaniline
tsükkel.

Ühe live-vaate kohta saab korraga olla pooleli ainult üks tsükkel. Peatamise,
profiilivahetuse või lehelt lahkumise järel saabunud vana vastus ei tohi enam
vaadet muuta. Uus kaader asendab vana alles siis, kui kogu live-frame päring on
edukalt lõppenud.

## 16. Välise kaamerapildi laadimise põhjendus

`cam217` tegelik pildiaadress on:

```text
https://ristmikud.tallinn.ee/last/cam217.jpg
```

Rakenduse avalik origin on:

```text
https://liiklus.fun-o.eu
```

27. novembril 2026 tehtud kontrollis vastas kaameraserver HTTP 200 ja
`image/jpeg` sisuga, kuid vastuses puudusid nii `Access-Control-Allow-Origin`
kui ka `Access-Control-Allow-Credentials`. Seetõttu ei saa rakenduse
JavaScript selle pildi baite otse `fetch()` kaudu lugeda.

Backend ei allu brauseri ristpäritolu piirangule. Live-kiht saab pildi
profiilis määratud URL-ilt alla laadida, räsi arvutada ja saata muutunud pildi
tuvastusteenusesse. Brauserile edastatakse ainult valmis annotatsioonipilt ja
tuvastuste JSON.

Välise päringu puhul kasutatakse cache-buster väärtust, piiratud timeout'i ja
mõistlikku vastuse mahupiirangut. Ebaõnnestunud välispäring teisendatakse
arusaadavaks live-frame API veaks.

## 17. Mõju olemasolevale lahendusele

Olemasolev analüüsivaade jääb kasutama `POST /api/detect/image` otspunkti ja
serveris genereeritud annotatsioonipilti. Selle kolme lävendi võrdlus,
üleslaaditud pildi treeningukandidaadid ja SVG-põhine ROI kuvamine jäävad
funktsionaalselt muutmata. Live-vaade saab lisaks pausil oleva puhta kaadri
räsi järgi treeningukandidaadiks saata.

Live-vaade kasutab eraldi DOM-elemente ja eraldi JavaScripti olekut. Analüüsi-
ja live-vaade jagavad:

- profiili- ja mudeliandmeid;
- klassinimede kuvamise loogikat;
- duplikaadieemalduse parameetrite koostamist;
- annotatsioonipildi data-URL-i loomist;
- ROI SVG seadistamise ja näitamise loogikat;
- tulemuse loendurite kuvamise abifunktsioone sobivas ulatuses.

Live-tsükli taimer, lähtepildi räsi, viimase kaadri olek ja sessiooniloendurid
on live-vaate eraldi olek.

Kasutajaliidese uued tekstid lisatakse eestikeelsesse tõlkefaili. README-d,
andmeskeemi kirjeldust ja API dokumentatsiooni uuendatakse koos teostusega.

## 18. Kontrollimine

Teostuse kontroll hõlmab vähemalt järgmisi juhtumeid:

- profiili API tagastab `source_image_url` ja
  `capture_interval_seconds` väärtused;
- live-vaates kuvatakse ainult URL-iga profiilid;
- live-frame laadib `cam217` JPEG-pildi ja arvutab selle räsi;
- puuduva profiili ja puuduva URL-i vead on korrektsed;
- sama `previous_hash` väärtusega pilt annab `204 No Content`;
- muutumata pilt ei käivita `POST /api/detect/image` päringut;
- muutunud pilt põhjustab ühe `POST /api/detect/image` päringu;
- live-frame edastab valitud mudeli, lävendi ja filtriseaded muutmata kujul;
- `POST /api/detect/image` leping töötab endisel kujul;
- brauser kuvab muutunud kaadri automaatselt olemasoleva `annotated_image`
  loogikaga;
- frontend ei joonista tuvastuskaste ise;
- mõlemad vaated kasutavad sama ROI SVG seadistamise loogikat;
- ROI lüliti näitab või peidab piiri kohe ilma API-päringuta;
- seadete muutmine ei töötle olemasolevat kaadrit uuesti;
- uued seaded rakenduvad esimesele järgmisele muutunud kaadrile;
- vana kaader jääb nähtavale kuni uue kaadri eduka töötlemiseni;
- sessioonisumma suureneb ainult eduka muutunud kaadri järel;
- profiili vahetamine peatab tsükli ja nullib sessiooni;
- aeglane päring ei tekita kattuvaid tsükleid;
- olemasolev analüüsi- ja treeninguvaade töötavad muutmata kujul.

Automatiseeritud testid kirjeldatakse enne nende käivitamist failis
`docs/testid.md`. Andmebaasimigratsiooni ega teste ei käivitata ilma kasutaja
eraldi loata.

## 19. Teostamise järjekord

1. Lisada skeemi ja migratsiooni `capture_interval_seconds`.
2. Laiendada Oracle'i profiilipäringut ja `CameraProfile` andmeobjekti.
3. Lisada profiili API vastusesse `source_image_url` ja
   `capture_interval_seconds`.
4. Lisada autentitud live-frame orkestreeriv otspunkt.
5. Ühendada live-frame otspunkt olemasoleva `POST /api/detect/image`
   teenusega ilma selle lepingut muutmata.
6. Lisada „Kaamerate live view“ vahekaart ja vaate HTML.
7. Teha olemasolev ROI SVG seadistamise loogika mõlema vaate jaoks
   korduvkasutatavaks.
8. Lisada live-vaate taimer, räsi olek, seadete hetkeseis ja automaatne
   annotatsioonipildi kuvamine.
9. Lisada live-vaate hetke- ja sessiooniloendurid.
10. Lisada tõlked ning responsiivne kujundus.
11. Uuendada README, andmemudeli kirjeldus ja testiplaan.
12. Rakendada migratsioon ja käivitada kokkulepitud kontrollid ainult pärast
    kasutaja vastavaid lubasid.
