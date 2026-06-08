from __future__ import annotations

from typing import Any, Literal

from neo4j.graph import Node, Path, Relationship

from app.core.neo4j_client import neo4j_session


Direction = Literal["both", "outgoing", "incoming"]

MAX_LIMIT = 500
MAX_DEPTH = 5


class GraphRepository:
    """Controlled Neo4j graph queries used by higher-level services."""

    def get_overview(self) -> dict[str, Any]:
        with neo4j_session() as session:
            total_nodes = session.run("MATCH (n) RETURN count(n) AS count").single()["count"]
            total_relationships = session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"]
            node_labels = [
                {"name": record["name"], "count": record["count"]}
                for record in session.run(
                    """
                    MATCH (n)
                    UNWIND labels(n) AS name
                    RETURN name, count(*) AS count
                    ORDER BY count DESC, name
                    """
                )
            ]
            relationship_types = [
                {"name": record["name"], "count": record["count"]}
                for record in session.run(
                    """
                    MATCH ()-[r]->()
                    RETURN type(r) AS name, count(*) AS count
                    ORDER BY count DESC, name
                    """
                )
            ]
        return {
            "total_nodes": total_nodes,
            "total_relationships": total_relationships,
            "node_labels": node_labels,
            "relationship_types": relationship_types,
        }

    def create_node(
        self,
        *,
        labels: list[str],
        properties: dict[str, Any],
        embedding_property: str | None = None,
        embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        label_clause = "".join(f":{escape_identifier(label)}" for label in self._clean_names(labels))
        embedding_set = ""
        params: dict[str, Any] = {"properties": clean_property_values(properties)}
        if embedding_property and embedding is not None:
            embedding_set = f"SET n.{escape_identifier(embedding_property)} = $embedding"
            params["embedding"] = embedding
        query = f"""
        CREATE (n{label_clause})
        SET n = $properties
        {embedding_set}
        RETURN n
        """
        with neo4j_session() as session:
            record = session.run(query, params).single()
            return serialize_node(record["n"])

    def create_relationship(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        relationship_type: str,
        properties: dict[str, Any],
        embedding_property: str | None = None,
        embedding: list[float] | None = None,
    ) -> dict[str, Any] | None:
        checked_relationship_type = self._clean_names([relationship_type])[0]
        embedding_set = ""
        params: dict[str, Any] = {
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "properties": clean_property_values(properties),
        }
        if embedding_property and embedding is not None:
            embedding_set = f"SET r.{escape_identifier(embedding_property)} = $embedding"
            params["embedding"] = embedding
        query = f"""
        MATCH (source), (target)
        WHERE elementId(source) = $source_node_id
          AND elementId(target) = $target_node_id
        CREATE (source)-[r:{escape_identifier(checked_relationship_type)}]->(target)
        SET r = $properties
        {embedding_set}
        RETURN source, target, r
        """
        with neo4j_session() as session:
            record = session.run(query, params).single()
            if record is None:
                return None
            return {
                "nodes": [serialize_node(record["source"]), serialize_node(record["target"])],
                "relationships": [serialize_relationship(record["r"])],
            }

    def find_exact_nodes(
        self,
        name: str,
        *,
        labels: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = f"""
        MATCH (n)
        WHERE {exact_name_predicate("n", "$name")}
          AND ($labels = [] OR any(label IN labels(n) WHERE label IN $labels))
        RETURN n
        ORDER BY coalesce(toString(n.name), toString(n.symbol), toString(n.id), elementId(n))
        LIMIT $limit
        """
        params = {
            "name": name.strip(),
            "labels": self._clean_names(labels or []),
            "limit": self._clamp_limit(limit),
        }
        with neo4j_session() as session:
            records = session.run(query, params)
            return [serialize_node(record["n"]) for record in records]

    def search_nodes(
        self,
        keyword: str,
        *,
        labels: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query = """
        MATCH (n)
        WHERE ($labels = [] OR any(label IN labels(n) WHERE label IN $labels))
          AND (
            any(value IN [
              n.name,
              n.title,
              n.symbol,
              n.id,
              n.vid,
              n.gene_full_name,
              n.alias,
              n.synonym,
              n.description,
              n.type
            ] WHERE value IS NOT NULL AND toLower(toString(value)) CONTAINS toLower($keyword))
            OR any(value IN coalesce(n.aliases, []) + coalesce(n.synonyms, [])
              WHERE value IS NOT NULL AND toLower(toString(value)) CONTAINS toLower($keyword))
          )
        RETURN n
        ORDER BY
          CASE
            WHEN toLower(coalesce(toString(n.name), '')) = toLower($keyword) THEN 0
            WHEN toLower(coalesce(toString(n.symbol), '')) = toLower($keyword) THEN 1
            ELSE 2
          END,
          coalesce(toString(n.name), toString(n.symbol), toString(n.id), elementId(n))
        LIMIT $limit
        """
        params = {
            "keyword": keyword.strip(),
            "labels": self._clean_names(labels or []),
            "limit": self._clamp_limit(limit),
        }
        with neo4j_session() as session:
            records = session.run(query, params)
            return [serialize_node(record["n"]) for record in records]

    def vector_search_nodes(
        self,
        *,
        index_name: str,
        query_embedding: list[float],
        labels: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        checked_labels = self._clean_names(labels or [])
        checked_top_k = self._clamp_limit(top_k)
        candidate_count = checked_top_k if not checked_labels else min(MAX_LIMIT, max(checked_top_k * 20, 100))
        query = """
        CALL db.index.vector.queryNodes($index_name, $candidate_count, $query_embedding)
        YIELD node, score
        WHERE $labels = [] OR any(label IN labels(node) WHERE label IN $labels)
        RETURN node, score
        ORDER BY score DESC
        LIMIT $top_k
        """
        params = {
            "index_name": index_name,
            "candidate_count": candidate_count,
            "query_embedding": query_embedding,
            "labels": checked_labels,
            "top_k": checked_top_k,
        }
        with neo4j_session() as session:
            records = session.run(query, params)
            results = []
            for record in records:
                node = serialize_node(record["node"])
                node["score"] = float(record["score"])
                results.append(node)
            return results

    def get_node_detail(self, node_id: str) -> dict[str, Any] | None:
        query = """
        MATCH (n)
        WHERE elementId(n) = $node_id
        RETURN n
        LIMIT 1
        """
        with neo4j_session() as session:
            record = session.run(query, {"node_id": node_id}).single()
            if record is None:
                return None
            return serialize_node(record["n"])

    def update_node_properties(self, node_id: str, properties: dict[str, Any]) -> dict[str, Any] | None:
        query = """
        MATCH (n)
        WHERE elementId(n) = $node_id
        SET n += $properties
        RETURN n
        LIMIT 1
        """
        with neo4j_session() as session:
            record = session.run(query, {"node_id": node_id, "properties": properties}).single()
            if record is None:
                return None
            return serialize_node(record["n"])

    def delete_node(self, node_id: str, *, detach: bool = False) -> bool:
        delete_clause = "DETACH DELETE n" if detach else "DELETE n"
        query = f"""
        MATCH (n)
        WHERE elementId(n) = $node_id
        WITH n, elementId(n) AS deleted_id
        {delete_clause}
        RETURN deleted_id
        """
        with neo4j_session() as session:
            record = session.run(query, {"node_id": node_id}).single()
            return record is not None

    def get_neighbors(
        self,
        node_id: str,
        *,
        depth: int = 1,
        direction: Direction = "both",
        relationship_types: list[str] | None = None,
        limit: int = 100,
    ) -> dict[str, list[dict[str, Any]]]:
        checked_depth = self._clamp_depth(depth)
        checked_limit = self._clamp_limit(limit)
        checked_direction = self._validate_direction(direction)
        checked_relationship_types = self._clean_names(relationship_types or [])

        pattern = {
            "both": f"(n)-[*1..{checked_depth}]-(m)",
            "outgoing": f"(n)-[*1..{checked_depth}]->(m)",
            "incoming": f"(n)<-[*1..{checked_depth}]-(m)",
        }[checked_direction]
        query = f"""
        MATCH path = {pattern}
        WHERE elementId(n) = $node_id
          AND (
            $relationship_types = []
            OR all(rel IN relationships(path) WHERE type(rel) IN $relationship_types)
          )
        RETURN path
        LIMIT $limit
        """
        params = {
            "node_id": node_id,
            "relationship_types": checked_relationship_types,
            "limit": checked_limit,
        }
        with neo4j_session() as session:
            records = session.run(query, params)
            return collect_graph(record["path"] for record in records)

    def get_neighborhood_by_node_id(
        self,
        node_id: str,
        *,
        depth: int = 1,
        direction: Direction = "both",
        relationship_types: list[str] | None = None,
        limit: int = 100,
    ) -> dict[str, list[dict[str, Any]]]:
        checked_depth = self._clamp_depth(depth)
        checked_limit = self._clamp_limit(limit)
        checked_direction = self._validate_direction(direction)
        checked_relationship_types = self._clean_names(relationship_types or [])
        pattern = {
            "both": f"(n)-[*1..{checked_depth}]-(m)",
            "outgoing": f"(n)-[*1..{checked_depth}]->(m)",
            "incoming": f"(n)<-[*1..{checked_depth}]-(m)",
        }[checked_direction]
        query = f"""
        MATCH path = {pattern}
        WHERE elementId(n) = $node_id
          AND (
            $relationship_types = []
            OR all(rel IN relationships(path) WHERE type(rel) IN $relationship_types)
          )
        RETURN path
        LIMIT $limit
        """
        params = {
            "node_id": node_id,
            "relationship_types": checked_relationship_types,
            "limit": checked_limit,
        }
        with neo4j_session() as session:
            records = session.run(query, params)
            return collect_graph(record["path"] for record in records)

    def get_neighborhood_by_exact_name(
        self,
        name: str,
        *,
        labels: list[str] | None = None,
        depth: int = 1,
        direction: Direction = "both",
        relationship_types: list[str] | None = None,
        limit: int = 100,
    ) -> dict[str, list[dict[str, Any]]]:
        checked_depth = self._clamp_depth(depth)
        checked_limit = self._clamp_limit(limit)
        checked_direction = self._validate_direction(direction)
        checked_labels = self._clean_names(labels or [])
        checked_relationship_types = self._clean_names(relationship_types or [])
        pattern = {
            "both": f"(n)-[*1..{checked_depth}]-(m)",
            "outgoing": f"(n)-[*1..{checked_depth}]->(m)",
            "incoming": f"(n)<-[*1..{checked_depth}]-(m)",
        }[checked_direction]
        query = f"""
        MATCH path = {pattern}
        WHERE {exact_name_predicate("n", "$name")}
          AND ($labels = [] OR any(label IN labels(n) WHERE label IN $labels))
          AND (
            $relationship_types = []
            OR all(rel IN relationships(path) WHERE type(rel) IN $relationship_types)
          )
        RETURN path
        LIMIT $limit
        """
        params = {
            "name": name.strip(),
            "labels": checked_labels,
            "relationship_types": checked_relationship_types,
            "limit": checked_limit,
        }
        with neo4j_session() as session:
            records = session.run(query, params)
            return collect_graph(record["path"] for record in records)

    def find_related_by_relationship(
        self,
        name: str,
        relationship_type: str,
        *,
        labels: list[str] | None = None,
        target_labels: list[str] | None = None,
        direction: Direction = "both",
        limit: int = 100,
    ) -> dict[str, list[dict[str, Any]]]:
        checked_direction = self._validate_direction(direction)
        checked_labels = self._clean_names(labels or [])
        checked_target_labels = self._clean_names(target_labels or [])
        checked_relationship_type = self._clean_names([relationship_type])[0]
        pattern = {
            "both": "(n)-[r]-(m)",
            "outgoing": "(n)-[r]->(m)",
            "incoming": "(n)<-[r]-(m)",
        }[checked_direction]
        query = f"""
        MATCH path = {pattern}
        WHERE {exact_name_predicate("n", "$name")}
          AND type(r) = $relationship_type
          AND ($labels = [] OR any(label IN labels(n) WHERE label IN $labels))
          AND ($target_labels = [] OR any(label IN labels(m) WHERE label IN $target_labels))
        RETURN path
        LIMIT $limit
        """
        params = {
            "name": name.strip(),
            "relationship_type": checked_relationship_type,
            "labels": checked_labels,
            "target_labels": checked_target_labels,
            "limit": self._clamp_limit(limit),
        }
        with neo4j_session() as session:
            records = session.run(query, params)
            return collect_graph(record["path"] for record in records)

    def find_direct_relationships_by_names(
        self,
        source_name: str,
        target_name: str,
        *,
        source_labels: list[str] | None = None,
        target_labels: list[str] | None = None,
        relationship_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query = f"""
        MATCH path = (source)-[r]-(target)
        WHERE {exact_name_predicate("source", "$source_name")}
          AND {exact_name_predicate("target", "$target_name")}
          AND ($source_labels = [] OR any(label IN labels(source) WHERE label IN $source_labels))
          AND ($target_labels = [] OR any(label IN labels(target) WHERE label IN $target_labels))
          AND ($relationship_types = [] OR type(r) IN $relationship_types)
        RETURN path
        LIMIT $limit
        """
        params = {
            "source_name": source_name.strip(),
            "target_name": target_name.strip(),
            "source_labels": self._clean_names(source_labels or []),
            "target_labels": self._clean_names(target_labels or []),
            "relationship_types": self._clean_names(relationship_types or []),
            "limit": self._clamp_limit(limit),
        }
        with neo4j_session() as session:
            records = session.run(query, params)
            return [serialize_path(record["path"]) for record in records]

    def find_paths(
        self,
        source_node_id: str,
        target_node_id: str,
        *,
        max_depth: int = 3,
        relationship_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        checked_depth = self._clamp_depth(max_depth)
        checked_limit = self._clamp_limit(limit)
        checked_relationship_types = self._clean_names(relationship_types or [])
        query = f"""
        MATCH path = (source)-[*1..{checked_depth}]-(target)
        WHERE elementId(source) = $source_node_id
          AND elementId(target) = $target_node_id
          AND (
            $relationship_types = []
            OR all(rel IN relationships(path) WHERE type(rel) IN $relationship_types)
          )
        RETURN path
        ORDER BY length(path)
        LIMIT $limit
        """
        params = {
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "relationship_types": checked_relationship_types,
            "limit": checked_limit,
        }
        with neo4j_session() as session:
            records = session.run(query, params)
            return [serialize_path(record["path"]) for record in records]

    def _clamp_limit(self, limit: int) -> int:
        return max(1, min(limit, MAX_LIMIT))

    def _clamp_depth(self, depth: int) -> int:
        return max(1, min(depth, MAX_DEPTH))

    def _validate_direction(self, direction: str) -> Direction:
        if direction not in {"both", "outgoing", "incoming"}:
            raise ValueError("direction must be one of: both, outgoing, incoming")
        return direction

    def _clean_names(self, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            item = value.strip()
            if not item:
                continue
            if any(char in item for char in "\r\n\t\0"):
                raise ValueError(f"Invalid Neo4j name: {item}")
            cleaned.append(item)
        return cleaned


def exact_name_predicate(variable: str, parameter: str) -> str:
    return f"""
        (
            any(value IN [
                {variable}.name,
                {variable}.title,
                {variable}.symbol,
                {variable}.id,
                {variable}.vid,
                {variable}.gene_full_name,
                {variable}.alias,
                {variable}.synonym
            ] WHERE value IS NOT NULL AND toLower(toString(value)) = toLower({parameter}))
            OR any(value IN coalesce({variable}.aliases, []) + coalesce({variable}.synonyms, [])
                WHERE value IS NOT NULL AND toLower(toString(value)) = toLower({parameter}))
        )
    """


def escape_identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"


def clean_property_values(properties: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in properties.items() if value is not None}


def serialize_node(node: Node) -> dict[str, Any]:
    return {
        "id": node.element_id,
        "labels": sorted(node.labels),
        "properties": dict(node.items()),
    }


def serialize_relationship(relationship: Relationship) -> dict[str, Any]:
    return {
        "id": relationship.element_id,
        "type": relationship.type,
        "source_id": relationship.start_node.element_id,
        "target_id": relationship.end_node.element_id,
        "properties": dict(relationship.items()),
    }


def serialize_path(path: Path) -> dict[str, Any]:
    return {
        "nodes": [serialize_node(node) for node in path.nodes],
        "relationships": [serialize_relationship(relationship) for relationship in path.relationships],
        "length": len(path.relationships),
    }


def collect_graph(paths: Any) -> dict[str, list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    relationships: dict[str, dict[str, Any]] = {}
    for path in paths:
        for node in path.nodes:
            nodes[node.element_id] = serialize_node(node)
        for relationship in path.relationships:
            relationships[relationship.element_id] = serialize_relationship(relationship)
    return {
        "nodes": list(nodes.values()),
        "relationships": list(relationships.values()),
    }
