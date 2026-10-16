import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from trustbank.api.deps import Services, services, valid_id
from trustbank.api.schemas import InvestigationTransaction, TimelineResponse, TransactionListItem
from trustbank.auth import Principal, require_investigator

router = APIRouter(prefix="/investigation", tags=["investigation"])


@router.get("/transactions", response_model=list[TransactionListItem])
async def list_transactions(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    svc: Services = Depends(services),
    who: Principal = Depends(require_investigator),
) -> list[TransactionListItem]:
    return await asyncio.to_thread(svc.investigation.list_recent, limit)


@router.get("/transactions/{transaction_id}", response_model=InvestigationTransaction)
async def transaction_detail(
    transaction_id: str,
    svc: Services = Depends(services),
    who: Principal = Depends(require_investigator),
) -> InvestigationTransaction:
    return await svc.investigation.detail(valid_id(transaction_id), who.subject)


@router.get("/transactions/{transaction_id}/timeline", response_model=TimelineResponse)
async def timeline(
    transaction_id: str,
    after: Annotated[int, Query(ge=0)] = 0,
    svc: Services = Depends(services),
    who: Principal = Depends(require_investigator),
) -> TimelineResponse:
    return await svc.investigation.timeline(valid_id(transaction_id), after)


@router.get(
    "/transactions/{transaction_id}/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "Server-sent events"}},
)
async def events(
    transaction_id: str,
    after: Annotated[int, Query(ge=0)] = 0,
    svc: Services = Depends(services),
    who: Principal = Depends(require_investigator),
) -> StreamingResponse:
    frames = await svc.investigation.open_stream(valid_id(transaction_id), after)
    return StreamingResponse(
        frames,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
