"""Customer-facing response models. Whitelists only: no scores, agents, graph or other customers."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PersonaOut(_Out):
    id: str
    display_name: str


class CustomerAuthIn(BaseModel):
    persona_id: str = Field(min_length=1, max_length=64)


class InvestigatorAuthIn(BaseModel):
    code: str = Field(min_length=1, max_length=128)


class TokenOut(_Out):
    access_token: str
    expires_at: datetime
    role: str


class TransactionOut(_Out):
    id: str
    recipient_name: str
    amount: int
    currency: str
    note: str
    timestamp: datetime


class MeOut(_Out):
    id: str
    display_name: str
    balance: int
    currency: str = "INR"
    recent_transactions: list[TransactionOut]


class RecipientOut(_Out):
    id: str
    display_name: str
    handle: str


class RecipientLookupOut(_Out):
    found: bool
    recipient: RecipientOut | None = None


class ComponentStatus(_Out):
    status: str


class HealthOut(_Out):
    status: str
    firestore: ComponentStatus
    neo4j: ComponentStatus
    model: ComponentStatus


class InvestigatorSessionOut(_Out):
    role: str
