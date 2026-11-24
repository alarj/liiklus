# Hinnang: Tallinna liikluse tuvastusmudel (projekti vahekokkuvõte)

Kursusetöö hinnang, aine: masinõppe alused. Põhineb täiendatud versioonil (441 kaadrit, 88 valideerimispilti)

## Üldmulje

Täiendatud versioon on märgatavalt tugevam: resolutsioon on ühtlustatud, andmestik on kirjeldatud klassipõhiselt ja v2 plaan on metoodiliselt mõtestatum. Nõrk koht on endiselt hindamise metoodika: väga väike valim ja jaotuse meetodi puudumine.

## Mis paranes

- **Resolutsioon klapib.** Treening käib `imgsz=1152`, eksport 1152×576, nii et mõõdetud mAP kehtib sihtmõõdul. ONNX-faili enda valideerimine 1152×576 juures oleks veel kena lisa.
- **Andmestik on kirjeldatud.** 441 kaadrit, 88 valideerimispilti, klassijaotus 11 bussi / 162 autot / 7 trammi, peegeldus ainult treeningule.
- **v2 plaan on metoodiliselt parem.** Kumulatiivne andmestik ja treenimine kogu kombineeritud komplektil lahendavad unustamise küsimuse. A/B-võrdlusskript on hea regressioonitööriist.
- **API käitumine on läbi mõeldud.** Hall täide paremale ja alla hoiab koordinaadid vasakust ülanurgast õigena ning suured pildid teisendatakse tagasi algse pildi mõõtkavasse.

## Mis jäi lahendamata

### 1. Väga väike valim klassides

7 trammi ja 11 bussi valideerimiskomplektis tähendab, et trammi "100% täpsus" ja mAP50 91,6% põhinevad seitsmel objektil. Üks tramm rohkem või vähem liigutab neid numbreid mitme protsendi võrra. Autode 94,3% ja trammide 91,6% vahet ei saa tõlgendada. Kirjutage see otse välja. Sama probleem puudutab klassipõhiseid lävesid: `tram: 0.25` valimine seitsme objekti põhjal on arvamus, mitte kalibreerimine.

### 2. Andmelekke oht

Kaadrid tulevad nüüd iga 5 sekundi järel, järjestikused kaadrid on seega veelgi sarnasemad. Jaotuse meetod (juhuslik, ajaline, päevade kaupa) on dokumendis kirjutamata. Kui jaotus oli juhuslik, on valideerimiskaadritel lähikaksikud treeningus ja mAP50 92,1% on optimistlik. Korduvate kaadrite eemaldamine aitab, aga ei asenda ajalist jaotust. Eraldi test-komplekti ei ole, kuigi `best.pt` ja `patience` kasutavad valideerimist.

### 3. v2 edu mõõtmine

Valideerimiskomplektis ei ole öö- ega hämarkaadreid, v2 on aga mõeldud just nende jaoks. Kui edu mõõdetakse samal komplektil, paranemist ei näe. Hoidke osa uutest rasketest kaadritest (öö, oksad) eraldi test-komplektis, mida treening ei näe, ja defineerige edumõõdik (nt trammi recall öösel) enne treeningut. A/B-skript näitab, kus mudelid erinevad, mitte kumb on õigem, sest testpiltidel pole märgendeid. See on hea visuaalne kontroll, aga mitte kvaliteedimõõdik.

### 4. Väikesed ebatäpsused

- 441 − 88 = 353 treeningpilti, kahekordistatuna \~706, mitte "\~800".
- `rect=True` ei sobi Ultralyticsis treeningul tavaliselt kokku segamisega. Kuna kõik kaadrid on ühesuurused, ei anna see midagi juurde, tasub kontrollida ja ära jätta.
- Erineva zoomi või kaamera nurgaga pildid võivad tuvastuskvaliteedis erineda, sest objektide suhteline suurus kaadris erineb treeningkaadritest. Suuruse määrab pildistatav ala, mitte vähendamine, mis säilitab kuvasuhted. Piirangute lõigus piisab ühest lausest.

### 5. Endiselt puudu

mAP50-95, segimatriks (väide "segiajamist ei esinenud" vajab seda), PR-kõverad, kaokõverad, `yolov8n` baseline, ARM64 ajamõõtmise tingimused (riistvara, korduskatsed, kas eel- ja järeltöötlus sisaldub) ning mõõtmise `conf` lävi.

## Mis kursuse seisukohalt puudu on

- **Teooria side:** IoU, mAP, precision/recall, overfitting, train/val/test eesmärk. Praegu on tööriistad esiplaanil, mõisted taustal.
- **Piirangute lõik:** üks kaamera, üks asukoht, üks aastaaeg, väike andmestik. Üldistusvõime teistele kaameratele on tundmatu.
- **Eetika/privaatsus:** lisage andmekogumise lõiku üks lause: kaamera on isiklik, filmitud avalikku ruumi oma kodu aknast, ning numbrimärgid ja näod pole eraldusvõime tõttu tuvastatavad. Eraldi eetikalõiku ei vaja. Andmestiku avalikustamisel (nt Roboflow avalik projekt) tasub lisada märkus, et kaadrid ei sisalda isikuandmeid.
- **Vorm:** kolm pikka koodiplokki keset teksti lõhuvad voolu. Kui kursus lubab, viige need lisadesse ja jätke põhitekstis lühike selgitus.

## Hinnang

Teostus ja dokumenteeritus on nüüd selgelt head ja v2 plaan on mõtestatum kui enne. Metoodika tõusis keskmisest keskmisest üle. Lõpuni viiks töö neli lisandust: jaotuse meetod ja lekke käsitlus, öökaadritega eraldi test-komplekt, märkus 7 trammi ja 11 bussi mõjust numbrite usaldusväärsusele ning segimatriks koos mAP50-95-ga. Kokku jääb see "hea", aga mitte "suurepärane".
