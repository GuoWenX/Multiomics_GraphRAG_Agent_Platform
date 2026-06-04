from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes.graph import get_graph_service
from app.main import app
from app.services.graph_service import GraphService


client = TestClient(app)


class FakeRepository:
    node = {
        "id": "node-1",
        "labels": ["Gene"],
        "properties": {"name": "SMPD3", "type": "gene"},
    }
    neighbor = {
        "id": "node-2",
        "labels": ["Pathway"],
        "properties": {"name": "Sphingolipid metabolism"},
    }
    relationship = {
        "id": "rel-1",
        "type": "PARTICIPATES_IN",
        "source_id": "node-1",
        "target_id": "node-2",
        "properties": {"source": "test"},
    }
    created_relationship = {
        "id": "rel-created",
        "type": "ENCODES",
        "source_id": "node-1",
        "target_id": "node-2",
        "properties": {"evidence": "manual"},
    }

    def create_node(self, *, labels, properties, embedding_property=None, embedding=None):
        node = {"id": "node-created", "labels": labels, "properties": dict(properties)}
        if embedding is not None and embedding_property:
            node["properties"][embedding_property] = embedding
        return node

    def create_relationship(
        self,
        *,
        source_node_id,
        target_node_id,
        relationship_type,
        properties,
        embedding_property=None,
        embedding=None,
    ):
        if source_node_id != self.node["id"] or target_node_id != self.neighbor["id"]:
            return None
        relationship = {
            "id": "rel-created",
            "type": relationship_type,
            "source_id": source_node_id,
            "target_id": target_node_id,
            "properties": dict(properties),
        }
        if embedding is not None and embedding_property:
            relationship["properties"][embedding_property] = embedding
        return {"nodes": [self.node, self.neighbor], "relationships": [relationship]}

    def find_exact_nodes(self, *args, **kwargs):
        name = args[0] if args else kwargs.get("name")
        labels = kwargs.get("labels") or []
        candidates = [self.node, self.neighbor]
        matches = [
            node
            for node in candidates
            if node["properties"].get("name") == name
            and (not labels or set(labels) & set(node["labels"]))
        ]
        return matches

    def get_node_detail(self, node_id):
        if node_id == self.node["id"]:
            return self.node
        if node_id == self.neighbor["id"]:
            return self.neighbor
        return None

    def get_neighborhood_by_exact_name(self, *args, **kwargs):
        return {"nodes": [self.node, self.neighbor], "relationships": [self.relationship]}

    def get_neighborhood_by_node_id(self, *args, **kwargs):
        return {"nodes": [self.node, self.neighbor], "relationships": [self.relationship]}

    def find_related_by_relationship(self, *args, **kwargs):
        return {"nodes": [self.node, self.neighbor], "relationships": [self.relationship]}

    def find_direct_relationships_by_names(self, *args, **kwargs):
        return [
            {
                "nodes": [self.node, self.neighbor],
                "relationships": [self.relationship],
                "length": 1,
            }
        ]

    def update_node_properties(self, node_id, properties):
        if node_id != self.node["id"]:
            return None
        node = {
            "id": self.node["id"],
            "labels": self.node["labels"],
            "properties": dict(self.node["properties"]),
        }
        for key, value in properties.items():
            if value is None:
                node["properties"].pop(key, None)
            else:
                node["properties"][key] = value
        return node

    def delete_node(self, node_id, *, detach=False):
        return node_id == self.node["id"]

    def vector_search_nodes(self, *, index_name, query_embedding, labels=None, top_k=5):
        assert index_name == "kg_node_embedding_index"
        assert query_embedding == [0.1, 0.2, 0.3]
        candidates = [
            {
                "id": self.node["id"],
                "labels": self.node["labels"],
                "properties": dict(self.node["properties"]),
                "score": 0.96,
            },
            {
                "id": self.neighbor["id"],
                "labels": self.neighbor["labels"],
                "properties": dict(self.neighbor["properties"]),
                "score": 0.91,
            },
        ]
        if labels:
            candidates = [node for node in candidates if set(labels) & set(node["labels"])]
        return candidates[:top_k]

    def get_overview(self):
        return {
            "total_nodes": 2,
            "total_relationships": 1,
            "node_labels": [
                {"name": "Gene", "count": 1},
                {"name": "Pathway", "count": 1},
            ],
            "relationship_types": [
                {"name": "PARTICIPATES_IN", "count": 1},
            ],
        }


class UnavailableGraphService:
    def check_health(self) -> None:
        raise RuntimeError("database down")


def override_graph_service():
    return GraphService(FakeRepository())


class FakeEmbeddingClient:
    def embed_text(self, text):
        assert text
        return [0.1, 0.2, 0.3]


def override_graph_service_with_embedding():
    return GraphService(FakeRepository(), embedding_client=FakeEmbeddingClient())


def test_graph_route_validation_rejects_invalid_depth() -> None:
    response = client.post("/api/v1/graph/neighbors", json={"name": "SMPD3", "depth": 0})

    assert response.status_code == 422


def test_graph_health_returns_503_when_neo4j_unavailable() -> None:
    app.dependency_overrides[get_graph_service] = lambda: UnavailableGraphService()
    try:
        response = client.get("/api/v1/graph/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "Neo4j unavailable" in response.json()["detail"]


def test_graph_overview_returns_label_and_relationship_counts() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service
    try:
        response = client.get("/api/v1/graph/overview")
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["total_nodes"] == 2
    assert payload["total_relationships"] == 1
    assert payload["node_labels"] == [
        {"name": "Gene", "count": 1},
        {"name": "Pathway", "count": 1},
    ]
    assert payload["relationship_types"] == [{"name": "PARTICIPATES_IN", "count": 1}]


def test_search_nodes_returns_parseable_graph_response_without_properties() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service
    try:
        response = client.post(
            "/api/v1/graph/nodes/search",
            json={"name": "SMPD3", "depth": 1, "include_properties": False, "llm_text": False},
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["query"] == "SMPD3"
    assert payload["matched_nodes"][0]["name"] == "SMPD3"
    assert payload["nodes"][0]["properties"] is None
    assert payload["relationships"][0]["source_name"] == "SMPD3"


def test_search_nodes_accepts_name_list() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service
    try:
        response = client.post(
            "/api/v1/graph/nodes/search",
            json={"name": ["SMPD3", "鞘脂代谢"], "depth": 1, "include_properties": True, "llm_text": False},
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["query"] == ["SMPD3", "鞘脂代谢"]
    assert payload["nodes"][0]["name"] == "SMPD3"
    assert payload["relationships"][0]["type"] == "PARTICIPATES_IN"


def test_search_nodes_returns_llm_text_by_default() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service
    try:
        response = client.post(
            "/api/v1/graph/nodes/search",
            json={"name": "SMPD3", "depth": 1},
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert set(payload) == {"entities", "relationships"}
    assert payload["entities"] == "SMPD3\nSphingolipid metabolism"
    assert payload["relationships"] == "PARTICIPATES_IN:[SMPD3->Sphingolipid metabolism]"


def test_search_nodes_can_use_vector_search_top_k() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service_with_embedding
    try:
        response = client.post(
            "/api/v1/graph/nodes/search",
            json={
                "name": "sphingomyelin phosphodiesterase 3",
                "vector_search": True,
                "top_k": 1,
                "llm_text": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["matched_nodes"][0]["name"] == "SMPD3"
    assert payload["matched_nodes"][0]["properties"]["_score"] == 0.96
    assert len(payload["matched_nodes"]) == 1


def test_search_nodes_vector_search_prioritizes_exact_match() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service_with_embedding
    try:
        response = client.post(
            "/api/v1/graph/nodes/search",
            json={
                "name": "SMPD3",
                "vector_search": True,
                "top_k": 2,
                "llm_text": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["matched_nodes"][0]["name"] == "SMPD3"
    assert payload["matched_nodes"][0]["properties"]["_score"] == 1.0


def test_search_nodes_vector_search_can_filter_labels() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service_with_embedding
    try:
        response = client.post(
            "/api/v1/graph/nodes/search",
            json={
                "name": "sphingolipid metabolism",
                "labels": ["Pathway"],
                "vector_search": True,
                "top_k": 5,
                "llm_text": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert [node["name"] for node in payload["matched_nodes"]] == ["Sphingolipid metabolism"]


def test_paths_endpoint_reports_direct_relationship() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service
    try:
        response = client.post(
            "/api/v1/graph/paths",
            json={"source_name": "SMPD3", "target_name": "Sphingolipid metabolism"},
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["direct_relationship_found"] is True
    assert payload["paths"][0]["length"] == 1


def test_create_node_writes_embedding_and_hides_vector_property() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service_with_embedding
    try:
        response = client.post(
            "/api/v1/graph/nodes/create",
            json={
                "labels": ["Gene", "KGNode"],
                "properties": {"name": "SMPD3", "description": "nSMase2"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["embedding_written"] is True
    assert payload["node"]["id"] == "node-created"
    assert payload["node"]["labels"] == ["Gene", "KGNode"]
    assert payload["node"]["properties"]["name"] == "SMPD3"
    assert "embedding" not in payload["node"]["properties"]


def test_create_node_can_skip_embedding() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service_with_embedding
    try:
        response = client.post(
            "/api/v1/graph/nodes/create",
            json={"labels": ["Gene"], "properties": {"name": "SMPD3"}, "embed": False},
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["embedding_written"] is False


def test_create_relationship_writes_embedding_and_hides_vector_property() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service_with_embedding
    try:
        response = client.post(
            "/api/v1/graph/relationships/create",
            json={
                "source_node_id": "node-1",
                "target_node_id": "node-2",
                "relationship_type": "ENCODES",
                "properties": {"evidence": "manual"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["embedding_written"] is True
    assert payload["relationship"]["type"] == "ENCODES"
    assert payload["relationship"]["source_name"] == "SMPD3"
    assert payload["relationship"]["target_name"] == "Sphingolipid metabolism"
    assert payload["relationship"]["properties"] == {"evidence": "manual"}


def test_create_relationship_returns_404_for_missing_node() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service_with_embedding
    try:
        response = client.post(
            "/api/v1/graph/relationships/create",
            json={
                "source_node_id": "missing",
                "target_node_id": "node-2",
                "relationship_type": "ENCODES",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_update_node_updates_and_removes_properties() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service
    try:
        response = client.post(
            "/api/v1/graph/nodes/update",
            json={
                "node_id": "node-1",
                "properties": {"description": "updated"},
                "remove_properties": ["type"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["node"]["id"] == "node-1"
    assert payload["node"]["properties"]["description"] == "updated"
    assert "type" not in payload["node"]["properties"]


def test_update_node_returns_404_for_missing_node() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service
    try:
        response = client.post(
            "/api/v1/graph/nodes/update",
            json={"node_id": "missing", "properties": {"description": "updated"}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_delete_node_returns_delete_result() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service
    try:
        response = client.post(
            "/api/v1/graph/nodes/delete",
            json={"node_id": "node-1", "detach": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "node_id": "node-1", "detached": True}


def test_delete_node_returns_404_for_missing_node() -> None:
    app.dependency_overrides[get_graph_service] = override_graph_service
    try:
        response = client.post(
            "/api/v1/graph/nodes/delete",
            json={"node_id": "missing"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
