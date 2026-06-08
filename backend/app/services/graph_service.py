from __future__ import annotations

import re
from typing import Any

from app.core.neo4j_client import verify_neo4j_connectivity
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import (
    GraphData,
    GraphLLMTextResponse,
    GraphOverviewResponse,
    GraphNode,
    GraphPath,
    GraphQueryResponse,
    GraphRelationship,
    NeighborQueryRequest,
    NodeCreateRequest,
    NodeCreateResponse,
    NodeDeleteRequest,
    NodeDeleteResponse,
    NodeDetailRequest,
    NodeSearchRequest,
    NodeUpdateRequest,
    NodeUpdateResponse,
    PathQueryRequest,
    RelationshipCreateRequest,
    RelationshipCreateResponse,
    RelationshipQueryRequest,
)
from app.services.embedding_client import EmbeddingClient, EmbeddingProvider
from app.services.rerank_client import RerankClient, RerankProvider
from app.services.semantic_retrieval import SemanticRetrievalConfig, load_semantic_retrieval_config


class GraphService:
    def __init__(
        self,
        repository: GraphRepository | None = None,
        embedding_client: EmbeddingProvider | None = None,
        rerank_client: RerankProvider | None = None,
        semantic_config: SemanticRetrievalConfig | None = None,
    ):
        self.repository = repository or GraphRepository()
        self.semantic_config = semantic_config or load_semantic_retrieval_config()
        self.embedding_client = embedding_client or EmbeddingClient(self.semantic_config.embedding)
        self.rerank_client = rerank_client or RerankClient(self.semantic_config.rerank)

    def check_health(self) -> None:
        verify_neo4j_connectivity()

    def get_overview(self) -> GraphOverviewResponse:
        return GraphOverviewResponse(**self.repository.get_overview())

    def search_exact_node(self, request: NodeSearchRequest) -> GraphQueryResponse | GraphLLMTextResponse:
        if request.vector_search:
            return self.search_vector_node(request)

        names = request_names(request.name)
        matched = self._find_exact_nodes(names, request.labels, request.limit)
        graph = {"nodes": matched, "relationships": []}
        if request.depth > 0:
            graph = self._get_neighborhoods_by_exact_names(
                names,
                labels=request.labels,
                depth=request.depth,
                direction=request.direction,
                relationship_types=request.relationship_types,
                limit=request.limit,
            )
            graph["nodes"] = merge_nodes(matched, graph["nodes"])

        if request.llm_text:
            return self._llm_text_response(graph["nodes"], graph["relationships"])

        return self._graph_response(
            query=request.name,
            matched_nodes=matched,
            nodes=graph["nodes"],
            relationships=graph["relationships"],
            include_properties=request.include_properties,
            warnings=[] if matched else [f"No exact node found for name: {format_query(request.name)}"],
        )

    def search_vector_node(self, request: NodeSearchRequest) -> GraphQueryResponse | GraphLLMTextResponse:
        names = request_names(request.name)
        matched = self._find_vector_nodes(
            names,
            request.labels,
            top_k=request.top_k,
            rerank=request.rerank,
            vector_top_k=request.vector_top_k,
            rerank_top_n=request.rerank_top_n,
        )
        graph = {"nodes": matched, "relationships": []}
        if request.depth > 0:
            graph = self._get_neighborhoods_by_node_ids(
                [str(node["id"]) for node in matched],
                depth=request.depth,
                direction=request.direction,
                relationship_types=request.relationship_types,
                limit=request.limit,
            )
            graph["nodes"] = merge_nodes(matched, graph["nodes"])

        if request.llm_text:
            return self._llm_text_response(graph["nodes"], graph["relationships"])

        return self._graph_response(
            query=request.name,
            matched_nodes=matched,
            nodes=graph["nodes"],
            relationships=graph["relationships"],
            include_properties=request.include_properties,
            warnings=[] if matched else [f"No vector node candidates found for query: {format_query(request.name)}"],
        )

    def _llm_text_response(
        self,
        nodes: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> GraphLLMTextResponse:
        deduped_nodes = dedupe_by_id(nodes)
        node_map = {str(node["id"]): node_display_name(node) for node in deduped_nodes}

        entity_items: list[str] = []
        entity_seen: set[str] = set()
        for node in deduped_nodes:
            append_unique(entity_items, entity_seen, node_display_name(node))

        relationship_groups: dict[str, list[str]] = {}
        relationship_seen: set[str] = set()
        for relationship in dedupe_by_id(relationships):
            source_id = str(relationship.get("source_id", ""))
            target_id = str(relationship.get("target_id", ""))
            source = node_map.get(source_id) or source_id
            target = node_map.get(target_id) or target_id
            relation = relationship_type_name(relationship)

            append_unique(entity_items, entity_seen, source)
            append_unique(entity_items, entity_seen, target)
            edge = f"{source}->{target}"
            dedupe_key = f"{relation}\t{edge}"
            if dedupe_key not in relationship_seen:
                relationship_seen.add(dedupe_key)
                relationship_groups.setdefault(relation, []).append(edge)

        return GraphLLMTextResponse(
            entities="\n".join(entity_items),
            relationships="\n".join(f"{relation}:[{';'.join(edges)}]" for relation, edges in relationship_groups.items()),
        )

    def get_exact_node_detail(self, request: NodeDetailRequest) -> GraphQueryResponse:
        matched = self._find_exact_nodes(request_names(request.name), request.labels, request.limit)
        return self._graph_response(
            query=request.name,
            matched_nodes=matched,
            nodes=matched,
            relationships=[],
            include_properties=request.include_properties,
            warnings=[] if matched else [f"No exact node found for name: {format_query(request.name)}"],
        )

    def create_node(self, request: NodeCreateRequest) -> NodeCreateResponse:
        embedding = self._embed_text(build_node_embedding_text(request.labels, request.properties, request.embedding_text), request.embed)
        node = self.repository.create_node(
            labels=request.labels,
            properties=request.properties,
            embedding_property=self.semantic_config.embedding.node_property,
            embedding=embedding,
        )
        return NodeCreateResponse(
            node=format_node(node, request.include_properties),
            embedding_written=embedding is not None,
        )

    def create_relationship(self, request: RelationshipCreateRequest) -> RelationshipCreateResponse:
        source_node = self.repository.get_node_detail(request.source_node_id)
        target_node = self.repository.get_node_detail(request.target_node_id)
        if source_node is None:
            raise LookupError(f"Source node not found: {request.source_node_id}")
        if target_node is None:
            raise LookupError(f"Target node not found: {request.target_node_id}")

        embedding = self._embed_text(
            build_relationship_embedding_text(
                source_node,
                target_node,
                request.relationship_type,
                request.properties,
                request.embedding_text,
            ),
            request.embed,
        )
        graph = self.repository.create_relationship(
            source_node_id=request.source_node_id,
            target_node_id=request.target_node_id,
            relationship_type=request.relationship_type,
            properties=request.properties,
            embedding_property=self.semantic_config.embedding.relationship_property,
            embedding=embedding,
        )
        if graph is None:
            raise LookupError("Source or target node not found")
        nodes = [format_node(node, request.include_properties) for node in graph["nodes"]]
        node_map = {node.id: node.name for node in nodes}
        relationship = format_relationship(graph["relationships"][0], node_map, request.include_properties)
        return RelationshipCreateResponse(
            relationship=relationship,
            embedding_written=embedding is not None,
        )

    def update_node(self, request: NodeUpdateRequest) -> NodeUpdateResponse:
        properties = dict(request.properties)
        for key in request.remove_properties:
            properties[key] = None
        node = self.repository.update_node_properties(request.node_id, properties)
        if node is None:
            raise LookupError(f"Node not found: {request.node_id}")
        return NodeUpdateResponse(node=format_node(node, request.include_properties))

    def delete_node(self, request: NodeDeleteRequest) -> NodeDeleteResponse:
        deleted = self.repository.delete_node(request.node_id, detach=request.detach)
        if not deleted:
            raise LookupError(f"Node not found: {request.node_id}")
        return NodeDeleteResponse(deleted=True, node_id=request.node_id, detached=request.detach)

    def _embed_text(self, text: str, enabled_for_request: bool) -> list[float] | None:
        if not enabled_for_request:
            return None
        return self.embedding_client.embed_text(text)

    def get_neighbors(self, request: NeighborQueryRequest) -> GraphQueryResponse:
        names = request_names(request.name)
        matched = self._find_exact_nodes(names, request.labels, request.limit)
        graph = self._get_neighborhoods_by_exact_names(
            names,
            labels=request.labels,
            depth=request.depth,
            direction=request.direction,
            relationship_types=request.relationship_types,
            limit=request.limit,
        )
        nodes = merge_nodes(matched, graph["nodes"])
        warnings = []
        if not matched:
            warnings.append(f"No exact node found for name: {format_query(request.name)}")
        elif not graph["relationships"]:
            warnings.append(
                f"No relationships found within depth {request.depth} for name: {format_query(request.name)}"
            )
        return self._graph_response(
            query=request.name,
            matched_nodes=matched,
            nodes=nodes,
            relationships=graph["relationships"],
            include_properties=request.include_properties,
            warnings=warnings,
        )

    def get_related_by_relationship(self, request: RelationshipQueryRequest) -> GraphQueryResponse:
        graph = self._find_related_by_relationships(
            request_names(request.name),
            request.relationship_type,
            labels=request.labels,
            target_labels=request.target_labels,
            direction=request.direction,
            limit=request.limit,
        )
        warnings = []
        if not graph["relationships"]:
            warnings.append(
                f"No {request.relationship_type} relationships found for exact node name: {format_query(request.name)}"
            )
        return self._graph_response(
            query=request.name,
            nodes=graph["nodes"],
            relationships=graph["relationships"],
            include_properties=request.include_properties,
            warnings=warnings,
        )

    def check_direct_relationship_or_neighborhood(self, request: PathQueryRequest) -> GraphQueryResponse:
        paths = self.repository.find_direct_relationships_by_names(
            request.source_name,
            request.target_name,
            source_labels=request.source_labels,
            target_labels=request.target_labels,
            relationship_types=request.relationship_types,
            limit=request.limit,
        )
        if paths:
            graph = graph_from_paths(paths)
            return self._graph_response(
                query=f"{request.source_name} -> {request.target_name}",
                nodes=graph["nodes"],
                relationships=graph["relationships"],
                paths=paths,
                include_properties=request.include_properties,
                direct_relationship_found=True,
            )

        source_graph = self.repository.get_neighborhood_by_exact_name(
            request.source_name,
            labels=request.source_labels,
            depth=request.fallback_depth,
            relationship_types=request.relationship_types,
            limit=request.limit,
        )
        target_graph = self.repository.get_neighborhood_by_exact_name(
            request.target_name,
            labels=request.target_labels,
            depth=request.fallback_depth,
            relationship_types=request.relationship_types,
            limit=request.limit,
        )
        return GraphQueryResponse(
            query=f"{request.source_name} -> {request.target_name}",
            direct_relationship_found=False,
            source_neighborhood=self._graph_data(source_graph, request.include_properties),
            target_neighborhood=self._graph_data(target_graph, request.include_properties),
            warnings=[
                "No direct relationship found; returned fallback neighborhoods for source and target nodes."
            ],
        )

    def _find_exact_nodes(self, names: list[str], labels: list[str], limit: int) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        for name in names:
            nodes.extend(self.repository.find_exact_nodes(name, labels=labels, limit=limit))
        return merge_nodes(nodes)

    def _find_vector_nodes(
        self,
        names: list[str],
        labels: list[str],
        *,
        top_k: int,
        rerank: bool = False,
        vector_top_k: int = 20,
        rerank_top_n: int = 2,
    ) -> list[dict[str, Any]]:
        exact_nodes: list[dict[str, Any]] = []
        vector_nodes: list[dict[str, Any]] = []
        candidate_top_k = vector_top_k if rerank else top_k
        for name in names:
            for exact_query in exact_node_queries(name):
                for node in self.repository.find_exact_nodes(exact_query, labels=labels, limit=candidate_top_k):
                    exact_node = dict(node)
                    exact_node["score"] = 1.0
                    exact_nodes.append(exact_node)
            embedding = self._embed_text(name, True)
            if embedding is None:
                continue
            vector_nodes.extend(
                self.repository.vector_search_nodes(
                    index_name=self.semantic_config.embedding.node_index,
                    query_embedding=embedding,
                    labels=labels,
                    top_k=candidate_top_k,
                )
            )
        exact_candidates = merge_nodes(exact_nodes)
        vector_candidates = merge_nodes_by_best_score(vector_nodes)[:candidate_top_k]
        if exact_candidates:
            exact_ids = {str(node["id"]) for node in exact_candidates}
            remaining = [node for node in vector_candidates if str(node["id"]) not in exact_ids]
            if not rerank:
                return merge_nodes(exact_candidates, remaining)[:top_k]
            if len(exact_candidates) >= rerank_top_n:
                return exact_candidates[:rerank_top_n]
            reranked_remaining = self._rerank_nodes(
                format_query(names),
                remaining,
                rerank_top_n - len(exact_candidates),
            )
            return merge_nodes(exact_candidates, reranked_remaining)[:rerank_top_n]

        candidates = vector_candidates
        if not rerank:
            return candidates[:top_k]
        return self._rerank_nodes(format_query(names), candidates, rerank_top_n)

    def _rerank_nodes(self, query: str, nodes: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
        if not nodes:
            return []
        texts = [build_node_rerank_text(node) for node in nodes]
        results = self.rerank_client.rerank(query, texts, top_n=top_n)
        if not results:
            return nodes[:top_n]
        ranked_nodes = []
        for result in results:
            if 0 <= result.index < len(nodes):
                node = dict(nodes[result.index])
                node["rerank_score"] = result.score
                ranked_nodes.append(node)
        return ranked_nodes[:top_n] if ranked_nodes else nodes[:top_n]

    def _get_neighborhoods_by_exact_names(
        self,
        names: list[str],
        *,
        labels: list[str],
        depth: int,
        direction: str,
        relationship_types: list[str],
        limit: int,
    ) -> dict[str, list[dict[str, Any]]]:
        nodes: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        for name in names:
            graph = self.repository.get_neighborhood_by_exact_name(
                name,
                labels=labels,
                depth=depth,
                direction=direction,
                relationship_types=relationship_types,
                limit=limit,
            )
            nodes.extend(graph["nodes"])
            relationships.extend(graph["relationships"])
        return {"nodes": merge_nodes(nodes), "relationships": dedupe_by_id(relationships)}

    def _get_neighborhoods_by_node_ids(
        self,
        node_ids: list[str],
        *,
        depth: int,
        direction: str,
        relationship_types: list[str],
        limit: int,
    ) -> dict[str, list[dict[str, Any]]]:
        nodes: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        for node_id in node_ids:
            graph = self.repository.get_neighborhood_by_node_id(
                node_id,
                depth=depth,
                direction=direction,
                relationship_types=relationship_types,
                limit=limit,
            )
            nodes.extend(graph["nodes"])
            relationships.extend(graph["relationships"])
        return {"nodes": merge_nodes(nodes), "relationships": dedupe_by_id(relationships)}

    def _find_related_by_relationships(
        self,
        names: list[str],
        relationship_type: str,
        *,
        labels: list[str],
        target_labels: list[str],
        direction: str,
        limit: int,
    ) -> dict[str, list[dict[str, Any]]]:
        nodes: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        for name in names:
            graph = self.repository.find_related_by_relationship(
                name,
                relationship_type,
                labels=labels,
                target_labels=target_labels,
                direction=direction,
                limit=limit,
            )
            nodes.extend(graph["nodes"])
            relationships.extend(graph["relationships"])
        return {"nodes": merge_nodes(nodes), "relationships": dedupe_by_id(relationships)}

    def _graph_response(
        self,
        *,
        query: str | list[str],
        include_properties: bool,
        matched_nodes: list[dict[str, Any]] | None = None,
        nodes: list[dict[str, Any]] | None = None,
        relationships: list[dict[str, Any]] | None = None,
        paths: list[dict[str, Any]] | None = None,
        direct_relationship_found: bool | None = None,
        warnings: list[str] | None = None,
    ) -> GraphQueryResponse:
        node_models = [format_node(node, include_properties) for node in dedupe_by_id(nodes or [])]
        node_map = {node.id: node.name for node in node_models}
        return GraphQueryResponse(
            query=query,
            matched_nodes=[format_node(node, include_properties) for node in dedupe_by_id(matched_nodes or [])],
            nodes=node_models,
            relationships=[
                format_relationship(relationship, node_map, include_properties)
                for relationship in dedupe_by_id(relationships or [])
            ],
            paths=[format_path(path, include_properties) for path in paths or []],
            direct_relationship_found=direct_relationship_found,
            warnings=warnings or [],
        )

    def _graph_data(self, graph: dict[str, list[dict[str, Any]]], include_properties: bool) -> GraphData:
        nodes = [format_node(node, include_properties) for node in dedupe_by_id(graph["nodes"])]
        node_map = {node.id: node.name for node in nodes}
        relationships = [
            format_relationship(relationship, node_map, include_properties)
            for relationship in dedupe_by_id(graph["relationships"])
        ]
        return GraphData(nodes=nodes, relationships=relationships)


def format_node(node: dict[str, Any], include_properties: bool) -> GraphNode:
    properties = visible_properties(dict(node.get("properties") or {}))
    if "score" in node:
        properties["_score"] = node["score"]
    return GraphNode(
        id=str(node["id"]),
        name=node_display_name(node),
        labels=list(node.get("labels") or []),
        properties=properties if include_properties else None,
    )


def format_relationship(
    relationship: dict[str, Any],
    node_map: dict[str, str],
    include_properties: bool,
) -> GraphRelationship:
    source_id = str(relationship["source_id"])
    target_id = str(relationship["target_id"])
    return GraphRelationship(
        id=str(relationship["id"]),
        type=str(relationship["type"]),
        source_id=source_id,
        target_id=target_id,
        source_name=node_map.get(source_id),
        target_name=node_map.get(target_id),
        properties=visible_properties(dict(relationship.get("properties") or {})) if include_properties else None,
    )


def format_path(path: dict[str, Any], include_properties: bool) -> GraphPath:
    nodes = [format_node(node, include_properties) for node in path.get("nodes", [])]
    node_map = {node.id: node.name for node in nodes}
    relationships = [
        format_relationship(relationship, node_map, include_properties)
        for relationship in path.get("relationships", [])
    ]
    return GraphPath(nodes=nodes, relationships=relationships, length=int(path.get("length", len(relationships))))


def node_display_name(node: dict[str, Any]) -> str:
    properties = node.get("properties") or {}
    for key in ("name", "symbol", "title", "id", "vid"):
        value = properties.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return str(node["id"])


def request_names(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else value


def exact_node_queries(value: str) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    append_unique(queries, seen, value)
    for token in re.split(r"[^0-9A-Za-z_.-]+", value):
        if len(token) >= 2 and any(char.isalpha() for char in token):
            append_unique(queries, seen, token)
    return queries


def format_query(value: str | list[str]) -> str:
    return value if isinstance(value, str) else ", ".join(value)


def build_node_embedding_text(labels: list[str], properties: dict[str, Any], explicit_text: str | None = None) -> str:
    if explicit_text and explicit_text.strip():
        return explicit_text.strip()
    node_type = semantic_node_type(labels, properties)
    if node_type == "Measurement":
        return ""
    return clean_embedding_value(properties.get("name"))


def build_node_rerank_text(node: dict[str, Any]) -> str:
    properties = dict(node.get("properties") or {})
    labels = list(node.get("labels") or [])
    node_type = semantic_node_type(labels, properties)
    parts = [f"name: {node_display_name(node)}"]
    if node_type:
        parts.append(f"node_type: {node_type}")
    append_embedding_fields(parts, properties, NODE_EMBEDDING_FIELDS.get(node_type, ("description",)))
    return "\n".join(parts)


def build_relationship_embedding_text(
    source_node: dict[str, Any],
    target_node: dict[str, Any],
    relationship_type: str,
    properties: dict[str, Any],
    explicit_text: str | None = None,
) -> str:
    if explicit_text and explicit_text.strip():
        return explicit_text.strip()
    if relationship_type == "HAS_MEASUREMENT":
        return ""
    parts = [
        f"relationship_type: {relationship_type}",
        f"source: {node_display_name(source_node)}",
        f"target: {node_display_name(target_node)}",
    ]
    append_embedding_fields(parts, properties, RELATIONSHIP_EMBEDDING_FIELDS.get(relationship_type, ()))
    return "\n".join(parts)


NODE_EMBEDDING_FIELDS: dict[str, tuple[str, ...]] = {
    "CellType": ("name", "tissue"),
    "Disease": ("name", "disease_category"),
    "GOFunction": ("name", "go_id", "go_category"),
    "Gene": ("name", "gene_full_name", "organism", "description"),
    "GeneFunction": ("name", "function_category", "source_text"),
    "Literature": ("name", "pmid", "year"),
    "Metabolite": ("name", "molecule_class", "structural_level", "sum_composition", "acyl_chains", "modifications"),
    "MetaboliteCategory": ("name", "description", "category_level"),
    "Pathway": ("name", "description", "kegg_id", "pathway_category"),
    "Protein": ("name", "description"),
}


RELATIONSHIP_EMBEDDING_FIELDS: dict[str, tuple[str, ...]] = {
    "ASSOCIATED_WITH_DISEASE": ("evidence",),
    "CATALYZES": ("reaction_type",),
    "METABOLITE_ASSOCIATED_WITH_DISEASE": ("biomarker_type",),
    "ORTHOLOG_MAPPING": ("role",),
    "PARTICIPATES_IN": ("role",),
    "PATHWAY_CONTAINS_METABOLITE": ("metabolite_role",),
    "PATHWAY_CROSSES": ("shared_component",),
    "PROTEIN_INTERACTS_WITH": ("interaction_type",),
}


SKIP_EMBEDDING_VALUES = {"", "待注释", "unknown", "none", "null", "nan"}


def semantic_node_type(labels: list[str], properties: dict[str, Any]) -> str:
    for label in labels:
        if label != "KGNode":
            return str(label)
    entity_type = properties.get("entity_type")
    return str(entity_type).strip() if entity_type is not None else ""


def append_embedding_fields(parts: list[str], properties: dict[str, Any], fields: tuple[str, ...]) -> None:
    for key in fields:
        value = clean_embedding_value(properties.get(key))
        if value:
            parts.append(f"{key}: {value}")


def clean_embedding_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list | tuple | set):
        text = ", ".join(str(item).strip() for item in value if str(item).strip())
    else:
        text = str(value).strip()
    if text.lower() in SKIP_EMBEDDING_VALUES:
        return ""
    return text


def visible_properties(properties: dict[str, Any]) -> dict[str, Any]:
    properties.pop("embedding", None)
    return properties


def relationship_type_name(relationship: dict[str, Any]) -> str:
    properties = relationship.get("properties") or {}
    return str(
        properties.get("relationship_type")
        or relationship.get("type")
        or properties.get("relationship_type_zh")
        or ""
    )


def append_unique(items: list[str], seen: set[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in seen:
        seen.add(text)
        items.append(text)


def merge_nodes(*node_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for nodes in node_lists:
        for node in nodes:
            node_id = str(node["id"])
            existing = merged.get(node_id)
            if existing is not None and "score" in existing and "score" not in node:
                continue
            if existing is not None and "score" in existing and "score" in node:
                if float(existing["score"]) >= float(node["score"]):
                    continue
            merged[node_id] = node
    return list(merged.values())


def merge_nodes_by_best_score(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(merge_nodes(nodes), key=lambda node: float(node.get("score", 0.0)), reverse=True)


def dedupe_by_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        deduped[str(item["id"])] = item
    return list(deduped.values())


def graph_from_paths(paths: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    relationships: dict[str, dict[str, Any]] = {}
    for path in paths:
        for node in path.get("nodes", []):
            nodes[str(node["id"])] = node
        for relationship in path.get("relationships", []):
            relationships[str(relationship["id"])] = relationship
    return {"nodes": list(nodes.values()), "relationships": list(relationships.values())}
