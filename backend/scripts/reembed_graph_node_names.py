from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.neo4j_client import neo4j_session  # noqa: E402
from app.services.embedding_client import EmbeddingClient  # noqa: E402
from app.services.semantic_retrieval import load_semantic_retrieval_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewrite KGNode embeddings using node name only.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum nodes to process. Default processes all.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_semantic_retrieval_config()
    if not config.embedding.enabled:
        raise SystemExit("Embedding is disabled in configuration.")

    nodes = load_nodes(args.limit)
    print(f"Nodes with names: {len(nodes)}")
    print(f"Embedding model: {config.embedding.model}")
    print(f"Embedding dimensions: {config.embedding.dimensions}")
    print(f"Embedding property: {config.embedding.node_property}")
    if args.dry_run:
        print("Dry run only. Re-run without --dry-run to write embeddings.")
        return

    client = EmbeddingClient(config.embedding)
    updated = 0
    for batch in chunks(nodes, config.embedding.batch_size):
        texts = [node["name"] for node in batch]
        vectors = client.embed_texts(texts)
        rows = [
            {"element_id": node["element_id"], "embedding": vector}
            for node, vector in zip(batch, vectors, strict=True)
        ]
        write_embeddings(rows, config.embedding.node_property)
        updated += len(rows)
        print(f"Updated {updated}/{len(nodes)}")
    print("Re-embedding complete.")


def load_nodes(limit: int) -> list[dict[str, str]]:
    limit_clause = "LIMIT $limit" if limit > 0 else ""
    query = f"""
    MATCH (n:KGNode)
    WHERE n.name IS NOT NULL AND trim(toString(n.name)) <> ''
    RETURN elementId(n) AS element_id, toString(n.name) AS name
    ORDER BY elementId(n)
    {limit_clause}
    """
    params = {"limit": limit}
    with neo4j_session() as session:
        return [dict(record) for record in session.run(query, params)]


def write_embeddings(rows: list[dict], property_name: str) -> None:
    query = f"""
    UNWIND $rows AS row
    MATCH (n)
    WHERE elementId(n) = row.element_id
    SET n.`{property_name.replace('`', '``')}` = row.embedding
    """
    with neo4j_session("WRITE") as session:
        session.run(query, {"rows": rows}).consume()


def chunks(items: list, size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


if __name__ == "__main__":
    main()
