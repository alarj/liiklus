# Live-view tuvastuscache ja treeningukaadri säilitamine

## 1. Dokumendi päritolu

Dokumendi koostas OpenAI Codex 27. novembril 2026 kasutajaga peetud
lahendusarutelu, projekti olemasoleva live-view teostuse ning
`kaamerate-live-view-teostusplaan.md` põhjal. Dokument kirjeldab kokkulepitud
lahendust; selle koostamisel ei muudeta rakenduse koodi, andmebaasi ega
käituskeskkonda.

## 2. Sisukord

- [3. Lahendatavad probleemid](#3-lahendatavad-probleemid)
- [4. Eesmärk ja ulatus](#4-eesmärk-ja-ulatus)
- [5. Põhimõisted](#5-põhimõisted)
- [6. Lahenduse ülevaade](#6-lahenduse-ülevaade)
- [7. Jagatud tuvastustulemuste cache](#7-jagatud-tuvastustulemuste-cache)
- [8. Puhaste originaalkaadrite hoidla](#8-puhaste-originaalkaadrite-hoidla)
- [9. Vaatajapõhine kahe kaadri puhver](#9-vaatajapõhine-kahe-kaadri-puhver)
- [10. Lease ja brauseri kadumise tuvastamine](#10-lease-ja-brauseri-kadumise-tuvastamine)
- [11. Seire peatamine](#11-seire-peatamine)
- [12. Live-kaadri saatmine treeningusse](#12-live-kaadri-saatmine-treeningusse)
- [13. Cache'ide koristusreeglid](#13-cacheide-koristusreeglid)
- [14. Samaaegsus ja päringute järjekord](#14-samaaegsus-ja-päringute-järjekord)
- [15. API-lepingu täiendused](#15-api-lepingu-täiendused)
- [16. Kasutajaliidese käitumine](#16-kasutajaliidese-käitumine)
- [17. Mälu piiramine](#17-mälu-piiramine)
- [18. Veakäitumine](#18-veakäitumine)
- [19. Mitme protsessi piirang](#19-mitme-protsessi-piirang)
- [20. Kinnitatud reeglite kokkuvõte](#20-kinnitatud-reeglite-kokkuvõte)

## 3. Lahendatavad probleemid

### 3.1. Tuvastus-API kui kriitilise ressursi koormus

Ühe pildi töötlemine tuvastusmudeliga võtab ligikaudu 0,5 sekundit. Kaamera
JPEG-pildi allalaadimine ja SHA-256 räsi arvutamine ei ole selle kõrval
kriitilised ressursid.

Praeguses live-view töövoos käivitab iga brauser oma pollimistsükli. Kui mitu
brauserit jälgivad sama profiili sama mudeli, lävendi ja filtriseadetega, võivad
nad saata sama kaadri tuvastus-API-sse mitu korda. Brauseri `previous_hash`
väldib kordust ainult ühe brauseri piires; see ei jaga tulemust eri brauserite
vahel.

Näiteks kahe viiesekundilise, kuid ajaliselt nihkes pollija korral võib teine
brauser saata sama kaadri mudelisse mõni sekund pärast esimest. Kahekümne
vaataja korral võib üks unikaalne kaader põhjustada kuni kakskümmend identset
inferentsi. Eesmärk on teha ühe unikaalse kaadri ja ühe seadekomplekti kohta
ainult üks tuvastus-API päring sõltumata vaatajate arvust ja
pollimisintervallidest.

### 3.2. Ärivajadus fikseerida puhas treeningpilt

Live-vaates kuvatakse kasutajale kastidega pilt, kuid treeningkandidaadiks tuleb
salvestada sama kaadri puhas, kastideta originaalpilt. Brauser ei tohi pilti
backendile tagasi saata. Treeningusse saatmisel edastab brauser kaadri räsi ja
metaandmed; backend leiab räsi järgi varem allalaaditud puhta originaali.

Treeninguks huvipakkuva kaadri märkamisel võib kasutaja seire peatada hetkel,
mil üks järgmine live-päring on juba pooleli. Samal ajal võivad teised brauserid
sama profiili edasi jälgida. Seetõttu ei piisa profiili kohta kahest viimasest
kaadrist: kiirema või jätkava vaataja päringud lükkaksid aeglasema või pausile
pandud vaataja ekraanil oleva originaali ühispuhvrist välja.

Backend peab säilitama iga live-vaate kaks viimast kuvatud puhast kaadrit nii,
et ühe vaataja polling ei eemaldaks teise vaataja ekraanil olevat kaadrit.

## 4. Eesmärk ja ulatus

Lahendus lisab olemasolevale live-kihile:

- jagatud tuvastustulemuste cache'i;
- sama cache-võtme samaaegseid päringuid koondava single-flight-loogika;
- räsi järgi deduplikeeritud puhaste originaalkaadrite mäluhoidla;
- iga brauseri vahekaardi ehk live-vaate kahe kaadri puhvri;
- lease'i ja heartbeat'i põhise koristuse;
- pausil kuvatava kaadri fikseerimise;
- live-kaadri treeningkandidaadiks salvestamise.

Lahendus ei muuda üldise `POST /api/detect/image` tuvastus-API vastutust.
Kaamera laadimise, räsiarvutuse, cache'i, single-flight'i ja vaataja oleku eest
vastutab live-kiht. Tuvastus-API võtab endiselt vastu pildi ning tagastab
tuvastustulemuse, teadmata pildi päritolu või kasutusotstarvet.

## 5. Põhimõisted

**Puhas kaader** on välisest kaameraallikast laaditud JPEG- või PNG-pilt enne
ROI-maskimist ja tuvastuskastide joonistamist.

**Tuvastustulemus** on `POST /api/detect/image` tagastatud JSON koos kastidega
`annotated_image` pildiga.

**Vaataja** on üks brauseri vahekaart ehk üks live-view instants. Sama kasutaja
kaks vahekaarti on kaks eri vaatajat.

**`viewer_id`** on brauseri vahekaardis loodud juhuslik identifikaator. See ei
ole autentimistunnus ega saladus; kasutaja tuvastamiseks kasutatakse endiselt
olemasolevat sessiooni.

**Lease** on serveripoolne ajaliselt piiratud õigus hoida vaataja olekut ja
selle kaadriviiteid elus. Lease'i uuendavad live-päringud või pausil oleva
vaate heartbeat.

**Single-flight** tähendab, et sama cache-võtme samaaegsetest päringutest ainult
üks kutsub tuvastus-API-t ning ülejäänud ootavad sama poolelioleva töö tulemust.

## 6. Lahenduse ülevaade

Ühe live-päringu töövoog on:

1. brauser saadab profiili, `viewer_id`, viimati kuvatud räsi ja
   tuvastusseaded;
2. live-kiht laadib kaamera hetke JPEG-i ja arvutab SHA-256 räsi;
3. live-kiht lisab puhta pildi räsi järgi originaalkaadrite hoidlasse või
   kasutab seal juba olevat sama pilti;
4. kui räsi võrdub selle brauseri `previous_hash` väärtusega, uuendatakse
   vaataja lease'i ja tagastatakse `204 No Content`;
5. uue räsi korral kontrollitakse jagatud tuvastustulemuste cache'i;
6. valmis tulemuse korral kasutatakse seda ilma tuvastus-API päringuta;
7. poolelioleva sama võtme korral oodatakse olemasolevat single-flight-tööd;
8. cache-miss'i korral käivitab üks päring tuvastus-API;
9. enne vastuse saatmist seob backend puhta kaadri vaataja kahe kaadri
   puhvriga;
10. sama tuvastustulemus saadetakse eraldi igale seda vajavale brauserile.

Brauseritele vastuste saatmine jääb vaatajapõhiseks. Jagatakse kriitilist
tuvastustööd, mitte brauseri HTTP-vastust.

### 6.1. Välise kaamerapäringu coalescing

Sama profiili täpselt samaaegsed välised kaamerapäringud koondatakse üheks
pooleliolevaks tööks. Esimene päring laadib kaamera JPEG-i ning teised samal
ajal saabunud päringud ootavad sama tulemust. See vähendab välise
kaameraserveri koormust, kuid ei ole tuvastustulemuste cache'i asendus.

Esialgses lahenduses ei hoita lõpetatud välise kaamerapäringu tulemust eraldi
1–2-sekundilises cache'is. Pärast poolelioleva päringu lõppu võib järgmine
mittekattuv poll laadida kaamerast uue pildi. Nii ei lisata live-vaatele
kokkuleppimata kunstlikku pildi vanust. Lühikese valmis pildi cache'i võib
hiljem lisada eraldi otsusena, kui välise allika koormus seda nõuab.

## 7. Jagatud tuvastustulemuste cache

### 7.1. Cache-võti

Tuvastustulemuse cache-võti sisaldab vähemalt:

```text
profile_code
image_sha256
model
confidence
cross_class_dedup
cross_class_iou_threshold
```

Pollimisintervall ei kuulu cache-võtmesse. Erineva intervalliga brauserid
kasutavad sama tulemust, kui pildiräsi ja tuvastusseaded kattuvad.

### 7.2. Põhikoristusreegel

Tuvastustulemuste cache'i põhikoristusreegel on:

> Uus unikaalne kaader asendab profiili eelmise kaadri tuvastustulemused.

Profiili kohta hoitakse cache'is ainult kõige uuema teadaoleva kaadri
tuvastustulemusi. Uue räsi saabumisel eemaldatakse eelmise räsi valmis JSON-id
ja kastidega pildid kohe. Vanad tuvastustulemused ei ole live-vaate jaoks
vajalikud, sest iga pollija saab päringu hetkel kõige uuema kaamerapildi.

TTL ei juhi tavapärast kaadrivahetust. Keskkonnaseade
`LIVE_HOT_CACHE_TTL_SECONDS` määrab ainult viimase kaadri varukoristuse juhuks,
kui profiili enam ei pollita ja uut kaadrit ei saabu. Esialgne väärtus on 15
sekundit.

### 7.3. Single-flight

Kui mitu päringut saavad sama cache-miss'i samaaegselt, peab üks neist saama
cache-võtme töö omanikuks. Teised päringud ootavad sama tulemust. Cache'i
kontroll tehakse uuesti pärast võtmekohase lukustuse saamist.

Sama profiili, räsi ja seadete korral tähendab see:

```text
20 live-frame päringut
20 brauserile saadetavat vastust
1 tuvastus-API päring
1 mudeli inferents
```

Single-flight peab olema cache-võtme põhine. Ühe profiili või kaadri töötlus ei
tohi põhjendamatult blokeerida teise profiili või erinevate seadete töötlust.

### 7.4. Pooleliolev vana tuvastus

Kui uue kaadri räsi saabub ajal, mil eelmise kaadri inferents on pooleli, ei
tohi vana töö tulemus muutuda profiili uusimaks cache-kirjeks. Inferentsi lõpus
kontrollitakse, kas töödeldud räsi vastab endiselt profiili uusimale räsile.

Vana tulemust võib kasutada ainult päring, mis seda juba ootas. Ühisesse
viimase kaadri cache'i seda enam ei lisata.

## 8. Puhaste originaalkaadrite hoidla

Puhaste piltide hoidla on tuvastustulemuste cache'ist eraldi. See sisaldab
räsi järgi indekseeritud puhtaid pilte ja nende minimaalset metaandmestikku:

```text
camera_profile_id
image_sha256
image bytes
media type
source filename
image width and height
created/accessed time
reference count or equivalent viewer references
```

Sama profiili ja sama räsi JPEG-i hoitakse mälus ühe eksemplarina. Mitu
vaatajat võivad viidata samale kaadriobjektile. Vaatajapuhvrid ei kopeeri pildi
baite.

Originaalkaadri eluiga ei võrdu tuvastustulemuse lühikese TTL-iga. Puhas pilt
säilib seni, kuni vähemalt üks järgmistest tingimustest kehtib:

- pilt kuulub üldisesse lühikesse hot-cache'i perioodi;
- aktiivse vaataja kahe kaadri puhver viitab sellele;
- pausil oleva vaataja lease viitab sellele;
- käimasolev treeningusse salvestamine kasutab seda.

## 9. Vaatajapõhine kahe kaadri puhver

Kahe kaadri puhver ei ole ainult profiilipõhine. Puhvri võti on:

```text
(camera_profile_id, viewer_id)
```

Iga vaataja puhver sisaldab maksimaalselt kahe viimase sellele vaatajale
edukalt kuvatud puhta kaadri räsi. Kaader seotakse vaatajaga enne vastuse
brauserile saatmist. Nii on serveris vastav puhas originaal juba alles hetkel,
mil brauser pildi ekraanile kuvab.

Kui A peatab seire kaadril X ja B jätkab sama profiili pollimist, muudab B
ainult enda puhvrit. B uued kaadrid ei eemalda X-i, sest A puhver viitab sellele
endiselt.

Näide:

```text
A puhver: [W, X]  ← A peatub kaadril X
B puhver: [Y, Z]  ← B jätkab

ühine puhaste piltide hoidla: W, X, Y, Z
```

Kui mitu vaatajat näevad sama kaadrit X, on hoidlas üks X JPEG ning mitu
räsiviidet.

## 10. Lease ja brauseri kadumise tuvastamine

Lahendus ei eelda, et brauser teatab vaate sulgemisest. Kasutaja võib sulgeda
vahekaardi, sulgeda brauseri, kaotada võrguühenduse või sisestada aadressiribale
uue URL-i. `beforeunload`, `sendBeacon` ja muud sulgemisteated võivad olla
abistavad, kuid need ei ole koristuse eeltingimus.

Aktiivse seire iga live-päring uuendab vaataja lease'i. Lease peab olema
konfigureeritav ning pollimisintervallist piisavalt pikem, et tavapärane
võrguviivitus või brauseri taustataimerite aeglustamine ei eemaldaks aktiivset
vaatajat.

Kui live-päringuid ega pausil oleva vaate heartbeat'i enam ei saabu, lease
aegub. Seejärel:

1. eemaldatakse vaataja olek;
2. vabastatakse tema kaadriviited;
3. viideteta puhas pilt muutub üldise koristuse kandidaadiks.

## 11. Seire peatamine

Seire peatamisel fikseerib UI ekraanil oleva `image_sha256` ja saadab backendile
vaataja pausioleku. Backend kontrollib, et vastav räsi kuulub selle vaataja
puhvrisse, ning jätab ekraanil oleva puhta kaadri lease'i alla.

Pausil ei tehta kaamera- ega tuvastuspäringuid. UI saadab ainult kerge
heartbeat'i, mis pikendab pausil oleva vaataja lease'i. Heartbeat ei sisalda
pilti ega käivita tuvastusmudelit.

Pausi heartbeat'i intervall tuleb keskkonnaseadest
`LIVE_PAUSE_HEARTBEAT_SECONDS`; esialgne väärtus on 60 sekundit. Pausi lease
tuleb keskkonnaseadest `LIVE_PAUSE_LEASE_SECONDS`; esialgne väärtus on 300
sekundit ehk 5 minutit.

Iga edukas heartbeat pikendab lease'i uuesti 300 sekundini. Viie minuti pikkune
lease jätab varu brauseri taustavahekaardi taimerite aeglustamiseks ja üksikute
heartbeat'ide hilinemiseks. Kui pausil vahekaart suletakse, heartbeat lõpeb
ning server koristab vaataja ja tema viited hiljemalt lease'i aegumisel.

Pausile minnes võib vaataja varasema kaadri viite vabastada ja alles jätta
ainult ekraanil oleva kaadri. See vähendab mälu kasutust ega halvenda
treeningusse saatmise kasutusjuhtu.

## 12. Live-kaadri saatmine treeningusse

### 12.1. UI reegel

Nupp **„Saada treeningusse“** on live-vaates nähtav ainult siis, kui:

- seire on peatatud;
- ekraanil on vähemalt üks edukalt analüüsitud kaader;
- selle kaadri `image_sha256` on olemas.

Nupp kasutab täpselt ekraanil oleva kaadri räsi. Teise brauseri uuemad kaadrid
ega backendis olev profiili uusim kaader ei muuda valikut.

Nupp avab sama põhjuste ja siltide dialoogi, mida kasutab ühe pildi
analüüsivaade. Dialoogi avamisel fikseeritakse sihtprofiil ja pildiräsi, et
hilisem UI olekumuutus ei muudaks salvestatavat kaadrit.

### 12.2. Backendi töö

Brauser ei saada pilti tagasi. Päring sisaldab vähemalt:

```text
profile_code
image_sha256
reason
tags
```

Lisaks edastatakse treeningkandidaadi eelmärgistuseks vajalik mudeli- ja
filtrikonfiguratsioon sama põhimõtte järgi nagu ühe pildi analüüsivaatest
treeningusse saatmisel.

Backend:

1. kontrollib kasutajasessiooni ja CSRF-kaitset;
2. leiab profiili ja räsi järgi puhta kaadri;
3. kontrollib, et kaader on endiselt vaataja lease'i all;
4. kasutab olemasolevat treeningkandidaadi loomise äriloogikat;
5. salvestab puhta, kastideta originaalpildi;
6. loob YOLO eelmärgistuse olemasoleva treeninguloogika järgi;
7. rakendab olemasolevat sama profiili duplikaadikontrolli;
8. tagastab loodud kandidaadi metaandmed.

Live-tuvastuse kastidega JPEG-i ei salvestata treeningpildiks. Brauserist ei
saadeta tuvastuskaste tagasi serverisse. Vajadusel teeb treeningkandidaadi
loomine ühe eraldi inferentsi olemasoleva treeninglävendi järgi; see on
kasutaja teadliku treeningutoimingu kulu, mitte live-seire korduv kulu.

## 13. Cache'ide koristusreeglid

### 13.1. Tuvastustulemused

1. Uus unikaalne kaader eemaldab profiili eelmise kaadri valmis
   tuvastustulemused.
2. Pooleliolev vana tulemus ei tohi pärast valmimist uut tulemust üle kirjutada.
3. Viimase kaadri lühike TTL on ainult varukoristus, kui uut kaadrit ei saabu.

### 13.2. Puhas originaal

Puhas originaal eemaldatakse alles siis, kui:

- ükski aktiivne ega pausil vaataja sellele ei viita;
- ükski käimasolev toiming seda ei kasuta;
- selle üldine hot-cache periood on lõppenud.

### 13.3. Vaataja olek

Vaataja eemaldatakse lease'i aegumisel. Brauseri sulgemisteade võib koristust
kiirendada, kuid selle puudumine ei takista ega lükka koristust lõputult edasi.

## 14. Samaaegsus ja päringute järjekord

Kaamerapäringutele määratakse profiilipõhine kasvav generatsioon. Varem
alustatud, kuid hiljem lõppenud päring ei tohi uuema päringu kaadrit profiili
uusima kaadrina tagasi vanemaks muuta.

Single-flight'i olekud on vähemalt:

```text
missing
processing
ready
failed/removed
```

Tuvastusvea korral ei jäeta ebaõnnestunud tulemust pikaajaliselt cache'i.
Pooleliolevat tööd oodanud päringud saavad sama vea ning järgmine sobiv päring
võib uuesti proovida.

Cache'i ja viidete muudatused peavad olema lukuga kaitstud. Kallis
tuvastusmudeli töö ei tohi toimuda globaalse cache-luku all; lukk kaitseb ainult
oleku lugemist ja muutmist.

## 15. API-lepingu täiendused

Teostuses kasutatakse järgmisi otspunkte.

### 15.1. Live-frame

Olemasolev live-frame päring saab lisaks `viewer_id` ja kasutaja valitud
pollimisintervalli. Pollimisintervalli kasutatakse lease'i kestuse arvutamiseks,
mitte tuvastustulemuse cache-võtmena.

```http
GET /api/camera-profiles/{profile_code}/live-frame
```

### 15.2. Paus ja heartbeat

Pausioperatsioon seob vaataja ekraanil oleva räsi pausilease'iga. Eraldi kerge
heartbeat pikendab lease'i ilma kaamerat või tuvastus-API-t kutsumata. Backend
annab UI-le konfiguratsioonina heartbeat'i intervalli, et brauser ei dubleeriks
keskkonnaseadet kõvakodeeritud väärtusena.

```http
POST /api/camera-profiles/{profile_code}/live-viewers/{viewer_id}/pause
POST /api/camera-profiles/{profile_code}/live-viewers/{viewer_id}/heartbeat
```

### 15.3. Treeningkandidaat puhverdatud live-kaadrist

Eraldi treeninguoperatsioon võtab vastu profiili, pildiräsi, põhjuse, sildid ja
vajaliku eelmärgistuse konfiguratsiooni. Pildi baite päringus ei ole.

```http
POST /api/training-pool/live-frame
```

Pausile fikseeritud vaataja lease'i ei tohi muuta aktiivseks ükski enne pausi
alanud, kuid pärast pausi lõppenud live-frame päring. Iga uus seirekäivitus saab
uue `viewer_id`; nii jääb eelmise pausiseansi täpne kaader lease'i lõpuni
üheselt seotuks.

Kõik operatsioonid kasutavad olemasolevat autentimist. Oleku muutvad päringud
kasutavad olemasolevat CSRF-kaitset. `viewer_id` ei asenda autentimist.

## 16. Kasutajaliidese käitumine

- Iga live-vaate brauserivahekaart loob mälus juhusliku `viewer_id`.
- `viewer_id` püsib sama kuni vahekaardi laadimise lõpuni.
- Aktiivne live-päring uuendab lease'i.
- Seire peatamine fikseerib ekraanil oleva profiili ja pildiräsi.
- Pausil vaade saadab iga 60 sekundi järel kerget heartbeat'i ning iga edukas
  heartbeat pikendab viieminutilist pausi lease'i.
- „Saada treeningusse“ kuvatakse ainult pausil ja olemasoleva kaadri korral.
- Seire jätkamisel lõpetatakse pausi heartbeat ning tavapärane polling jätkab
  lease'i uuendamist.
- Lehe sulgemisel ei eeldata edukat lõpetamispäringut.

## 17. Mälu piiramine

TTL-i ja lease'ide kõrval kasutatakse konfigureeritavat cache'i maksimaalse
mahu piirangut. Kokkulepitud esialgsed keskkonnaseaded on:

```dotenv
LIVE_CACHE_MAX_MB=128
LIVE_HOT_CACHE_TTL_SECONDS=15
LIVE_PAUSE_HEARTBEAT_SECONDS=60
LIVE_PAUSE_LEASE_SECONDS=300
```

Cache'i mälupiirangu algväärtus on 128 MB. Väärtus ei ole rakenduskoodi sisse
kirjutatud ning selle võib serveri mäluvaru korral tõsta näiteks 256 MB-ni.
Hot-cache'i 15-sekundiline TTL on tuvastustulemuste viimase kaadri
varukoristus ning viideteta puhta originaali lühike säilitusaeg. Pausi
heartbeat on 60 sekundit ja pausi lease 300 sekundit.

Teostamisel lisatakse kõik neli seadet `.env.example` faili koos ühikute ja
vaikekäitumise kirjeldusega. UI jaoks vajalik heartbeat'i intervall edastatakse
serveri konfiguratsioonivastuses; seda ei kirjutata JavaScripti eraldi
konstandina.

Piirang arvestab tegelikult cache'is hoitavaid baite, vähemalt puhaste piltide,
kastidega Base64-piltide ja tuvastustulemuste JSON-i mahtu. Piirangut ei
arvutata oletusliku kaadrite arvu järgi.

Koristusjärjekord on:

1. aegunud ja viideteta kirjed;
2. viideteta LRU-kirjed;
3. aegunud vaatajate viited;
4. aktiivse lease'iga kaadreid ei eemaldata tavapärase LRU tõttu.

Üks vaataja hoiab aktiivses olekus maksimaalselt kahte räsiviidet ja pausil
üht fikseeritud räsiviidet. Sama JPEG-i jagavad vaatajad ei suurenda pildi
baidimahu kasutust vaatajate arvuga võrdeliselt.

Rakendus peab piirama ka ühe pildi maksimaalset lubatud suurust olemasoleva
üleslaadimispiirangu põhimõttel. Cache'i täitumine ei tohi põhjustada kogu
protsessi kontrollimatut mälukasvu.

## 18. Veakäitumine

Kui treeningusse saadetavat räsi puhaste piltide hoidlas enam ei ole, tagastab
backend konkreetse veateate, et kaader ei ole enam saadaval. UI jätab seire
peatatuks ja võimaldab kasutajal seiret jätkata ning valida uue kaadri.

Kui sama profiili ja räsi treeningkandidaat on juba aktiivselt olemas,
rakendatakse olemasolevat duplikaadikontrolli ning tagastatakse konflikt.

Tuvastus-API vea korral ei asendata brauseris viimast edukat kaadrit ega
salvestata vigast cache-kirjet. Teised sama single-flight-tööd oodanud päringud
saavad sama ebaõnnestumise.

## 19. Mitme protsessi piirang

Mälus olev cache, single-flight ja vaatajapuhvrid töötavad protsessi piires.
Praeguse ühe API protsessi korral on see piisav.

Kui backend käivitatakse hiljem mitme protsessi või replika kujul, ei taga
protsessipõhine lukk enam ühte tuvastust unikaalse kaadri kohta. Sel juhul tuleb
cache, lease'id ja single-flight koordineerida jagatud hoidla kaudu, näiteks
Redise abil, või tagada sama profiili päringute püsiv suunamine samale
protsessile. Seda keerukust ei lisata enne, kui käitusmudel seda nõuab.

## 20. Kinnitatud reeglite kokkuvõte

- Kriitiline ressurss on tuvastusmudeliga API, mitte kaamera JPEG-i laadimine.
- Sama profiili, pildiräsi ja tuvastusseadete korral tehakse üks inferents.
- Single-flight väldib samaaegsete cache-miss'ide dubleerimist.
- Sama profiili samaaegsed välised kaamerapäringud kasutavad ühist
  pooleliolevat allalaadimist; lõpetatud kaamerapildile eraldi 1–2-sekundilist
  cache'i esialgu ei lisata.
- Pollimisintervall ei kuulu tuvastustulemuse cache-võtmesse.
- Tuvastustulemuste põhikoristusreegel on „uus kaader asendab eelmise“.
- `LIVE_HOT_CACHE_TTL_SECONDS=15` on ainult viimase kaadri varukoristus ja
  viideteta puhta originaali lühike hot-cache periood.
- Puhas originaal ja tuvastustulemus on eri elutsükliga cache-kirjed.
- Puhas JPEG deduplikeeritakse profiili ja SHA-256 räsi järgi.
- Igal live-vaatel on oma kahe kaadri räsipuhver.
- Ühe vaataja polling ei eemalda teise vaataja ekraanil olevat kaadrit.
- Kaader seotakse vaatajaga enne vastuse brauserile saatmist.
- Aktiivne polling uuendab vaataja lease'i; pausil saadetakse heartbeat iga 60
  sekundi järel ning pausi lease on 300 sekundit.
- Brauseri sulgemisteatele ei loodeta; puuduv heartbeat põhjustab lease'i
  aegumise ja koristuse.
- „Saada treeningusse“ on nähtav ainult peatatud seire ja olemasoleva kaadri
  korral.
- Treeningusse saadetakse profiil, räsi ja metaandmed, mitte pildi baidid.
- Treeningkandidaadina salvestatakse puhas, kastideta originaal.
- Cache'i mälukasutusel on lisaks TTL-idele keskkonnaseade
  `LIVE_CACHE_MAX_MB`; algväärtus on 128 MB ja seda saab vajaduse korral tõsta,
  näiteks 256 MB-ni.
- Kõik cache'i, heartbeat'i ja lease'i algväärtused tulevad `.env` failist ning
  on dokumenteeritud `.env.example` failis.

