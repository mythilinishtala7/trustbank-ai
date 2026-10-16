"""Domain documents stored in Firestore and projected into the knowledge graph.

These carry facts only. They have no fraud label, score, complaint, verdict, or scenario identity.
Money is whole rupees. Timestamps are timezone-aware (UTC).
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class Provenance(StrEnum):
    VERIFIED_SYNTHETIC = "VERIFIED_SYNTHETIC"
    INFERRED = "INFERRED"
    USER_PROVIDED = "USER_PROVIDED"


class OwnerType(StrEnum):
    CUSTOMER = "CUSTOMER"
    BENEFICIARY = "BENEFICIARY"


class ConnectionKind(StrEnum):
    SHARED_DEVICE = "SHARED_DEVICE"
    BUSINESS_SUPPLIER = "BUSINESS_SUPPLIER"
    SAME_OWNER = "SAME_OWNER"


class TransactionStatus(StrEnum):
    COMPLETED = "COMPLETED"


class _Document(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _plain_datetime(cls, value: Any) -> Any:
        # Firestore returns a datetime subclass that the Neo4j driver rejects.
        if isinstance(value, datetime) and type(value) is not datetime:
            return datetime.fromisoformat(value.isoformat())
        return value


class Customer(_Document):
    id: str
    display_name: str
    handle: str
    balance: int
    is_demo_persona: bool = False


class Beneficiary(_Document):
    id: str
    display_name: str
    handle: str
    first_seen_at: datetime


class Account(_Document):
    id: str
    owner_id: str
    owner_type: OwnerType
    opened_at: datetime
    account_number: str
    masked_number: str


class Transaction(_Document):
    id: str
    source_account_id: str
    beneficiary_id: str
    amount: int
    currency: str = "INR"
    note: str
    timestamp: datetime
    status: TransactionStatus = TransactionStatus.COMPLETED


class Connection(_Document):
    """A declared relationship between two accounts. Evidence to investigate, not proof."""

    id: str
    account_a_id: str
    account_b_id: str
    kind: ConnectionKind
    provenance: Provenance = Provenance.VERIFIED_SYNTHETIC


class Dataset(_Document):
    customers: tuple[Customer, ...]
    beneficiaries: tuple[Beneficiary, ...]
    accounts: tuple[Account, ...]
    transactions: tuple[Transaction, ...]
    connections: tuple[Connection, ...]
