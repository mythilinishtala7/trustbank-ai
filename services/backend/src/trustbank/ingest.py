"""Project Firestore data into Neo4j: python -m trustbank.ingest [--reset]"""

import argparse

from trustbank.config import get_settings
from trustbank.graph import GraphStore, create_driver
from trustbank.store import DatasetRepository, create_client


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Load the knowledge graph from Firestore.")
    parser.add_argument("--reset", action="store_true", help="delete all graph data first")
    parser.add_argument("--remote-firestore", metavar="PROJECT_ID", help="read real Firestore")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.remote_firestore:
        from google.cloud import firestore

        client = firestore.Client(project=args.remote_firestore)
    else:
        client = create_client(settings)
    dataset = DatasetRepository(client).load()
    if not dataset.transactions:
        raise SystemExit("Firestore has no dataset; run `python -m trustbank.seed` first.")

    driver = create_driver(settings)
    try:
        graph = GraphStore(driver)
        if args.reset:
            graph.reset()
            print("reset: graph cleared")
        graph.ingest(dataset)
        problems = graph.verify(dataset)
    finally:
        driver.close()
    if problems:
        raise SystemExit("Integrity problems:\n" + "\n".join(problems))
    print(
        f"ingested: {len(dataset.customers)} customers, "
        f"{len(dataset.beneficiaries)} beneficiaries, "
        f"{len(dataset.accounts)} accounts, {len(dataset.transactions)} transactions, "
        f"{len(dataset.connections)} connections; integrity OK"
    )


if __name__ == "__main__":
    main()
