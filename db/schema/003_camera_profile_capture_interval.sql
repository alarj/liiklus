-- Käivita LIIKLUS skeemikasutajana SQL Developeris.
-- Skript lisab olemasolevatele kaameraprofiilidele live-vaate intervalli.

ALTER TABLE camera_profiles ADD (
    capture_interval_seconds NUMBER(10)
);

UPDATE camera_profiles
   SET capture_interval_seconds = 5
 WHERE source_image_url IS NOT NULL;

ALTER TABLE camera_profiles ADD CONSTRAINT camera_profiles_capture_interval_ck
    CHECK (
        capture_interval_seconds IS NULL
        OR (source_image_url IS NOT NULL AND capture_interval_seconds >= 0)
    );

COMMIT;
