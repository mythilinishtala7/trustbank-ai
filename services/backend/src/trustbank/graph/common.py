"""Shared helpers for ingestion and queries."""

from datetime import datetime

from neo4j import Driver, GraphDatabase

from trustbank.config import Settings
from trustbank.domain import Provenance

FACT = Provenance.VERIFIED_SYNTHETIC.value


def build_driver(settings: Settings) -> Driver:
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        connection_timeout=5,
        notifications_min_severity="OFF",
        connection_acquisition_timeout=10,
    )


def plain_datetime(value: datetime) -> datetime:
    """Firestore returns a datetime subclass the Neo4j driver cannot encode."""
    return datetime.fromisoformat(value.isoformat())
