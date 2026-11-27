# Kasutajarollid ja ligipääsuõigused

## 1. Dokumendi päritolu

Koostaja: AI (OpenAI Codex), kasutaja 27. novembri 2026 kinnitatud
rollijaotuse alusel.

## 2. Sisukord

- [3. Rollid](#3-rollid)
- [4. Backendi kontroll](#4-backendi-kontroll)
- [5. Kasutajaliides](#5-kasutajaliides)
- [6. Tulevane profiilide uuesti laadimine](#6-tulevane-profiilide-uuesti-laadimine)

## 3. Rollid

Rakendus kasutab täpselt kahte rollikoodi: `USER` ja `ADMIN`.

| Tegevus | `USER` | `ADMIN` |
|---|---:|---:|
| Pildianalüüs | jah | jah |
| Kaamerate live-vaade | jah | jah |
| Pildi lisamine treeningukandidaadiks | ei | jah |
| Treeningukandidaatide vaatamine ja haldamine | ei | jah |
| Treeningupakkide loomine, muutmine ja allalaadimine | ei | jah |
| Tulevane profiilide uuesti laadimine | ei | jah |

## 4. Backendi kontroll

Sessioonis hoitakse ainult kasutaja ID-d. Backend loeb aktiivse kasutaja ja
tema `role_code` väärtuse Oracle'ist igal autenditud API-päringul. Kõik
`/api/training-pool...` ja `/api/training-packages...` otspunktid nõuavad
`ADMIN` rolli; `USER` saab HTTP 403 vastuse.

Rolli muutmine `ADMIN`-ist `USER`-iks rakendub seetõttu backendis kohe
järgmisele päringule. `USER`-ist `ADMIN`-iks muutmisel saab backend õiguse kohe,
kuid admini menüüde kuvamiseks peab UI uuesti `/api/auth/me` laadima.

## 5. Kasutajaliides

`USER` suunatakse pärast sisselogimist kohe kaamerate live-vaatesse. Talle
kuvatakse ainult pildianalüüsi ja live-vaate vahekaardid. Treeningpiltide
vahekaart ning pildianalüüsi ja live-vaate treeningusse saatmise nupud on
peidetud.

`ADMIN` avab vaikimisi pildianalüüsi vaate ja näeb kõiki olemasolevaid
funktsioone. UI piirang on kasutusmugavuse jaoks; tegelik õiguskontroll toimub
alati backendis.

## 6. Tulevane profiilide uuesti laadimine

Tulevane „Laadi profiilid uuesti“ tegevus kuulub ainult `ADMIN` rollile ja peab
kasutama sama keskset backendi rollikontrolli.
