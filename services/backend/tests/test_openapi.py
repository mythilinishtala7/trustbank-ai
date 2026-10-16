import json
from pathlib import Path

from trustbank.openapi_export import build_openapi


def test_committed_openapi_is_current() -> None:
    committed = json.loads(Path(__file__).parents[1].joinpath("openapi.json").read_text())
    assert committed == json.loads(json.dumps(build_openapi())), (
        "run: python -m trustbank.openapi_export > openapi.json"
    )
