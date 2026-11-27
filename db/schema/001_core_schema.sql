-- Käivita LIIKLUS skeemikasutajana ühe skriptina tühjas skeemis.

CREATE SEQUENCE app_users_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE camera_profiles_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE training_images_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE training_packages_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE training_package_images_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE training_package_downloads_seq START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE app_users (
    user_id NUMBER(19) DEFAULT app_users_seq.NEXTVAL NOT NULL,
    public_id VARCHAR2(36 CHAR) NOT NULL,
    identity_provider VARCHAR2(100 CHAR),
    external_subject VARCHAR2(255 CHAR),
    email VARCHAR2(320 CHAR),
    display_name VARCHAR2(250 CHAR),
    role_code VARCHAR2(30 CHAR) DEFAULT 'USER' NOT NULL,
    enabled NUMBER(1) DEFAULT 1 NOT NULL,
    start_date DATE DEFAULT SYSDATE NOT NULL,
    end_date DATE,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    last_updated TIMESTAMP,
    CONSTRAINT app_users_pk PRIMARY KEY (user_id),
    CONSTRAINT app_users_public_id_uq UNIQUE (public_id),
    CONSTRAINT app_users_identity_uq UNIQUE (identity_provider, external_subject),
    CONSTRAINT app_users_email_uq UNIQUE (email),
    CONSTRAINT app_users_role_ck CHECK (role_code IN ('USER', 'ADMIN')),
    CONSTRAINT app_users_enabled_ck CHECK (enabled IN (0, 1))
);

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
CREATE TABLE training_images (
    training_image_id NUMBER(19) DEFAULT training_images_seq.NEXTVAL NOT NULL,
    public_id VARCHAR2(36 CHAR) NOT NULL,
    candidate_by_user_id NUMBER(19) NOT NULL,
    camera_profile_id NUMBER(19) NOT NULL,
    original_filename VARCHAR2(500 CHAR) NOT NULL,
    image_relative_path VARCHAR2(1000 CHAR) NOT NULL,
    label_relative_path VARCHAR2(1000 CHAR) NOT NULL,
    source_media_type VARCHAR2(255 CHAR) NOT NULL,
    stored_media_type VARCHAR2(255 CHAR) NOT NULL,
    source_size_bytes NUMBER(19) NOT NULL,
    stored_size_bytes NUMBER(19) NOT NULL,
    source_width NUMBER(10) NOT NULL,
    source_height NUMBER(10) NOT NULL,
    stored_width NUMBER(10) NOT NULL,
    stored_height NUMBER(10) NOT NULL,
    source_sha256 CHAR(64 CHAR) NOT NULL,
    stored_sha256 CHAR(64 CHAR) NOT NULL,
    reason VARCHAR2(2000 CHAR),
    tags_json JSON,
    analysis_json JSON NOT NULL,
    model_sha256 CHAR(64 CHAR) NOT NULL,
    label_confidence NUMBER(4,3) NOT NULL,
    start_date DATE DEFAULT SYSDATE NOT NULL,
    end_date DATE,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    last_updated TIMESTAMP,
    CONSTRAINT training_images_pk PRIMARY KEY (training_image_id),
    CONSTRAINT training_images_public_id_uq UNIQUE (public_id),
    CONSTRAINT training_images_image_path_uq UNIQUE (image_relative_path),
    CONSTRAINT training_images_label_path_uq UNIQUE (label_relative_path),
    CONSTRAINT training_images_user_fk FOREIGN KEY (candidate_by_user_id)
        REFERENCES app_users (user_id),
    CONSTRAINT training_images_profile_fk FOREIGN KEY (camera_profile_id)
        REFERENCES camera_profiles (camera_profile_id)
);

CREATE UNIQUE INDEX training_images_active_sha_uq
    ON training_images (
        CASE WHEN end_date IS NULL THEN camera_profile_id END,
        CASE WHEN end_date IS NULL THEN source_sha256 END
    );

CREATE INDEX training_images_profile_ix
    ON training_images (camera_profile_id, created);

CREATE TABLE training_packages (
    training_package_id NUMBER(19) DEFAULT training_packages_seq.NEXTVAL NOT NULL,
    public_id VARCHAR2(36 CHAR) NOT NULL,
    package_name VARCHAR2(250 CHAR) NOT NULL,
    created_by_user_id NUMBER(19) NOT NULL,
    camera_profile_id NUMBER(19) NOT NULL,
    first_downloaded_at TIMESTAMP,
    first_downloaded_by_user_id NUMBER(19),
    start_date DATE DEFAULT SYSDATE NOT NULL,
    end_date DATE,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    last_updated TIMESTAMP,
    CONSTRAINT training_packages_pk PRIMARY KEY (training_package_id),
    CONSTRAINT training_packages_public_id_uq UNIQUE (public_id),
    CONSTRAINT training_packages_creator_fk FOREIGN KEY (created_by_user_id)
        REFERENCES app_users (user_id),
    CONSTRAINT training_packages_profile_fk FOREIGN KEY (camera_profile_id)
        REFERENCES camera_profiles (camera_profile_id),
    CONSTRAINT training_packages_first_dl_fk FOREIGN KEY (first_downloaded_by_user_id)
        REFERENCES app_users (user_id),
    CONSTRAINT training_packages_dl_pair_ck CHECK (
        (first_downloaded_at IS NULL AND first_downloaded_by_user_id IS NULL)
        OR
        (first_downloaded_at IS NOT NULL AND first_downloaded_by_user_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX training_packages_name_uq
    ON training_packages (LOWER(package_name));

CREATE INDEX training_packages_profile_ix
    ON training_packages (camera_profile_id, created);

CREATE TABLE training_package_images (
    training_package_image_id NUMBER(19)
        DEFAULT training_package_images_seq.NEXTVAL NOT NULL,
    public_id VARCHAR2(36 CHAR) NOT NULL,
    training_package_id NUMBER(19) NOT NULL,
    training_image_id NUMBER(19) NOT NULL,
    added_by_user_id NUMBER(19) NOT NULL,
    start_date DATE DEFAULT SYSDATE NOT NULL,
    end_date DATE,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    last_updated TIMESTAMP,
    CONSTRAINT training_package_images_pk PRIMARY KEY (training_package_image_id),
    CONSTRAINT training_pkg_images_public_uq UNIQUE (public_id),
    CONSTRAINT training_pkg_images_package_fk FOREIGN KEY (training_package_id)
        REFERENCES training_packages (training_package_id),
    CONSTRAINT training_pkg_images_image_fk FOREIGN KEY (training_image_id)
        REFERENCES training_images (training_image_id),
    CONSTRAINT training_pkg_images_user_fk FOREIGN KEY (added_by_user_id)
        REFERENCES app_users (user_id)
);

CREATE UNIQUE INDEX training_pkg_images_active_uq
    ON training_package_images (
        CASE WHEN end_date IS NULL THEN training_package_id END,
        CASE WHEN end_date IS NULL THEN training_image_id END
    );

CREATE TABLE training_package_downloads (
    training_package_download_id NUMBER(19)
        DEFAULT training_package_downloads_seq.NEXTVAL NOT NULL,
    public_id VARCHAR2(36 CHAR) NOT NULL,
    training_package_id NUMBER(19) NOT NULL,
    downloaded_by_user_id NUMBER(19) NOT NULL,
    image_count NUMBER(10) NOT NULL,
    start_date DATE DEFAULT SYSDATE NOT NULL,
    end_date DATE,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    last_updated TIMESTAMP,
    CONSTRAINT training_package_downloads_pk PRIMARY KEY (training_package_download_id),
    CONSTRAINT training_pkg_downloads_public_uq UNIQUE (public_id),
    CONSTRAINT training_pkg_downloads_pkg_fk FOREIGN KEY (training_package_id)
        REFERENCES training_packages (training_package_id),
    CONSTRAINT training_pkg_downloads_user_fk FOREIGN KEY (downloaded_by_user_id)
        REFERENCES app_users (user_id)
);

CREATE INDEX training_pkg_images_image_ix
    ON training_package_images (training_image_id);

CREATE INDEX training_pkg_downloads_pkg_ix
    ON training_package_downloads (training_package_id, created);

