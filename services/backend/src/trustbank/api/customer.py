import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from trustbank.api.deps import Services, services, valid_id
from trustbank.api.schemas import (
    AnswersRequest,
    AuthorizeRequest,
    CreatePaymentRequest,
    Me,
    RecentTransaction,
    RecipientLookup,
)
from trustbank.auth import Principal, require_customer
from trustbank.errors import not_found
from trustbank.payments.models import PaymentDoc
from trustbank.payments.views import CustomerPayment, to_customer_payment
from trustbank.recipients import resolve

router = APIRouter(tags=["customer"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


def _view(svc: Services, doc: PaymentDoc) -> CustomerPayment:
    return to_customer_payment(doc, svc.clock())


@router.get("/me", response_model=Me)
async def me(svc: Services = Depends(services), who: Principal = Depends(require_customer)) -> Me:
    def load() -> Me:
        customer = svc.dataset.get_customer(who.subject)
        if customer is None:
            raise not_found("Customer not found.")
        account = svc.dataset.account_for_owner(customer.id)
        txns = svc.dataset.transactions_from_account(account.id, limit=5) if account else []
        names: dict[str, str] = {}
        recent: list[RecentTransaction] = []
        for t in txns:
            if t.beneficiary_id not in names:
                b = svc.dataset.get_beneficiary(t.beneficiary_id)
                names[t.beneficiary_id] = b.display_name if b else "Unknown recipient"
            recent.append(
                RecentTransaction(
                    id=t.id,
                    recipient_name=names[t.beneficiary_id],
                    amount=t.amount,
                    note=t.note,
                    timestamp=t.timestamp,
                )
            )
        return Me(
            display_name=customer.display_name,
            handle=customer.handle,
            balance=customer.balance,
            recent_transactions=recent,
        )

    return await asyncio.to_thread(load)


@router.get("/recipients/lookup", response_model=RecipientLookup)
async def lookup(
    q: Annotated[str, Query(min_length=1, max_length=64)],
    svc: Services = Depends(services),
    who: Principal = Depends(require_customer),
) -> RecipientLookup:
    resolved = await asyncio.to_thread(resolve, svc.dataset, q)
    return RecipientLookup(
        found=resolved.verified,
        verified=resolved.verified,
        display_name=resolved.beneficiary.display_name if resolved.beneficiary else None,
        handle=resolved.handle,
        masked_account=resolved.account.masked_number if resolved.account else None,
    )


@router.post("/payments", response_model=CustomerPayment)
async def create_payment(
    body: CreatePaymentRequest,
    idempotency_key: IdempotencyKey,
    svc: Services = Depends(services),
    who: Principal = Depends(require_customer),
) -> CustomerPayment:
    doc = await svc.payments.create_payment(
        who.subject, body.recipient, body.amount, (body.note or "").strip(), idempotency_key
    )
    return _view(svc, doc)


@router.get("/payments/{payment_id}", response_model=CustomerPayment)
async def get_payment(
    payment_id: str, svc: Services = Depends(services), who: Principal = Depends(require_customer)
) -> CustomerPayment:
    doc = await asyncio.to_thread(svc.payments.get, who.subject, valid_id(payment_id))
    return _view(svc, doc)


@router.post("/payments/{payment_id}/answers", response_model=CustomerPayment)
async def answers(
    payment_id: str,
    body: AnswersRequest,
    svc: Services = Depends(services),
    who: Principal = Depends(require_customer),
) -> CustomerPayment:
    doc = await svc.payments.submit_answers(who.subject, valid_id(payment_id), body.answers)
    return _view(svc, doc)


@router.post("/payments/{payment_id}/acknowledge", response_model=CustomerPayment)
async def acknowledge(
    payment_id: str, svc: Services = Depends(services), who: Principal = Depends(require_customer)
) -> CustomerPayment:
    return _view(svc, await svc.payments.acknowledge(who.subject, valid_id(payment_id)))


@router.post("/payments/{payment_id}/verify", response_model=CustomerPayment)
async def verify(
    payment_id: str, svc: Services = Depends(services), who: Principal = Depends(require_customer)
) -> CustomerPayment:
    return _view(svc, await svc.payments.verify(who.subject, valid_id(payment_id)))


@router.post("/payments/{payment_id}/continue", response_model=CustomerPayment)
async def continue_payment(
    payment_id: str, svc: Services = Depends(services), who: Principal = Depends(require_customer)
) -> CustomerPayment:
    return _view(svc, await svc.payments.continue_(who.subject, valid_id(payment_id)))


@router.post("/payments/{payment_id}/authorize", response_model=CustomerPayment)
async def authorize(
    payment_id: str,
    body: AuthorizeRequest,
    svc: Services = Depends(services),
    who: Principal = Depends(require_customer),
) -> CustomerPayment:
    return _view(svc, await svc.payments.authorize(who.subject, valid_id(payment_id), body.pin))


@router.post("/payments/{payment_id}/cancel", response_model=CustomerPayment)
async def cancel(
    payment_id: str, svc: Services = Depends(services), who: Principal = Depends(require_customer)
) -> CustomerPayment:
    return _view(svc, await svc.payments.cancel(who.subject, valid_id(payment_id)))
