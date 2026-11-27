# Tallinna liiklustuvastuse aktiivõppe ERD

## 1. Dokumendi päritolu

Dokumendi koostas OpenAI Codex 24. novembril 2026 kasutaja kinnitatud
aktiivõppe, kasutajate, treeningpiltide ja treeningpakkide nõuete põhjal ning
täiendas 27. novembril 2026 kaameraprofiilide seostega.

## 2. Mermaid ER-diagramm

```mermaid
erDiagram
    APP_USERS ||--o{ TRAINING_IMAGES : selects_candidate
    APP_USERS ||--o{ TRAINING_PACKAGES : creates
    APP_USERS o|--o{ TRAINING_PACKAGES : first_downloads
    APP_USERS ||--o{ TRAINING_PACKAGE_IMAGES : adds_to_package
    APP_USERS ||--o{ TRAINING_PACKAGE_DOWNLOADS : downloads

    CAMERA_PROFILES ||--o{ TRAINING_IMAGES : classifies
    CAMERA_PROFILES ||--o{ TRAINING_PACKAGES : scopes

    TRAINING_IMAGES ||--o{ TRAINING_PACKAGE_IMAGES : belongs_to
    TRAINING_PACKAGES ||--o{ TRAINING_PACKAGE_IMAGES : contains
    TRAINING_PACKAGES ||--o{ TRAINING_PACKAGE_DOWNLOADS : has_downloads

    APP_USERS {
        NUMBER user_id PK
        VARCHAR2 public_id UK
        VARCHAR2 identity_provider
        VARCHAR2 external_subject
        VARCHAR2 email UK
        VARCHAR2 display_name
        VARCHAR2 role_code
        NUMBER enabled
        DATE start_date
        DATE end_date
        TIMESTAMP created
        TIMESTAMP last_updated
    }

    CAMERA_PROFILES {
        NUMBER camera_profile_id PK
        VARCHAR2 profile_code
        NUMBER profile_version
        VARCHAR2 profile_name
        NUMBER sort_order
        NUMBER is_default
        VARCHAR2 source_image_url
        JSON model_files_json
        JSON vehicle_classes_json
        JSON roi_mask_json
        NUMBER default_confidence
        DATE start_date
        DATE end_date
        TIMESTAMP created
        TIMESTAMP last_updated
    }

    TRAINING_IMAGES {
        NUMBER training_image_id PK
        VARCHAR2 public_id UK
        NUMBER candidate_by_user_id FK
        NUMBER camera_profile_id FK
        VARCHAR2 original_filename
        VARCHAR2 image_relative_path UK
        VARCHAR2 label_relative_path UK
        VARCHAR2 source_media_type
        VARCHAR2 stored_media_type
        NUMBER source_size_bytes
        NUMBER stored_size_bytes
        NUMBER source_width
        NUMBER source_height
        NUMBER stored_width
        NUMBER stored_height
        CHAR source_sha256
        CHAR stored_sha256
        VARCHAR2 reason
        JSON tags_json
        JSON analysis_json
        CHAR model_sha256
        NUMBER label_confidence
        DATE start_date
        DATE end_date
        TIMESTAMP created
        TIMESTAMP last_updated
    }

    TRAINING_PACKAGES {
        NUMBER training_package_id PK
        VARCHAR2 public_id UK
        VARCHAR2 package_name UK
        NUMBER created_by_user_id FK
        NUMBER camera_profile_id FK
        TIMESTAMP first_downloaded_at
        NUMBER first_downloaded_by_user_id FK
        DATE start_date
        DATE end_date
        TIMESTAMP created
        TIMESTAMP last_updated
    }

    TRAINING_PACKAGE_IMAGES {
        NUMBER training_package_image_id PK
        VARCHAR2 public_id UK
        NUMBER training_package_id FK
        NUMBER training_image_id FK
        NUMBER added_by_user_id FK
        DATE start_date
        DATE end_date
        TIMESTAMP created
        TIMESTAMP last_updated
    }

    TRAINING_PACKAGE_DOWNLOADS {
        NUMBER training_package_download_id PK
        VARCHAR2 public_id UK
        NUMBER training_package_id FK
        NUMBER downloaded_by_user_id FK
        NUMBER image_count
        DATE start_date
        DATE end_date
        TIMESTAMP created
        TIMESTAMP last_updated
    }
```

## 3. Olulised reeglid

- `TRAINING_PACKAGES.package_name` on unikaalne.
- Aktiivse `CAMERA_PROFILES.profile_code` kohta saab olla üks versioon ja
  aktiivseid vaikeprofiile saab olla maksimaalselt üks. Rakendus nõuab
  käivitamisel täpselt ühte aktiivset vaikeprofiili.
- Kaameraprofiili `model_files_json` on järjestatud loend, mille esimene
  element on profiili vaikemudel. Mudelifailid ise asuvad serveri
  `MODEL_DIR` kataloogis.
- Iga treeningpilt ja treeningpakk kuulub ühele konkreetsele
  kaameraprofiilile. Pakki võib lisada ainult sama profiili pilte.
- Sama pilt võib kuuluda mitmesse paketti; sama pildi ja paketi aktiivne seos
  võib esineda ainult üks kord.
- Paketi koosseisu võib muuta kuni esimese allalaadimiseni. Esimene
  allalaadimine väärtustab `first_downloaded_at` ja lukustab koosseisu.
- `TRAINING_IMAGES.created` näitab kandidaadiks märkimise aega ning
  `TRAINING_PACKAGE_IMAGES.created` konkreetsesse paketti lisamise aega.
- Viimane allalaadija ja aeg leitakse `TRAINING_PACKAGE_DOWNLOADS` kõige
  uuemast kirjest.
- Pilt ja YOLO `.txt` asuvad kettal. Pildi kustutamisel failid eemaldatakse,
  kuid Oracle'i metaandmed ja pakiseosed säilivad soft delete'iga.
- `TRAINING_IMAGES.analysis_json` sisaldab eelmärgenduseks kasutatud mudeli
  failinime ja kontrollsummat; `model_sha256` veerg säilitab kontrollsumma ka
  eraldi auditeeritava väärtusena.
- Kõigi `DATE` ja `TIMESTAMP` väärtuste autoriteetne ajavöönd on UTC. API
  lisab Oracle'ist loetud ajatemplitele UTC-ajavööndi enne JSON-väljundit ning
  UI kuvab need brauseri kohalikus ajavööndis.

