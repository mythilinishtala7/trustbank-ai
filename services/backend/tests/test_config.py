import pytest

from trustbank.config import Settings
from trustbank.main import create_app


def make(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[arg-type]


def test_missing_secrets_refuse_to_start() -> None:
    with pytest.raises(RuntimeError, match="TRUSTBANK_TOKEN_SECRET"):
        create_app(make(environment="local"))


@pytest.mark.parametrize(
    ("secret", "code"),
    [
        ("change-me-" + "x" * 40, "real-code"),
        ("short", "real-code"),
        ("s" * 40, "change-me-please"),
    ],
)
def test_deployed_rejects_placeholders(secret: str, code: str) -> None:
    settings = make(environment="deployed", token_secret=secret, investigator_code=code)
    with pytest.raises(RuntimeError):
        settings.validate_for_serving()


def test_deployed_accepts_real_values() -> None:
    make(
        environment="deployed", token_secret="s" * 40, investigator_code="a-real-code"
    ).validate_for_serving()


def test_secrets_are_not_in_repr() -> None:
    settings = make(environment="local", token_secret="s" * 40, investigator_code="open-code")
    assert "open-code" not in repr(settings) and "s" * 40 not in repr(settings)


def test_threshold_ordering_validated() -> None:
    with pytest.raises(ValueError):
        make(environment="test", elevated_threshold=70, high_threshold=60)
