"""Firestore repository for the synthetic dataset (system of record)."""

from collections.abc import Iterator, Sequence
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel

from trustbank.config import Settings
from trustbank.domain import (
    Account,
    Beneficiary,
    Connection,
    Customer,
    Dataset,
    OwnerType,
    Transaction,
)

CUSTOMERS = "customers"
BENEFICIARIES = "beneficiaries"
ACCOUNTS = "accounts"
TRANSACTIONS = "transactions"
CONNECTIONS = "connections"
DATASET_COLLECTIONS = (CUSTOMERS, BENEFICIARIES, ACCOUNTS, TRANSACTIONS, CONNECTIONS)

_BATCH_SIZE = 400  # Firestore allows 500 writes per batch


def create_client(settings: Settings) -> firestore.Client:
    """Build a client: the emulator when a host is configured, else real Firestore via ADC."""
    if settings.firestore_emulator_host:
        import os

        os.environ["FIRESTORE_EMULATOR_HOST"] = settings.firestore_emulator_host
    return firestore.Client(project=settings.google_cloud_project)


def _to_doc(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="python")


def _chunks[T](items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class DatasetRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._db = client

    def seed(self, dataset: Dataset) -> dict[str, int]:
        """Idempotent upsert keyed by deterministic ids. Returns counts written per collection."""
        groups: dict[str, Sequence[BaseModel]] = {
            CUSTOMERS: dataset.customers,
            BENEFICIARIES: dataset.beneficiaries,
            ACCOUNTS: dataset.accounts,
            TRANSACTIONS: dataset.transactions,
            CONNECTIONS: dataset.connections,
        }
        for name, models in groups.items():
            for chunk in _chunks(models, _BATCH_SIZE):
                batch = self._db.batch()
                for m in chunk:
                    batch.set(self._db.collection(name).document(m.id), _to_doc(m))  # type: ignore[attr-defined]
                batch.commit()
        return {name: len(models) for name, models in groups.items()}

    def reset(self) -> None:
        """Delete every document in the dataset collections."""
        for name in DATASET_COLLECTIONS:
            for chunk in _chunks(list(self._db.collection(name).list_documents()), _BATCH_SIZE):
                batch = self._db.batch()
                for ref in chunk:
                    batch.delete(ref)
                batch.commit()

    def load(self) -> Dataset:
        def read[M: BaseModel](name: str, model: type[M]) -> tuple[M, ...]:
            docs = (model.model_validate(d.to_dict()) for d in self._db.collection(name).stream())
            return tuple(sorted(docs, key=lambda m: m.id))  # type: ignore[attr-defined]

        return Dataset(
            customers=read(CUSTOMERS, Customer),
            beneficiaries=read(BENEFICIARIES, Beneficiary),
            accounts=read(ACCOUNTS, Account),
            transactions=read(TRANSACTIONS, Transaction),
            connections=read(CONNECTIONS, Connection),
        )

    def get_customer(self, customer_id: str) -> Customer | None:
        snap = self._db.collection(CUSTOMERS).document(customer_id).get()
        return Customer.model_validate(snap.to_dict()) if snap.exists else None

    def get_beneficiary(self, beneficiary_id: str) -> Beneficiary | None:
        snap = self._db.collection(BENEFICIARIES).document(beneficiary_id).get()
        return Beneficiary.model_validate(snap.to_dict()) if snap.exists else None

    def account_for_owner(self, owner_id: str) -> Account | None:
        query = (
            self._db.collection(ACCOUNTS)
            .where(filter=FieldFilter("owner_id", "==", owner_id))
            .limit(1)
        )
        docs = list(query.stream())
        return Account.model_validate(docs[0].to_dict()) if docs else None

    def transactions_from_account(self, account_id: str, limit: int = 200) -> list[Transaction]:
        query = (
            self._db.collection(TRANSACTIONS)
            .where(filter=FieldFilter("source_account_id", "==", account_id))
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [Transaction.model_validate(d.to_dict()) for d in query.stream()]

    def list_demo_personas(self) -> list[Customer]:
        query = self._db.collection(CUSTOMERS).where(
            filter=FieldFilter("is_demo_persona", "==", True)
        )
        return sorted(
            (Customer.model_validate(d.to_dict()) for d in query.stream()), key=lambda c: c.id
        )

    def find_beneficiary_by_handle(self, handle: str) -> Beneficiary | None:
        query = self._db.collection(BENEFICIARIES).where(filter=FieldFilter("handle", "==", handle))
        docs = list(query.limit(1).stream())
        return Beneficiary.model_validate(docs[0].to_dict()) if docs else None

    def find_beneficiary_by_account_number(self, number: str) -> Beneficiary | None:
        query = self._db.collection(ACCOUNTS).where(
            filter=FieldFilter("account_number", "==", number)
        )
        docs = list(query.limit(1).stream())
        if not docs:
            return None
        account = Account.model_validate(docs[0].to_dict())
        if account.owner_type != OwnerType.BENEFICIARY:
            return None
        return self.get_beneficiary(account.owner_id)

    def ping(self) -> None:
        next(iter(self._db.collection(CUSTOMERS).limit(1).stream()), None)
