"""Allow named Radarr/Sonarr instances and target requests to one instance.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07
"""
import sqlalchemy as sa
from alembic import op


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older databases already had a non-null name column, but be defensive about
    # hand-edited/early development databases containing an empty label.
    op.execute("UPDATE services SET name = kind WHERE name IS NULL OR trim(name) = ''")
    with op.batch_alter_table("services") as batch_op:
        batch_op.drop_index("ix_services_kind")
        batch_op.create_index("ix_services_kind", ["kind"], unique=False)
        batch_op.create_unique_constraint("uq_service_kind_name", ["kind", "name"])
        batch_op.create_check_constraint("ck_service_name_nonempty", "length(trim(name)) > 0")

    with op.batch_alter_table("media_requests") as batch_op:
        batch_op.add_column(sa.Column("service_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("service_name", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_media_requests_service_id", "services", ["service_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index("ix_media_requests_service_id", ["service_id"], unique=False)
        batch_op.drop_constraint("uq_request_media", type_="unique")
        batch_op.create_unique_constraint(
            "uq_request_media", ["service_id", "media_type", "tmdb_id", "tvdb_id"]
        )

    # Existing requests keep pointing at the same (original) app. Requests made
    # without a connected app retain a useful label and fall back to the default.
    op.execute(
        """
        UPDATE media_requests
        SET service_id = (
                SELECT id FROM services
                WHERE kind = CASE media_requests.media_type WHEN 'movie' THEN 'radarr' ELSE 'sonarr' END
                ORDER BY id LIMIT 1
            ),
            service_name = COALESCE(
                (SELECT name FROM services
                 WHERE kind = CASE media_requests.media_type WHEN 'movie' THEN 'radarr' ELSE 'sonarr' END
                 ORDER BY id LIMIT 1),
                CASE media_requests.media_type WHEN 'movie' THEN 'Radarr' ELSE 'Sonarr' END
            )
        """
    )


def downgrade() -> None:
    # This succeeds for a single-instance database. As expected, SQLite rejects
    # a downgrade that would collapse distinct same-title or same-kind rows.
    with op.batch_alter_table("media_requests") as batch_op:
        batch_op.drop_constraint("uq_request_media", type_="unique")
        batch_op.create_unique_constraint("uq_request_media", ["media_type", "tmdb_id", "tvdb_id"])
        batch_op.drop_index("ix_media_requests_service_id")
        batch_op.drop_constraint("fk_media_requests_service_id", type_="foreignkey")
        batch_op.drop_column("service_name")
        batch_op.drop_column("service_id")

    with op.batch_alter_table("services") as batch_op:
        batch_op.drop_constraint("ck_service_name_nonempty", type_="check")
        batch_op.drop_constraint("uq_service_kind_name", type_="unique")
        batch_op.drop_index("ix_services_kind")
        batch_op.create_index("ix_services_kind", ["kind"], unique=True)
