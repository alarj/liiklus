-- Käivita LIIKLUS skeemikasutajana ühe skriptina tühjas skeemis.

CREATE SEQUENCE app_users_seq START WITH 1 INCREMENT BY 1 NOCACHE;
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

CREATE TABLE training_images (
    training_image_id NUMBER(19) DEFAULT training_images_seq.NEXTVAL NOT NULL,
    public_id VARCHAR2(36 CHAR) NOT NULL,
    candidate_by_user_id NUMBER(19) NOT NULL,
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
        REFERENCES app_users (user_id)
);

CREATE UNIQUE INDEX training_images_active_sha_uq
    ON training_images (
        CASE WHEN end_date IS NULL THEN source_sha256 END
    );

CREATE TABLE training_packages (
    training_package_id NUMBER(19) DEFAULT training_packages_seq.NEXTVAL NOT NULL,
    public_id VARCHAR2(36 CHAR) NOT NULL,
    package_name VARCHAR2(250 CHAR) NOT NULL,
    created_by_user_id NUMBER(19) NOT NULL,
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

