"""Print the OpenAPI document: `python -m trustbank.openapi_export > openapi.json`.

Builds the app with inert collaborators so no Firestore, Neo4j or model access is needed.
"""

import json
import sys
from typing import Any, cast

from trustbank.config import Settings
from trustbank.contracts import Orchestrator
from trustbank.graph import GraphService
from trustbank.main import create_app


class _Inert:
    """Stands in for the orchestrator and graph; the schema never calls them."""

    model_name = "none"

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"{name} is unavailable in schema export")


def build_openapi() -> dict[str, Any]:
    settings = Settings(
        _env_file=None,
        environment="test",
        firestore_emulator_host="127.0.0.1:1",
    )
    app = create_app(
        settings, orchestrator=cast(Orchestrator, _Inert()), graph=cast(GraphService, _Inert())
    )
    return app.openapi()


def main() -> None:
    json.dump(build_openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
