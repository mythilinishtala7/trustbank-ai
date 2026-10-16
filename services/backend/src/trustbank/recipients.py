"""Resolve a UPI id or 9-18 digit account number to a known beneficiary (or an unverified payee)."""

import hashlib
import re
from dataclasses import dataclass

from trustbank.domain import Account, Beneficiary
from trustbank.errors import validation_error
from trustbank.store import DatasetRepository

_UPI = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}@[a-z][a-z0-9]{1,31}$")
_ACCOUNT = re.compile(r"^\d{9,18}$")
_SUFFIX_LEN = 4  # accounts store only a masked number, so the tail is all that can be matched


@dataclass(frozen=True)
class Resolved:
    handle: str  # normalized input, or the beneficiary's handle when known
    beneficiary: Beneficiary | None
    account: Account | None
    beneficiary_id: str

    @property
    def verified(self) -> bool:
        return self.beneficiary is not None


def normalize(query: str) -> str:
    q = query.strip()
    if _ACCOUNT.match(q):
        return q
    q = q.lower()
    if _UPI.match(q):
        return q
    raise validation_error("Enter a UPI id (name@bank) or a 9 to 18 digit account number.")


UNVERIFIED_PREFIX = "ben_ext_"


def unknown_beneficiary_id(normalized: str) -> str:
    return UNVERIFIED_PREFIX + hashlib.sha256(normalized.encode()).hexdigest()[:10]


def resolve(repo: DatasetRepository, query: str) -> Resolved:
    q = normalize(query)
    beneficiary: Beneficiary | None
    account: Account | None = None
    if _ACCOUNT.match(q):
        matches = repo.beneficiaries_by_account_suffix(q[-_SUFFIX_LEN:])
        beneficiary, account = matches[0] if len(matches) == 1 else (None, None)
    else:
        beneficiary = repo.beneficiary_by_handle(q)
        account = repo.account_for_owner(beneficiary.id) if beneficiary else None
    if beneficiary is not None and beneficiary.id.startswith(UNVERIFIED_PREFIX):
        beneficiary, account = (
            None,
            None,
        )  # created by an earlier completed payment, still unverified
    if beneficiary is None:
        return Resolved(
            handle=q, beneficiary=None, account=None, beneficiary_id=unknown_beneficiary_id(q)
        )
    return Resolved(
        handle=beneficiary.handle,
        beneficiary=beneficiary,
        account=account,
        beneficiary_id=beneficiary.id,
    )
