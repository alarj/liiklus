-- Käivita LIIKLUS skeemikasutajana olemasoleva 001_core_schema.sql skeemi peal.
-- Skript muudab andmestruktuuri ja olemasolevaid ridu. Ära käivita seda ilma
-- kasutaja eraldi loata ning tee enne andmebaasi varukoopia või taastepunkt.

CREATE SEQUENCE camera_profiles_seq START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE camera_profiles (
    camera_profile_id NUMBER(19) DEFAULT camera_profiles_seq.NEXTVAL NOT NULL,
    profile_code VARCHAR2(100 CHAR) NOT NULL,
    profile_version NUMBER(10) DEFAULT 1 NOT NULL,
    profile_name VARCHAR2(250 CHAR) NOT NULL,
    sort_order NUMBER(10) DEFAULT 0 NOT NULL,
    is_default NUMBER(1) DEFAULT 0 NOT NULL,
    source_image_url VARCHAR2(2000 CHAR),
    capture_interval_seconds NUMBER(10),
    model_files_json JSON NOT NULL,
    vehicle_classes_json JSON NOT NULL,
    roi_mask_json JSON,
    default_confidence NUMBER(4,3) DEFAULT 0.45 NOT NULL,
    start_date DATE DEFAULT SYSDATE NOT NULL,
    end_date DATE,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    last_updated TIMESTAMP,
    CONSTRAINT camera_profiles_pk PRIMARY KEY (camera_profile_id),
    CONSTRAINT camera_profiles_code_version_uq
        UNIQUE (profile_code, profile_version),
    CONSTRAINT camera_profiles_version_ck CHECK (profile_version > 0),
    CONSTRAINT camera_profiles_default_ck CHECK (is_default IN (0, 1)),
    CONSTRAINT camera_profiles_capture_interval_ck CHECK (
        capture_interval_seconds IS NULL
        OR (source_image_url IS NOT NULL AND capture_interval_seconds >= 0)
    ),
    CONSTRAINT camera_profiles_confidence_ck
        CHECK (default_confidence BETWEEN 0.01 AND 1.0)
);

CREATE UNIQUE INDEX camera_profiles_active_code_uq
    ON camera_profiles (
        CASE WHEN end_date IS NULL THEN profile_code END
    );

CREATE UNIQUE INDEX camera_profiles_active_default_uq
    ON camera_profiles (
        CASE WHEN end_date IS NULL AND is_default = 1 THEN 1 END
    );

INSERT INTO camera_profiles (
    profile_code, profile_version, profile_name, sort_order, is_default,
    source_image_url, model_files_json, vehicle_classes_json, roi_mask_json,
    default_confidence
) VALUES (
    'parnu-mnt-karja', 1, 'Pärnu mnt - Karja', 10, 1,
    NULL,
    JSON('["best v3.onnx","best v2.onnx","best.onnx"]'),
    JSON('[{"model_index":0,"code":"bus","name":"Buss"},{"model_index":1,"code":"car","name":"Auto"},{"model_index":2,"code":"tram","name":"Tramm"}]'),
    NULL,
    0.45
);


INSERT INTO camera_profiles (
    profile_code, profile_version, profile_name, sort_order, is_default,
    source_image_url, model_files_json, vehicle_classes_json, roi_mask_json,
    default_confidence
) VALUES (
    'cam217', 1, 'Laagna tee / Mustakivi', 20, 0,
    NULL,
    JSON('["cam217 v2.onnx"]'),
    JSON('[{"model_index":0,"code":"bus","name":"Buss"},{"model_index":1,"code":"car","name":"Auto"},{"model_index":2,"code":"van-truck","name":"Kaubik/veok"}]'),
    JSON('{"type":"polygon","fill_rgb":[114,114,114],"normalized_points":[[0.032,0.105],[0.098,0.068],[0.558,0.258],[0.922,0.562],[0.875,0.992],[0.232,0.985]]}'),
    0.45
);
ALTER TABLE training_images ADD (camera_profile_id NUMBER(19));

UPDATE training_images
   SET camera_profile_id = (
       SELECT camera_profile_id
         FROM camera_profiles
        WHERE profile_code = 'parnu-mnt-karja'
          AND end_date IS NULL
   );

ALTER TABLE training_images MODIFY (camera_profile_id NOT NULL);

ALTER TABLE training_images ADD CONSTRAINT training_images_profile_fk
    FOREIGN KEY (camera_profile_id)
    REFERENCES camera_profiles (camera_profile_id);

CREATE INDEX training_images_profile_ix
    ON training_images (camera_profile_id, created);

DROP INDEX training_images_active_sha_uq;

CREATE UNIQUE INDEX training_images_active_sha_uq
    ON training_images (
        CASE WHEN end_date IS NULL THEN camera_profile_id END,
        CASE WHEN end_date IS NULL THEN source_sha256 END
    );

ALTER TABLE training_packages ADD (camera_profile_id NUMBER(19));

UPDATE training_packages
   SET camera_profile_id = (
       SELECT camera_profile_id
         FROM camera_profiles
        WHERE profile_code = 'parnu-mnt-karja'
          AND end_date IS NULL
   );

ALTER TABLE training_packages MODIFY (camera_profile_id NOT NULL);

ALTER TABLE training_packages ADD CONSTRAINT training_packages_profile_fk
    FOREIGN KEY (camera_profile_id)
    REFERENCES camera_profiles (camera_profile_id);

CREATE INDEX training_packages_profile_ix
    ON training_packages (camera_profile_id, created);

COMMIT;
