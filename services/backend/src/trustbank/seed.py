"""Seed command: python -m trustbank.seed [--reset]"""

import argparse
from datetime import UTC, datetime

from google.cloud import firestore

from trustbank.config import get_settings
from trustbank.fixtures import build_dataset
from trustbank.store import DatasetRepository, create_client


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed the synthetic dataset into Firestore.")
    parser.add_argument("--reset", action="store_true", help="delete existing dataset first")
    parser.add_argument(
        "--remote", metavar="PROJECT_ID", help="seed real Firestore in this project"
    )
    parser.add_argument("--yes", action="store_true", help="skip the remote confirmation prompt")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.remote:
        if settings.firestore_emulator_host:
            raise SystemExit("Unset TRUSTBANK_FIRESTORE_EMULATOR_HOST to seed real Firestore.")
        if not args.yes and input(f"Write to REAL Firestore in '{args.remote}'? [y/N] ") != "y":
            raise SystemExit("aborted")
        client = firestore.Client(project=args.remote)
    else:
        if not settings.firestore_emulator_host:
            raise SystemExit(
                "Set TRUSTBANK_FIRESTORE_EMULATOR_HOST to seed the emulator, "
                "or pass --remote PROJECT_ID to seed real Firestore."
            )
        client = create_client(settings)
    repo = DatasetRepository(client)
    if args.reset:
        repo.reset()
        print("reset: dataset collections cleared")
    counts = repo.seed(build_dataset(datetime.now(UTC)))
    for name, n in counts.items():
        print(f"{name}: {n}")


if __name__ == "__main__":
    main()
