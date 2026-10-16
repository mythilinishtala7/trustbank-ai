"""Firestore persistence for payments, trace events, assessments and the audit log."""

import hashlib
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from trustbank.contracts import TraceEvent
from trustbank.domain import Customer
from trustbank.payments.models import Assessment, PaymentDoc

PAYMENTS = "payments"
EVENTS = "events"
ASSESSMENTS = "assessments"
AUDIT_LOG = "audit_log"
IDEMPOTENCY = "idempotency_keys"


def new_payment_id() -> str:
    return "txn_" + uuid.uuid4().hex[:8]


def new_assessment_id() -> str:
    return "asm_" + uuid.uuid4().hex[:12]


def idempotency_id(customer_id: str, key: str) -> str:
    return hashlib.sha256(f"{customer_id}:{key}".encode()).hexdigest()


class TxnContext:
    """Reads run immediately; writes are buffered and applied after the callback returns."""

    def __init__(self, db: firestore.Client, transaction: Any, payment_id: str) -> None:
        self._db = db
        self._tx = transaction
        self._writes: list[tuple[Any, dict[str, Any], bool]] = []
        snap = db.collection(PAYMENTS).document(payment_id).get(transaction=transaction)
        self.payment: PaymentDoc | None = (
            PaymentDoc.model_validate(snap.to_dict()) if snap.exists else None
        )
        self._payment_id = payment_id

    def customer(self, customer_id: str) -> Customer | None:
        snap = self._db.collection("customers").document(customer_id).get(transaction=self._tx)
        return Customer.model_validate(snap.to_dict()) if snap.exists else None

    def exists(self, collection: str, doc_id: str) -> bool:
        return bool(
            self._db.collection(collection).document(doc_id).get(transaction=self._tx).exists
        )

    def put_payment(self, doc: PaymentDoc) -> None:
        ref = self._db.collection(PAYMENTS).document(self._payment_id)
        self._writes.append((ref, doc.model_dump(mode="python"), False))

    def put(
        self, collection: str, doc_id: str, data: dict[str, Any], *, merge: bool = False
    ) -> None:
        self._writes.append((self._db.collection(collection).document(doc_id), data, merge))

    def flush(self) -> None:
        for ref, data, merge in self._writes:
            self._tx.set(ref, data, merge=merge)


class PaymentRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._db = client

    @property
    def client(self) -> firestore.Client:
        return self._db

    def ping(self) -> bool:
        list(self._db.collection("customers").limit(1).stream(timeout=3))
        return True

    def create(self, doc: PaymentDoc, idempotency_key_id: str) -> tuple[PaymentDoc, bool]:
        """Create the payment, or return the original one for a repeated idempotency key."""
        idem_ref = self._db.collection(IDEMPOTENCY).document(idempotency_key_id)
        pay_ref = self._db.collection(PAYMENTS).document(doc.id)

        @firestore.transactional
        def run(transaction: Any) -> tuple[str, bool]:
            existing = idem_ref.get(transaction=transaction)
            if existing.exists:
                return str((existing.to_dict() or {})["payment_id"]), False
            transaction.set(idem_ref, {"payment_id": doc.id, "created_at": doc.created_at})
            transaction.set(pay_ref, doc.model_dump(mode="python"))
            return doc.id, True

        payment_id, created = run(self._db.transaction())
        stored = self.get(payment_id)
        assert stored is not None
        return stored, created

    def find_by_idempotency(self, idempotency_key_id: str) -> str | None:
        snap = self._db.collection(IDEMPOTENCY).document(idempotency_key_id).get()
        return str((snap.to_dict() or {})["payment_id"]) if snap.exists else None

    def get(self, payment_id: str) -> PaymentDoc | None:
        snap = self._db.collection(PAYMENTS).document(payment_id).get()
        return PaymentDoc.model_validate(snap.to_dict()) if snap.exists else None

    def transact[T](self, payment_id: str, fn: Callable[[TxnContext], T]) -> T:
        """Run fn in a Firestore transaction on the payment document (fn may be retried)."""

        @firestore.transactional
        def run(transaction: Any) -> T:
            ctx = TxnContext(self._db, transaction, payment_id)
            result = fn(ctx)
            ctx.flush()
            return result

        return run(self._db.transaction())  # type: ignore[no-any-return]

    def recent(self, limit: int) -> list[PaymentDoc]:
        query = (
            self._db.collection(PAYMENTS)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [PaymentDoc.model_validate(d.to_dict()) for d in query.stream()]

    def add_event(self, payment_id: str, event: TraceEvent) -> None:
        data = event.model_dump(mode="json", by_alias=False)
        ref = self._db.collection(PAYMENTS).document(payment_id).collection(EVENTS)
        ref.document(f"{event.seq:08d}").set(data)

    def last_event_seq(self, payment_id: str) -> int:
        query = (
            self._db.collection(PAYMENTS)
            .document(payment_id)
            .collection(EVENTS)
            .order_by("seq", direction=firestore.Query.DESCENDING)
            .limit(1)
        )
        docs = list(query.stream())
        return int((docs[0].to_dict() or {})["seq"]) if docs else 0

    def events_after(self, payment_id: str, after: int, limit: int = 500) -> list[TraceEvent]:
        query = (
            self._db.collection(PAYMENTS)
            .document(payment_id)
            .collection(EVENTS)
            .where(filter=FieldFilter("seq", ">", after))
            .order_by("seq")
            .limit(limit)
        )
        return [TraceEvent.model_validate(d.to_dict()) for d in query.stream()]

    def add_assessment(self, payment_id: str, customer_id: str, assessment: Assessment) -> None:
        data = assessment.model_dump(mode="json", by_alias=False)
        data["payment_id"] = payment_id
        data["customer_id"] = customer_id
        # create() fails if the id exists: assessments are append-only.
        self._db.collection(ASSESSMENTS).document(assessment.id).create(data)

    def assessments_for(self, payment_id: str) -> list[Assessment]:
        query = self._db.collection(ASSESSMENTS).where(
            filter=FieldFilter("payment_id", "==", payment_id)
        )
        items: list[Assessment] = []
        for d in query.stream():
            data = d.to_dict() or {}
            data.pop("payment_id", None)
            data.pop("customer_id", None)
            items.append(Assessment.model_validate(data))
        return sorted(items, key=lambda a: (a.created_at, a.stage != "INITIAL"))

    def audit(self, at: datetime, action: str, actor: str, **fields: str | None) -> None:
        self._db.collection(AUDIT_LOG).add({"at": at, "action": action, "actor": actor, **fields})
