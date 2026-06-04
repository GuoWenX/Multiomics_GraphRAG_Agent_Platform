from __future__ import annotations

import pytest

from app.repositories.graph_repository import GraphRepository


def test_repository_clamps_depth_and_limit() -> None:
    repository = GraphRepository()

    assert repository._clamp_depth(99) == 5
    assert repository._clamp_depth(0) == 1
    assert repository._clamp_limit(9999) == 500
    assert repository._clamp_limit(0) == 1


def test_repository_accepts_chinese_labels_and_relationship_types() -> None:
    repository = GraphRepository()

    assert repository._clean_names(["基因", "  参与通路  "]) == ["基因", "参与通路"]


def test_repository_rejects_invalid_direction() -> None:
    repository = GraphRepository()

    with pytest.raises(ValueError, match="direction"):
        repository._validate_direction("sideways")
