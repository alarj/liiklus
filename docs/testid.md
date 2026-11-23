# Tallinna liikluse tuvastuse API minimaalne testiplaan

## 1. Dokumendi päritolu

Dokumendi koostas OpenAI Codex 23. novembril 2026 kasutaja nõudel. Testiplaan
on teadlikult minimaalne ja vajab enne käivitamist kasutaja heakskiitu.

## 2. Sisukord

- [3. Käivitamise tingimus](#3-käivitamise-tingimus)
- [4. Testide teostuse seis](#4-testide-teostuse-seis)
- [5. Kavandatud kontrollid](#5-kavandatud-kontrollid)
- [6. Käivitamise sagedus](#6-käivitamise-sagedus)
- [7. Tulemuste talletamine](#7-tulemuste-talletamine)

## 3. Käivitamise tingimus

Ühtegi allpool kirjeldatud käsku, testi ega testpäringut ei käivitata enne,
kui kasutaja on selle dokumendi üle vaadanud ja andnud eraldi selgesõnalise
loa. Testid ei tohi muuta andmebaasi ega muid püsivaid andmeid.

## 4. Testide teostuse seis

Automatiseeritud testikood asub failis `tests/test_app.py`. Testid ehitatakse
eraldi Docker image'i sihtmärki ja neid saab käivitada ainult Compose'i
`testing` profiiliga. Tootmis-API ehitamine või käivitamine teste automaatselt
ei käivita. Ühtegi testi pole veel käivitatud.

## 5. Kavandatud kontrollid

1. **Konteiner ja health.** Ehitada ning käivitada `liiklus-api`; kontrollida,
   et `GET /api/health` vastab HTTP 200 ja `{"status":"ok"}`.
2. **Eeltöötlus ja sisendi piirid.** Kontrollida, et mudeli sisendmõõtu mahtuv
   pilt säilitab algse mõõdu ning saab täite ainult paremale ja alla. Kontrollida,
   et suurem pilt skaleeritakse kuvasuhet hoides mõõtu `1152 × 576` mahtuvaks.
   Kontrollida ühe näitega ka seda, et vale failivorming, üle 5 MiB fail ja üle
   10 000 000 piksliga pilt lükatakse tagasi.
3. **Pärispildi JSON.** Saata kasutaja antud JPEG- või PNG-pilt otspunktile
   `POST /api/detect`; kontrollida vastuse välju, klassinimesid, koordinaate ja
   `X-Model-SHA256` päist.
4. **Pärispildi visualiseering.** Saata sama pilt otspunktile
   `POST /api/detect/image`; kontrollida, et vastus on avatav JPEG ning kastid
   vastavad JSON-vastusele.

Automatiseeritud testid katavad punktid 1 ja 2 ning punktide 3 ja 4 API lepingu
sünteetilise pildiga. Pärispildi sisuline tulemus kontrollitakse eraldi pärast
kasutajalt testpildi saamist.

## 6. Käivitamise sagedus

Teste ei käivitata automaatselt pärast iga muudatust. Iga muudatuse järel
valitakse ainult selle muudatusega seotud kontrollid. Kogu testiplaan on
mõeldud esimese tervikliku juurutuse kontrolliks või olukorraks, kus muutub
inferents, pildi eeltöötlus, API leping või konteineri käitus. Iga testide
käivitamine vajab kasutaja eraldi luba.

## 7. Tulemuste talletamine

Pärast loa saamist märgitakse iga kontrolli juurde kuupäev, kasutatud sisend,
tulemus ja võimalik kõrvalekalle. Pärispilte Git-i ega andmebaasi ei lisata.
