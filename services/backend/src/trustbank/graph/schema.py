"""Graph schema constants and constraints (specs/knowledge-graph)."""

from typing import Final

NODE_LABELS: Final = ("Customer", "Account", "Transaction", "Beneficiary", "RiskSignal")
REL_TYPES: Final = ("OWNS", "SENT", "PAID", "CONNECTED_TO", "FLAGGED_FOR")

CONSTRAINTS: Final = (
    *(
        f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
        for label in NODE_LABELS
    ),
    *(
        f"CREATE CONSTRAINT {rel.lower()}_rel_id IF NOT EXISTS "
        f"FOR ()-[r:{rel}]-() REQUIRE r.id IS UNIQUE"
        for rel in REL_TYPES
    ),
)
