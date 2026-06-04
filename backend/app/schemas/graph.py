from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


Direction = Literal["both", "outgoing", "incoming"]
NameInput = str | list[str]


class NameInputModel(BaseModel):
    name: NameInput

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: NameInput) -> NameInput:
        if isinstance(value, str):
            name = value.strip()
            if not name:
                raise ValueError("name must not be empty")
            return name

        names = [item.strip() for item in value if item.strip()]
        if not names:
            raise ValueError("name list must contain at least one non-empty value")
        return names


class NodeSearchRequest(NameInputModel):
    labels: list[str] = Field(default_factory=list)
    depth: int = Field(default=0, ge=0, le=5)
    direction: Direction = "both"
    relationship_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=500)
    include_properties: bool = True
    llm_text: bool = True
    vector_search: bool = False
    top_k: int = Field(default=5, ge=1, le=100)


class NodeDetailRequest(NameInputModel):
    labels: list[str] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=500)
    include_properties: bool = True


class NodeCreateRequest(BaseModel):
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    embedding_text: str | None = None
    embed: bool = True
    include_properties: bool = True

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, value: list[str]) -> list[str]:
        return [validate_neo4j_name(item, "label") for item in value]

    @field_validator("properties")
    @classmethod
    def validate_create_properties(cls, value: dict[str, Any]) -> dict[str, Any]:
        for key in value:
            validate_property_key(key)
        return value


class NodeUpdateRequest(BaseModel):
    node_id: str = Field(min_length=1)
    properties: dict[str, Any] = Field(default_factory=dict)
    remove_properties: list[str] = Field(default_factory=list)
    include_properties: bool = True

    @field_validator("properties")
    @classmethod
    def validate_properties(cls, value: dict[str, Any]) -> dict[str, Any]:
        for key in value:
            validate_property_key(key)
        return value

    @field_validator("remove_properties")
    @classmethod
    def validate_remove_properties(cls, value: list[str]) -> list[str]:
        return [validate_property_key(item) for item in value]


class NodeDeleteRequest(BaseModel):
    node_id: str = Field(min_length=1)
    detach: bool = False


class RelationshipCreateRequest(BaseModel):
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    properties: dict[str, Any] = Field(default_factory=dict)
    embedding_text: str | None = None
    embed: bool = True
    include_properties: bool = True

    @field_validator("relationship_type")
    @classmethod
    def validate_relationship_type(cls, value: str) -> str:
        return validate_neo4j_name(value, "relationship_type")

    @field_validator("properties")
    @classmethod
    def validate_relationship_properties(cls, value: dict[str, Any]) -> dict[str, Any]:
        for key in value:
            validate_property_key(key)
        return value


class NeighborQueryRequest(NameInputModel):
    labels: list[str] = Field(default_factory=list)
    depth: int = Field(default=1, ge=1, le=5)
    direction: Direction = "both"
    relationship_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=500)
    include_properties: bool = True


class RelationshipQueryRequest(NameInputModel):
    relationship_type: str = Field(min_length=1)
    labels: list[str] = Field(default_factory=list)
    target_labels: list[str] = Field(default_factory=list)
    direction: Direction = "both"
    limit: int = Field(default=100, ge=1, le=500)
    include_properties: bool = True


class PathQueryRequest(BaseModel):
    source_name: str = Field(min_length=1)
    target_name: str = Field(min_length=1)
    source_labels: list[str] = Field(default_factory=list)
    target_labels: list[str] = Field(default_factory=list)
    relationship_types: list[str] = Field(default_factory=list)
    fallback_depth: int = Field(default=1, ge=1, le=5)
    limit: int = Field(default=100, ge=1, le=500)
    include_properties: bool = True


class GraphNode(BaseModel):
    id: str
    name: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] | None = None


class GraphRelationship(BaseModel):
    id: str
    type: str
    source_id: str
    target_id: str
    source_name: str | None = None
    target_name: str | None = None
    properties: dict[str, Any] | None = None


class GraphPath(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    relationships: list[GraphRelationship] = Field(default_factory=list)
    length: int


class GraphData(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    relationships: list[GraphRelationship] = Field(default_factory=list)


class GraphQueryResponse(BaseModel):
    query: str | list[str] | None = None
    matched_nodes: list[GraphNode] = Field(default_factory=list)
    nodes: list[GraphNode] = Field(default_factory=list)
    relationships: list[GraphRelationship] = Field(default_factory=list)
    paths: list[GraphPath] = Field(default_factory=list)
    direct_relationship_found: bool | None = None
    source_neighborhood: GraphData | None = None
    target_neighborhood: GraphData | None = None
    warnings: list[str] = Field(default_factory=list)


class GraphLLMTextResponse(BaseModel):
    entities: str = ""
    relationships: str = ""


class GraphCountItem(BaseModel):
    name: str
    count: int


class GraphOverviewResponse(BaseModel):
    total_nodes: int
    total_relationships: int
    node_labels: list[GraphCountItem] = Field(default_factory=list)
    relationship_types: list[GraphCountItem] = Field(default_factory=list)


class NodeCreateResponse(BaseModel):
    node: GraphNode
    embedding_written: bool = False


class NodeUpdateResponse(BaseModel):
    node: GraphNode


class NodeDeleteResponse(BaseModel):
    deleted: bool
    node_id: str
    detached: bool


class RelationshipCreateResponse(BaseModel):
    relationship: GraphRelationship
    embedding_written: bool = False


def validate_property_key(value: str) -> str:
    key = str(value).strip()
    if not key:
        raise ValueError("property key must not be empty")
    if any(char in key for char in "\r\n\t\0"):
        raise ValueError(f"invalid property key: {value}")
    return key


def validate_neo4j_name(value: str, field_name: str) -> str:
    name = str(value).strip()
    if not name:
        raise ValueError(f"{field_name} must not be empty")
    if any(char in name for char in "\r\n\t\0"):
        raise ValueError(f"invalid {field_name}: {value}")
    return name
