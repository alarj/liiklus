# Projekti tööreeglid

## 1. Dokumendi päritolu

Koostaja: AI (OpenAI Codex), kasutaja juhiste järgi. Käesoleva dokumendi esimene versioon põhines projekti `err_video_to_text` tööjuhendil; seda on käesoleva `liiklus` projekti jaoks kohandatud ja täiendatud.

## 2. Sisukord

- [3. Charset ja failivorming](#3-charset-ja-failivorming)
- [4. Peamine tööreegel: enne vastamist tutvu olemasoleva olukorraga](#4-peamine-tööreegel-enne-vastamist-tutvu-olemasoleva-olukorraga)
- [5. Tööpõhimõtted](#5-tööpõhimõtted)
- [6. Projekti dokumentide koostamine](#6-projekti-dokumentide-koostamine)
- [7. Vea käsitlemise juhis](#7-vea-käsitlemise-juhis)
- [8. Mittefunktsionaalsed ootused](#8-mittefunktsionaalsed-ootused)
- [9. Dokumentatsiooni ja tõeallikate register](#9-dokumentatsiooni-ja-tõeallikate-register)
- [10. Millal mida kindlasti lugeda](#10-millal-mida-kindlasti-lugeda)
- [11. Väljundi ootused](#11-väljundi-ootused)

## 3. Charset ja failivorming

- Kõik kood, konfiguratsioon ja dokumentatsioon peavad olema UTF-8 kodeeringus.
- Uute failide loomisel ja olemasolevate failide muutmisel tuleb säilitada UTF-8.
- Kui failis esineb kodeeringuprobleem, tuleb see käsitleda veana ja parandada juurpõhjus, mitte peita sümptomit.

## 4. Peamine tööreegel: enne vastamist tutvu olemasoleva olukorraga

- Enne igat sisulist vastust, hinnangut, kavandamist või muudatust tuleb tutvuda ülesandega seotud olemasoleva dokumentatsiooni, koodi ja andmetega.
- Seda nõuet tuleb järgida ka siis, kui kasutaja küsib ainult selgitust või plaani: vastus peab põhinema projekti tegelikul olukorral, mitte üldisel oletusel.
- Enne muudatuste kavandamist tuleb läbi lugeda kõik dokumendid ja koodiosad, mis puudutavad muudetavat ala. Vajaduse korral tuleb kontrollida ka olemasolevaid tööartefakte, logisid, konfiguratsiooni ja näidisandmeid.
- Olemasolev dokumentatsioon, kood, konfiguratsioon, logid ja andmed ei ole iseenesest õiged ega valed. Iga allikas kirjeldab seda, mis projektis on kirjas, teostatud või vaadeldav; selle olemasolu ei tõenda veel väite õigsust ega allika ülimuslikkust.
- Dokumentatsiooni olemasolu ei vabasta koodi ja tegelike andmete kontrollimisest. Samuti ei tohi toimivat koodi või olemasolevaid andmeid automaatselt pidada dokumentatsioonist õigemaks.
- Kui dokumentide eneste, dokumentatsiooni ja koodi, dokumentatsiooni ja andmete, koodi ja andmete või muude allikate vahel esineb vastuolu, ei tohi iseseisvalt otsustada, milline allikas on õigem või ajakohasem.
- Vastuolu avastamisel tuleb sisuline töö selles küsimuses peatada, kirjeldada kasutajale täpselt vastuolus olevad väited või vaatlused ning küsida enne jätkamist kasutaja otsust. Ka näiliselt ilmset vastuolu ei tohi vaikimisi lahendada.
- Kui vajalik allikas puudub või töö käigus tekib kahtlus, ei tohi lünka oletusega peita. Kontrolli olemasolevat materjali ning kui kontroll ei anna üheselt kooskõlalist tulemust, peatu ja küsi üle.

## 5. Tööpõhimõtted

- Ülesannet ei tohi iseseisvalt laiendada ega kitsendada. Kui ülesande laiendamine või kitsendamine tundub vajalik, tuleb enne muudatuse tegemist kasutajalt küsida.
- Kasutusele ei tohi võtta enda välja mõeldud mõisteid ega termineid, mille sisu ei ole inimesele arusaadavalt lahti seletatud.
- Kasutada ei tohi mõõtühikuid, mida ei ole kasutajaga kokku lepitud ja mille olemus ei ole inimesele üheselt arusaadav.
- Ärireeglid peavad elama võimalikult tsentraalselt ja järjekindlalt; väldi reeglite dubleerimist eri kihtides.
- Muudatused peavad olema minimaalsed, sihitud ja kooskõlas olemasoleva arhitektuuriga.
- Töötavat koodi ei tohi igaks juhuks muuta ega ennetavalt parandada. Kui mingi osa töötab ja ei ole uuritava vea tõendatud juurpõhjus, siis seda ei muudeta.
- Ära muuda kõrvalisi faile ega paranda mitteseotud probleeme.
- Kõrge mõjuga otsuste puhul eelista juurpõhjuse parandamist, mitte lokaalseid ümberkäike.


### Dokumentatsiooni ajakohastamine

- Pärast iga muudatust tuleb alati uuendada ka muudatuse piirkonda kirjeldavat dokumentatsiooni.
- Eraldi tuleb kontrollida kõiki projekti dokumente, mida muudatus võib mõjutada, ning veenduda, et muudatuse otsene ja kaudne mõju on neis arvesse võetud.
- Muudatust ei loeta lõpetatuks enne, kui see dokumentatsiooni mõjukontroll on tehtud ja vajalikud dokumendimuudatused on rakendatud.

### Git ja juurutus

- `git commit` vajab kasutaja iga töökorra jaoks eraldi luba.
- `git push` vajab kasutaja iga töökorra jaoks eraldi luba.
- Kuna rakendus töötab samas serveris, piisab testimiseks koodi muutmisest ning
  vajaliku konteineri ehitamisest ja taaskäivitamisest; commit'i ega push'i ei
  tohi eeldada juurutuse eeltingimusena.

### Testimine ja andmete muutmine

- Teste käivitatakse ainult siis, kui kasutaja või ülesande väline
  vastuvõtukriteerium seda sõnaselgelt nõuab. Teste ei käivitata automaatselt
  ega tavapärase muudatuse osana.
- Nõutud testid tuleb eelnevalt kirjeldada failis `docs/testid.md` ja piirata
  konkreetse muudatuse kontrollimiseks vajaliku ulatusega.
- Ilma kasutaja eraldi loata ei tohi käivitada teste ega kontrollskripte, mis
  kirjutavad andmebaasi või muudavad olemasolevaid andmeid.
- Ilma sellise loata on lubatud ainult dry-run'id, lugemispäringud ja muud
  mitte-muteerivad kontrollid.
- Mistahes andmeid või andmestruktuuri muutvat tegevust ei tohi teha ilma
  kasutaja eelneva eraldi loata — mitte kunagi. See hõlmab nii andmeridade
  lisamist, muutmist ja kustutamist kui ka tabeli, veeru, indeksi, piirangu või
  sequence'i lisamist, muutmist või kustutamist ning migratsiooni rakendamist.
- Kui kontroll eeldab andmete muutmist, tuleb enne peatuda ja küsida kasutajalt
  eraldi luba.

## 6. Projekti dokumentide koostamine

- Projekti dokumentide vaikevorming on Markdown (`.md`), kui kasutaja ei ole sõnaselgelt nõudnud teistsugust vormingut.
- Dokumendi esimene jaotis peab alati olema „Dokumendi päritolu“. Selles tuleb märkida, kas dokumendi koostas inimene või AI; vajaduse korral kirjeldatakse lühidalt ka alusmaterjale ja inimese panust.
- Dokumendi teine jaotis on üldjuhul „Sisukord“.
- Sisukorra võib ära jätta ainult siis, kui dokument sisaldab alla kolme sisulise punkti ja on lühem kui neli lehekülge. Muudel juhtudel on sisukord kohustuslik.
- Dokumendi päritolu jaotist sisukorda ei lisata.

## 7. Vea käsitlemise juhis

- Vea või regressiooni korral uuri esmalt juurpõhjust.
- Uuri kogu ahelat, mitte ainult vea esinemise kohta.
- Ära piirdu ainult sümptomit eemaldava parandusega, kui juurpõhjus jääb alles.
- Tee veast, selle põhjustest ja võimalikest parandusvariantidest kokkuvõte ning küsi nõusolek parandamiseks.
- Vastuses või töö kokkuvõttes kirjelda võimalusel lühidalt:
  1. mis oli juurpõhjus;
  2. miks viga tekkis;
  3. kuidas tehtud parandus selle kõrvaldab;
  4. milline jääkrisk või eeldus alles jääb.
- Kui loogiline koht on olemas, lisa või uuenda test, mis kinnitab parandust.

## 8. Mittefunktsionaalsed ootused

- Hoia API, andmemudeli, tööartefaktide ja ärireeglite käitumine eri klientide jaoks järjekindel.
- Väldi lahendusi, mis suurendavad põhjendamatult CPU-, mälu-, ketta-, võrgu- või andmebaasikoormust.
- API teenused peavad tagastama konkreetse kasutusjuhtumi jaoks vajaliku minimaalse andmehulga.
- Kui lisatakse püsiv andmebaas, on autoriteetne aeg UTC ning kasutajaliides kuvab aja kasutaja lokaalses ajavööndis.
- Kõik rakenduse skeemi tabelid kasutavad `start_date`, `end_date`, `created` ja `last_updated` veerge. Füüsilist kustutamist ei kasutata ning suletud kirjed ei tohi tavavoogudes nähtavale jääda.
- Kasutajaliidese tekstid peavad olema tõlgetest, mitte kõvakodeeritud.
- Eelista korduvate väärtuste puhul eeldefineeritud konstante ja ühist äriloogikat.
- Saladused, ligipääsutokenid ja autentimisküpsised peavad tulema `.env`-ist või muust saladuste hoidlast ning neid ei tohi kirjutada Git-i, logidesse ega väljunditesse.
- Mahukaid audio-, video-, mudeli- ega ajutisi tööfaile ei salvestata Git-repositooriumi ega andmebaasi. Andmebaasis hoitakse vajaduse korral ainult viiteid, kontrollsummasid ja metaandmeid.
- Kõik olulised mudeli-, tööriista- ja skeemiversioonid peavad olema väljundis auditeeritavad.

## 9. Dokumentatsiooni ja tõeallikate register

### Projekti põhidokumendid

- [`README.md`](../README.md) — rakenduse hetkeseis, käivitamine, väljundid ja piirangud.
- [`docs/agents.md`](agents.md) — projekti siduvad tööreeglid.
- [`docs/lähteülesanne.md`](lähteülesanne.md) — rakenduse eesmärk, ulatus ja vastuvõtukriteeriumid.
- [`docs/testid.md`](testid.md) — enne käivitamist kooskõlastatav minimaalne testiplaan.

### Lähte- ja võrdlusmaterjalid

- `/home/ubuntu/fun_o/nginx/default.conf` ja `/home/ubuntu/fun_o/docker-compose.yml` ühise nginx-veebiserveri või `funo_net` võrguga integratsiooni kavandamisel ja muutmisel.

### Teostuse põhilised allikad

Registrit tuleb täiendada kohe, kui projektile lisandub README, andmeskeem, API leping, konteinerite kirjeldus, hindamisandmete register või muu asjakohane allikas. Registrisse kuulumine ei anna allikale teiste ees ülimuslikkust.
- [`app.py`](../app.py) — API ja liiklustuvastuse rakendusloogika.
- [`docker-compose.yml`](../docker-compose.yml) — konteineri käitus, mudeli mount ja võrk.
- [`Dockerfile`](../Dockerfile) — rakenduse Docker image'i ehitus.
- [`.env.example`](../.env.example) — käituskeskkonna seadistuse näidis.
- [`db/erd.md`](../db/erd.md) — Oracle'i aktiivõppe andmemudel, tabelid, seosed ja terviklusreeglid.
- [`db/schema/001_core_schema.sql`](../db/schema/001_core_schema.sql) — Oracle'i skeemi loomise skript.
- [`tests/test_app.py`](../tests/test_app.py) — automatiseeritud API ja eeltöötluse testid.
- [`tests/test_ui_contract.py`](../tests/test_ui_contract.py) — UI staatilise lepingu testid.
- [`requirements-test.txt`](../requirements-test.txt) — testide fikseeritud sõltuvused.

## 10. Millal mida kindlasti lugeda

- Enne igat sisulist vastust loe vähemalt käesolev juhend ja ülesandega seotud põhidokumendi osad; koodi olemasolul kontrolli vastavat teostust.


## 11. Väljundi ootused

- Kui töö sisaldab vea parandust, too kokkuvõttes eraldi välja juurpõhjus ja paranduse loogika.
- Kui töö tugineb oletusele, nimeta oletus selgelt ning küsi enne muudatuse tegemist luba.
- Kui avastad allikate vahel lahknevuse, peata seda küsimust puudutav sisuline töö kohe, too vastuolu välja ja küsi enne jätkamist täiendavaid juhtnööre. Vastuolu ei tohi jätta ainult töö lõpu kokkuvõttesse.
