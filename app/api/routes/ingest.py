"""
Ingest API Route — triggers dataset ingestion and index building.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.dependencies import get_chunk_repo, get_retrieval_service
from app.domain.models import IngestStats
from app.repositories.chunk_repository import ChunkRepository
from app.services.ingest_service import IngestService
from app.services.retrieval_service import RetrievalService

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


class IngestRequest(BaseModel):
    csv_path: str = ""
    rebuild_vectors: bool = False


@router.post("", response_model=IngestStats)
def trigger_ingest(
    req: IngestRequest,
    chunk_repo: ChunkRepository = Depends(get_chunk_repo),
    retrieval_svc: RetrievalService = Depends(get_retrieval_service),
    settings: Settings = Depends(get_settings),
):
    """
    Parse and index emails from CSV.
    Pass csv_path to override default; set rebuild_vectors=true to rebuild LanceDB.
    """
    csv_path = req.csv_path or str(settings.enron_csv)
    svc = IngestService(chunk_repo=chunk_repo, settings=settings)

    try:
        stats = svc.ingest_csv(csv_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Rebuild retrieval index
    retrieval_svc.build_index(embed=req.rebuild_vectors)
    return stats


@router.get("/status")
def ingest_status(
    chunk_repo: ChunkRepository = Depends(get_chunk_repo),
):
    """Check if the index is populated."""
    count = chunk_repo.count()
    threads = chunk_repo.list_threads()
    return {
        "indexed": count > 0,
        "chunk_count": count,
        "thread_count": len(threads),
        "threads": list(threads.keys()),
    }
