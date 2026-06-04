from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import TextClause, bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.datasets import ExperimentDatasetCreate, ExperimentDatasetUpdate


class ExperimentDatasetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, app_user: str = "nfyy") -> list[dict[str, Any]]:
        result = await self.session.execute(
            text(
                """
                SELECT id::text, app_user, display_name, file_name, file_size, top_k, result_count,
                       group_descriptions, warnings, results, metadata, created_at, updated_at
                FROM experiment_datasets
                WHERE app_user = :app_user
                ORDER BY updated_at DESC, created_at DESC
                """
            ),
            {"app_user": app_user},
        )
        return [dict(row) for row in result.mappings().all()]

    async def create(self, payload: ExperimentDatasetCreate, app_user: str = "nfyy") -> dict[str, Any]:
        query = self._json_query(
            """
            INSERT INTO experiment_datasets (
                app_user, display_name, file_name, file_size, top_k, result_count,
                group_descriptions, warnings, results, metadata
            )
            VALUES (
                :app_user, :display_name, :file_name, :file_size, :top_k, :result_count,
                :group_descriptions, :warnings, :results, :metadata
            )
            RETURNING id::text, app_user, display_name, file_name, file_size, top_k, result_count,
                      group_descriptions, warnings, results, metadata, created_at, updated_at
            """
        )
        result = await self.session.execute(
            query,
            {
                "app_user": app_user,
                "display_name": payload.display_name.strip(),
                "file_name": payload.file_name,
                "file_size": payload.file_size,
                "top_k": payload.top_k,
                "result_count": len(payload.results),
                "group_descriptions": payload.group_descriptions,
                "warnings": payload.warnings,
                "results": payload.results,
                "metadata": payload.metadata,
            },
        )
        await self.session.commit()
        return dict(result.mappings().one())

    async def update(self, dataset_id: str, payload: ExperimentDatasetUpdate, app_user: str = "nfyy") -> dict[str, Any] | None:
        result = await self.session.execute(
            text(
                """
                UPDATE experiment_datasets
                SET display_name = :display_name,
                    updated_at = now()
                WHERE id = CAST(:dataset_id AS uuid)
                  AND app_user = :app_user
                RETURNING id::text, app_user, display_name, file_name, file_size, top_k, result_count,
                          group_descriptions, warnings, results, metadata, created_at, updated_at
                """
            ),
            {
                "dataset_id": dataset_id,
                "app_user": app_user,
                "display_name": payload.display_name.strip(),
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            await self.session.rollback()
            return None
        await self.session.commit()
        return dict(row)

    async def delete(self, dataset_id: str, app_user: str = "nfyy") -> bool:
        result = await self.session.execute(
            text(
                """
                DELETE FROM experiment_datasets
                WHERE id = CAST(:dataset_id AS uuid)
                  AND app_user = :app_user
                """
            ),
            {"dataset_id": dataset_id, "app_user": app_user},
        )
        await self.session.commit()
        return result.rowcount > 0

    def _json_query(self, sql: str) -> TextClause:
        return (
            text(sql)
            .bindparams(bindparam("group_descriptions", type_=JSONB))
            .bindparams(bindparam("warnings", type_=JSONB))
            .bindparams(bindparam("results", type_=JSONB))
            .bindparams(bindparam("metadata", type_=JSONB))
        )
