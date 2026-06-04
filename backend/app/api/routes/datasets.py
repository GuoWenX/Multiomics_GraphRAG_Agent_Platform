from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postgres import postgres_session
from app.repositories.experiment_dataset_repository import ExperimentDatasetRepository
from app.schemas.datasets import ExperimentDatasetCreate, ExperimentDatasetResponse, ExperimentDatasetUpdate

router = APIRouter()


async def get_dataset_repository(
    session: AsyncSession = Depends(postgres_session),
) -> ExperimentDatasetRepository:
    return ExperimentDatasetRepository(session)


@router.get("", response_model=list[ExperimentDatasetResponse])
async def list_datasets(
    repository: ExperimentDatasetRepository = Depends(get_dataset_repository),
) -> list[dict]:
    return await repository.list()


@router.post("", response_model=ExperimentDatasetResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    payload: ExperimentDatasetCreate,
    repository: ExperimentDatasetRepository = Depends(get_dataset_repository),
) -> dict:
    return await repository.create(payload)


@router.patch("/{dataset_id}", response_model=ExperimentDatasetResponse)
async def update_dataset(
    dataset_id: str,
    payload: ExperimentDatasetUpdate,
    repository: ExperimentDatasetRepository = Depends(get_dataset_repository),
) -> dict:
    dataset = await repository.update(dataset_id, payload)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    repository: ExperimentDatasetRepository = Depends(get_dataset_repository),
) -> dict[str, bool]:
    deleted = await repository.delete(dataset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"deleted": True}
