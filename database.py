from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Sequence


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


@dataclass(frozen=True)
class User:
    user_id: int
    public_id: str
    email: str
    display_name: str
    role_code: str
    enabled: bool


def _oracle_kwargs() -> dict[str, str]:
    required = {
        "user": os.getenv("ORACLE_USER", "").strip(),
        "password": os.getenv("ORACLE_PASSWORD", ""),
        "dsn": os.getenv("ORACLE_DSN", "").strip(),
    }
    if not all(required.values()):
        raise RuntimeError("ORACLE_USER, ORACLE_PASSWORD and ORACLE_DSN are required")
    optional = {
        "config_dir": os.path.expanduser(os.getenv("ORACLE_CONFIG_DIR", "").strip()),
        "wallet_location": os.path.expanduser(
            os.getenv("ORACLE_WALLET_LOCATION", "").strip()
        ),
        "wallet_password": os.getenv("ORACLE_WALLET_PASSWORD", ""),
    }
    return {**required, **{key: value for key, value in optional.items() if value}}


def _row(cursor: Any, value: Sequence[Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        column[0].lower(): _utc_datetime(item)
        for column, item in zip(cursor.description, value)
    }


def _utc_datetime(value: Any) -> Any:
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _rows(cursor: Any) -> list[dict[str, Any]]:
    return [_row(cursor, value) for value in cursor.fetchall()]  # type: ignore[misc]


def _returning_number(variable: Any) -> int:
    value = variable.getvalue()
    if isinstance(value, list):
        value = value[0]
    return int(value)


def _user_from_row(row: dict[str, Any]) -> User:
    return User(
        user_id=int(row["user_id"]),
        public_id=str(row["public_id"]),
        email=str(row.get("email") or ""),
        display_name=str(row.get("display_name") or row.get("email") or ""),
        role_code=str(row["role_code"]),
        enabled=bool(row["enabled"]),
    )


class OracleRepository:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    @classmethod
    def from_env(cls) -> "OracleRepository":
        import oracledb

        pool = oracledb.create_pool(
            min=int(os.getenv("ORACLE_POOL_MIN", "1")),
            max=int(os.getenv("ORACLE_POOL_MAX", "5")),
            increment=1,
            **_oracle_kwargs(),
        )
        return cls(pool)

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        with self.pool.acquire() as connection:
            yield connection

    def get_or_create_google_user(
        self, subject: str, email: str, display_name: str
    ) -> User:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, public_id, email, display_name, role_code, enabled
                  FROM app_users
                 WHERE identity_provider = 'GOOGLE'
                   AND external_subject = :subject
                   AND end_date IS NULL
                """,
                {"subject": subject},
            )
            row = _row(cursor, cursor.fetchone())
            if row is None:
                output = cursor.var(int)
                cursor.execute(
                    """
                    INSERT INTO app_users (
                        public_id, identity_provider, external_subject, email,
                        display_name, role_code, enabled
                    ) VALUES (
                        :public_id, 'GOOGLE', :subject, :email,
                        :display_name, 'USER', 1
                    ) RETURNING user_id INTO :output
                    """,
                    {
                        "public_id": str(uuid.uuid4()),
                        "subject": subject,
                        "email": email.lower(),
                        "display_name": display_name,
                        "output": output,
                    },
                )
                user_id = _returning_number(output)
            else:
                user_id = int(row["user_id"])
                cursor.execute(
                    """
                    UPDATE app_users
                       SET email = :email,
                           display_name = :display_name,
                           last_updated = SYSTIMESTAMP
                     WHERE user_id = :user_id
                    """,
                    {
                        "email": email.lower(),
                        "display_name": display_name,
                        "user_id": user_id,
                    },
                )
            connection.commit()
        return self.get_user(user_id)

    def get_user(self, user_id: int) -> User:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, public_id, email, display_name, role_code, enabled
                  FROM app_users
                 WHERE user_id = :user_id AND end_date IS NULL
                """,
                {"user_id": user_id},
            )
            row = _row(cursor, cursor.fetchone())
        if row is None:
            raise NotFoundError("User not found")
        return _user_from_row(row)

    def training_history(self, source_sha256: str) -> dict[str, Any] | None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ti.training_image_id, ti.public_id, ti.created,
                       ti.end_date, u.display_name, u.email
                  FROM training_images ti
                  JOIN app_users u ON u.user_id = ti.candidate_by_user_id
                 WHERE ti.source_sha256 = :source_sha256
                 ORDER BY ti.created
                """,
                {"source_sha256": source_sha256},
            )
            candidates = _rows(cursor)
            if not candidates:
                return None
            selections: list[dict[str, Any]] = []
            for candidate in candidates:
                cursor.execute(
                    """
                    SELECT tp.public_id AS package_id, tp.package_name,
                           tpi.created AS added_at,
                           u.display_name AS added_by_name,
                           u.email AS added_by_email
                      FROM training_package_images tpi
                      JOIN training_packages tp
                        ON tp.training_package_id = tpi.training_package_id
                      JOIN app_users u ON u.user_id = tpi.added_by_user_id
                     WHERE tpi.training_image_id = :training_image_id
                     ORDER BY tpi.created
                    """,
                    {"training_image_id": candidate["training_image_id"]},
                )
                packages = _rows(cursor)
                selections.append(
                    {
                        "training_image_id": candidate["public_id"],
                        "candidate_at": candidate["created"],
                        "candidate_by": candidate["display_name"]
                        or candidate["email"],
                        "file_available": candidate["end_date"] is None,
                        "packages": packages,
                    }
                )
        return {"selections": selections}

    def create_training_image(self, values: dict[str, Any]) -> int:
        with self._connection() as connection, connection.cursor() as cursor:
            import oracledb

            output = cursor.var(int)
            try:
                cursor.setinputsizes(
                    tags_json=oracledb.DB_TYPE_JSON,
                    analysis_json=oracledb.DB_TYPE_JSON,
                )
                cursor.execute(
                    """
                    INSERT INTO training_images (
                        public_id, candidate_by_user_id, original_filename,
                        image_relative_path, label_relative_path,
                        source_media_type, stored_media_type,
                        source_size_bytes, stored_size_bytes,
                        source_width, source_height, stored_width, stored_height,
                        source_sha256, stored_sha256, reason, tags_json,
                        analysis_json, model_sha256, label_confidence
                    ) VALUES (
                        :public_id, :candidate_by_user_id, :original_filename,
                        :image_relative_path, :label_relative_path,
                        :source_media_type, :stored_media_type,
                        :source_size_bytes, :stored_size_bytes,
                        :source_width, :source_height, :stored_width, :stored_height,
                        :source_sha256, :stored_sha256, :reason, :tags_json,
                        :analysis_json, :model_sha256, :label_confidence
                    ) RETURNING training_image_id INTO :output
                    """,
                    {
                        **values,
                        "tags_json": values["tags_json"],
                        "analysis_json": values["analysis_json"],
                        "output": output,
                    },
                )
                connection.commit()
            except Exception as exc:
                connection.rollback()
                if getattr(exc, "args", None) and "ORA-00001" in str(exc):
                    raise ConflictError("Image is already a training candidate") from exc
                raise
        return _returning_number(output)

    def list_training_images(
        self,
        search: str = "",
        limit: int = 100,
        offset: int = 0,
        package_filter: str = "",
    ) -> dict[str, Any]:
        pattern = f"%{search.lower()}%"
        package_mode = (
            "none" if package_filter == "__none__" else "package" if package_filter else "all"
        )
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ti.training_image_id, ti.public_id, ti.original_filename,
                       ti.image_relative_path,
                       ti.reason, ti.tags_json, ti.analysis_json, ti.created,
                       u.display_name AS candidate_by_name,
                       u.email AS candidate_by_email,
                       (SELECT COUNT(*)
                          FROM training_package_images tpi
                         WHERE tpi.training_image_id = ti.training_image_id
                           AND tpi.end_date IS NULL) AS package_count,
                       COUNT(*) OVER () AS total_count
                  FROM training_images ti
                  JOIN app_users u ON u.user_id = ti.candidate_by_user_id
                 WHERE ti.end_date IS NULL
                   AND (
                       :search = '' OR
                       LOWER(ti.original_filename) LIKE :pattern OR
                       LOWER(ti.reason) LIKE :pattern OR
                       LOWER(JSON_SERIALIZE(ti.tags_json RETURNING VARCHAR2(4000)))
                           LIKE :pattern
                   )
                   AND (
                       :package_mode = 'all'
                       OR (
                           :package_mode = 'none'
                           AND NOT EXISTS (
                               SELECT 1
                                 FROM training_package_images tpi_filter
                                 JOIN training_packages tp_filter
                                   ON tp_filter.training_package_id =
                                      tpi_filter.training_package_id
                                WHERE tpi_filter.training_image_id =
                                      ti.training_image_id
                                  AND tpi_filter.end_date IS NULL
                                  AND tp_filter.end_date IS NULL
                           )
                       )
                       OR (
                           :package_mode = 'package'
                           AND EXISTS (
                               SELECT 1
                                 FROM training_package_images tpi_filter
                                 JOIN training_packages tp_filter
                                   ON tp_filter.training_package_id =
                                      tpi_filter.training_package_id
                                WHERE tpi_filter.training_image_id =
                                      ti.training_image_id
                                  AND tpi_filter.end_date IS NULL
                                  AND tp_filter.end_date IS NULL
                                  AND tp_filter.public_id = :package_public_id
                           )
                       )
                   )
                 ORDER BY ti.created DESC
                 OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
                """,
                {
                    "search": search,
                    "pattern": pattern,
                    "package_mode": package_mode,
                    "package_public_id": package_filter if package_mode == "package" else None,
                    "offset": offset,
                    "limit": limit,
                },
            )
            rows = _rows(cursor)
            memberships: dict[int, list[dict[str, Any]]] = {
                int(row["training_image_id"]): [] for row in rows
            }
            if memberships:
                binds = {
                    f"image_id_{index}": image_id
                    for index, image_id in enumerate(memberships)
                }
                placeholders = ", ".join(f":{name}" for name in binds)
                cursor.execute(
                    f"""
                    SELECT tpi.training_image_id,
                           tp.public_id AS package_id,
                           tp.package_name,
                           tpi.created AS added_at,
                           u.display_name AS added_by_name,
                           u.email AS added_by_email
                      FROM training_package_images tpi
                      JOIN training_packages tp
                        ON tp.training_package_id = tpi.training_package_id
                      JOIN app_users u ON u.user_id = tpi.added_by_user_id
                     WHERE tpi.training_image_id IN ({placeholders})
                       AND tpi.end_date IS NULL
                       AND tp.end_date IS NULL
                     ORDER BY tpi.created, tpi.training_package_image_id
                    """,
                    binds,
                )
                for membership in _rows(cursor):
                    image_id = int(membership.pop("training_image_id"))
                    memberships[image_id].append(membership)
        total = int(rows[0]["total_count"]) if rows else 0
        for row in rows:
            image_id = int(row.pop("training_image_id"))
            row.pop("total_count", None)
            row["packages"] = memberships[image_id]
        return {"items": rows, "total": total}

    def get_training_image(self, public_id: str, include_deleted: bool = False) -> dict[str, Any]:
        end_filter = "" if include_deleted else "AND ti.end_date IS NULL"
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT ti.*
                  FROM training_images ti
                 WHERE ti.public_id = :public_id {end_filter}
                """,
                {"public_id": public_id},
            )
            row = _row(cursor, cursor.fetchone())
        if row is None:
            raise NotFoundError("Training image not found")
        return row

    def close_training_image(self, public_id: str) -> dict[str, Any]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT training_image_id, image_relative_path, label_relative_path
                  FROM training_images
                 WHERE public_id = :public_id AND end_date IS NULL
                   FOR UPDATE
                """,
                {"public_id": public_id},
            )
            row = _row(cursor, cursor.fetchone())
            if row is None:
                raise NotFoundError("Training image not found")
            cursor.execute(
                """
                UPDATE training_package_images tpi
                   SET end_date = SYSDATE, last_updated = SYSTIMESTAMP
                 WHERE training_image_id = :training_image_id
                   AND end_date IS NULL
                   AND EXISTS (
                       SELECT 1 FROM training_packages tp
                        WHERE tp.training_package_id = tpi.training_package_id
                          AND tp.first_downloaded_at IS NULL
                   )
                """,
                {"training_image_id": row["training_image_id"]},
            )
            cursor.execute(
                """
                UPDATE training_images
                   SET end_date = SYSDATE, last_updated = SYSTIMESTAMP
                 WHERE training_image_id = :training_image_id
                """,
                {"training_image_id": row["training_image_id"]},
            )
            connection.commit()
        return row

    def create_training_package(self, name: str, user_id: int) -> dict[str, Any]:
        public_id = str(uuid.uuid4())
        with self._connection() as connection, connection.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO training_packages (
                        public_id, package_name, created_by_user_id
                    ) VALUES (:public_id, :package_name, :user_id)
                    """,
                    {"public_id": public_id, "package_name": name, "user_id": user_id},
                )
                connection.commit()
            except Exception as exc:
                connection.rollback()
                if "ORA-00001" in str(exc):
                    raise ConflictError("Training package name already exists") from exc
                raise
        return self.get_training_package(public_id)

    def get_training_package(self, public_id: str) -> dict[str, Any]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tp.training_package_id, tp.public_id, tp.package_name,
                       tp.created, tp.first_downloaded_at,
                       creator.display_name AS created_by_name,
                       creator.email AS created_by_email,
                       first_user.display_name AS first_downloaded_by_name,
                       (SELECT COUNT(*) FROM training_package_images tpi
                         WHERE tpi.training_package_id = tp.training_package_id
                           AND tpi.end_date IS NULL) AS image_count,
                       (SELECT MAX(tpd.created) FROM training_package_downloads tpd
                         WHERE tpd.training_package_id = tp.training_package_id
                           AND tpd.end_date IS NULL) AS last_downloaded_at,
                       (SELECT MAX(u.display_name) KEEP (
                                   DENSE_RANK LAST ORDER BY tpd.created,
                                   tpd.training_package_download_id)
                          FROM training_package_downloads tpd
                          JOIN app_users u ON u.user_id = tpd.downloaded_by_user_id
                         WHERE tpd.training_package_id = tp.training_package_id
                           AND tpd.end_date IS NULL) AS last_downloaded_by_name
                  FROM training_packages tp
                  JOIN app_users creator ON creator.user_id = tp.created_by_user_id
                  LEFT JOIN app_users first_user
                    ON first_user.user_id = tp.first_downloaded_by_user_id
                 WHERE tp.public_id = :public_id AND tp.end_date IS NULL
                """,
                {"public_id": public_id},
            )
            row = _row(cursor, cursor.fetchone())
        if row is None:
            raise NotFoundError("Training package not found")
        return row

    def list_training_packages(self) -> list[dict[str, Any]]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tp.public_id
                  FROM training_packages tp
                 WHERE tp.end_date IS NULL
                 ORDER BY tp.created DESC
                """
            )
            ids = [str(value[0]) for value in cursor.fetchall()]
        return [self.get_training_package(public_id) for public_id in ids]

    def add_images_to_package(
        self, package_public_id: str, image_public_ids: list[str], user_id: int
    ) -> dict[str, Any]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT training_package_id, first_downloaded_at
                  FROM training_packages
                 WHERE public_id = :public_id AND end_date IS NULL
                   FOR UPDATE
                """,
                {"public_id": package_public_id},
            )
            package = _row(cursor, cursor.fetchone())
            if package is None:
                raise NotFoundError("Training package not found")
            if package["first_downloaded_at"] is not None:
                raise ConflictError("Downloaded training package is locked")
            added = 0
            for image_public_id in dict.fromkeys(image_public_ids):
                cursor.execute(
                    """
                    SELECT training_image_id
                      FROM training_images
                     WHERE public_id = :public_id AND end_date IS NULL
                    """,
                    {"public_id": image_public_id},
                )
                value = cursor.fetchone()
                if value is None:
                    raise NotFoundError(f"Training image not found: {image_public_id}")
                image_id = int(value[0])
                cursor.execute(
                    """
                    SELECT 1 FROM training_package_images
                     WHERE training_package_id = :package_id
                       AND training_image_id = :image_id
                       AND end_date IS NULL
                    """,
                    {"package_id": package["training_package_id"], "image_id": image_id},
                )
                if cursor.fetchone() is not None:
                    continue
                cursor.execute(
                    """
                    INSERT INTO training_package_images (
                        public_id, training_package_id, training_image_id,
                        added_by_user_id
                    ) VALUES (:public_id, :package_id, :image_id, :user_id)
                    """,
                    {
                        "public_id": str(uuid.uuid4()),
                        "package_id": package["training_package_id"],
                        "image_id": image_id,
                        "user_id": user_id,
                    },
                )
                added += 1
            connection.commit()
        result = self.get_training_package(package_public_id)
        result["added_count"] = added
        return result

    def remove_image_from_package(
        self, package_public_id: str, image_public_id: str
    ) -> None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT training_package_id, first_downloaded_at
                  FROM training_packages
                 WHERE public_id = :public_id AND end_date IS NULL
                   FOR UPDATE
                """,
                {"public_id": package_public_id},
            )
            package = _row(cursor, cursor.fetchone())
            if package is None:
                raise NotFoundError("Training package not found")
            if package["first_downloaded_at"] is not None:
                raise ConflictError("Downloaded training package is locked")
            cursor.execute(
                """
                UPDATE training_package_images tpi
                   SET end_date = SYSDATE, last_updated = SYSTIMESTAMP
                 WHERE tpi.training_package_id = :package_id
                   AND tpi.end_date IS NULL
                   AND tpi.training_image_id = (
                       SELECT training_image_id FROM training_images
                        WHERE public_id = :image_public_id
                   )
                """,
                {
                    "package_id": package["training_package_id"],
                    "image_public_id": image_public_id,
                },
            )
            if cursor.rowcount == 0:
                raise NotFoundError("Image is not in the training package")
            connection.commit()

    def package_export_snapshot(self, public_id: str) -> dict[str, Any]:
        package = self.get_training_package(public_id)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ti.public_id, ti.original_filename,
                       ti.image_relative_path, ti.label_relative_path,
                       ti.reason, ti.created, ti.end_date,
                       u.display_name AS candidate_by_name,
                       tpi.created AS added_at,
                       added.display_name AS added_by_name,
                       added.email AS added_by_email
                  FROM training_package_images tpi
                  JOIN training_images ti
                    ON ti.training_image_id = tpi.training_image_id
                  JOIN app_users u ON u.user_id = ti.candidate_by_user_id
                  JOIN app_users added ON added.user_id = tpi.added_by_user_id
                 WHERE tpi.training_package_id = :package_id
                   AND tpi.end_date IS NULL
                 ORDER BY tpi.created, tpi.training_package_image_id
                """,
                {"package_id": package["training_package_id"]},
            )
            items = _rows(cursor)
        package["items"] = items
        return package

    def record_package_download(
        self, public_id: str, user_id: int, expected_image_ids: list[str]
    ) -> None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT training_package_id, first_downloaded_at
                  FROM training_packages
                 WHERE public_id = :public_id AND end_date IS NULL
                   FOR UPDATE
                """,
                {"public_id": public_id},
            )
            package = _row(cursor, cursor.fetchone())
            if package is None:
                raise NotFoundError("Training package not found")
            cursor.execute(
                """
                SELECT ti.public_id
                  FROM training_package_images tpi
                  JOIN training_images ti
                    ON ti.training_image_id = tpi.training_image_id
                 WHERE tpi.training_package_id = :package_id
                   AND tpi.end_date IS NULL
                 ORDER BY tpi.created, tpi.training_package_image_id
                """,
                {"package_id": package["training_package_id"]},
            )
            actual_ids = [str(value[0]) for value in cursor.fetchall()]
            if actual_ids != expected_image_ids:
                raise ConflictError("Training package changed during export")
            if package["first_downloaded_at"] is None:
                cursor.execute(
                    """
                    UPDATE training_packages
                       SET first_downloaded_at = SYSTIMESTAMP,
                           first_downloaded_by_user_id = :user_id,
                           last_updated = SYSTIMESTAMP
                     WHERE training_package_id = :package_id
                    """,
                    {"user_id": user_id, "package_id": package["training_package_id"]},
                )
            cursor.execute(
                """
                INSERT INTO training_package_downloads (
                    public_id, training_package_id, downloaded_by_user_id,
                    image_count
                ) VALUES (:public_id, :package_id, :user_id, :image_count)
                """,
                {
                    "public_id": str(uuid.uuid4()),
                    "package_id": package["training_package_id"],
                    "user_id": user_id,
                    "image_count": len(actual_ids),
                },
            )
            connection.commit()

