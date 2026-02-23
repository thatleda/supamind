from unittest.mock import MagicMock

from tools.memory import memory


async def test_remember_stores_and_returns_entity(mock_db):
    mock_db.execute.return_value = MagicMock(data=[{
        "id": "abc-123",
        "entity_name": "Test Memory",
        "emotional_resonance": 0.4,
        "created_at": "2026-01-01T00:00:00+00:00",
    }])

    result = await memory.call_tool("remember", {
        "entity_name": "Test Memory",
        "observations": ["First observation", "Second observation"],
        "emotional_resonance": 0.4,
    })
    content = result.structured_content

    assert content["entityId"] == "abc-123"
    assert content["entityName"] == "Test Memory"
    assert content["observationsCount"] == 2


async def test_remember_clamps_resonance_below_minimum(mock_db):
    mock_db.execute.return_value = MagicMock(data=[{
        "id": "abc-123",
        "entity_name": "Test",
        "emotional_resonance": 0.1,
        "created_at": "2026-01-01T00:00:00+00:00",
    }])

    await memory.call_tool("remember", {
        "entity_name": "Test",
        "observations": ["obs"],
        "emotional_resonance": 0.0,
    })

    inserted_row = mock_db.insert.call_args[0][0]
    assert inserted_row["emotional_resonance"] == 0.1


async def test_remember_clamps_resonance_above_maximum(mock_db):
    mock_db.execute.return_value = MagicMock(data=[{
        "id": "abc-123",
        "entity_name": "Test",
        "emotional_resonance": 1.0,
        "created_at": "2026-01-01T00:00:00+00:00",
    }])

    await memory.call_tool("remember", {
        "entity_name": "Test",
        "observations": ["obs"],
        "emotional_resonance": 99.0,
    })

    inserted_row = mock_db.insert.call_args[0][0]
    assert inserted_row["emotional_resonance"] == 1.0


async def test_recall_by_entity_name(mock_db):
    mock_db.execute.return_value = MagicMock(data=[{
        "entity_name": "Engineering Principles",
        "emotional_resonance": 1.0,
        "entity_type": "general",
        "created_at": "2026-01-01T00:00:00+00:00",
        "memory_content": {"observations": ["always investigate first"]},
    }])

    result = await memory.call_tool("recall", {"entity_name": "Engineering Principles"})
    content = result.structured_content

    assert content["totalRecalled"] == 1
    assert content["memories"][0]["entityName"] == "Engineering Principles"
    assert content["resonanceBuckets"]["high"] == 1


async def test_recall_returns_error_without_params():
    result = await memory.call_tool("recall", {})
    assert "error" in result.structured_content


async def test_recall_resonance_buckets(mock_db):
    mock_db.execute.return_value = MagicMock(data=[
        {"entity_name": "A", "emotional_resonance": 0.9, "entity_type": "general",
         "created_at": "2026-01-01T00:00:00+00:00", "memory_content": {}},
        {"entity_name": "B", "emotional_resonance": 0.7, "entity_type": "general",
         "created_at": "2026-01-01T00:00:00+00:00", "memory_content": {}},
        {"entity_name": "C", "emotional_resonance": 0.3, "entity_type": "general",
         "created_at": "2026-01-01T00:00:00+00:00", "memory_content": {}},
    ])

    result = await memory.call_tool("recall", {"entity_type": "general"})
    buckets = result.structured_content["resonanceBuckets"]

    assert buckets["high"] == 1
    assert buckets["medium"] == 1
    assert buckets["low"] == 1


async def test_memory_delete_not_found(mock_db):
    mock_db.execute.return_value = MagicMock(data=None)

    result = await memory.call_tool("memory_delete", {"entity_name": "Nonexistent"})
    content = result.structured_content

    assert content["deleted"] is False


async def test_memory_delete_success(mock_db):
    mock_db.execute.side_effect = [
        MagicMock(data={"id": "abc-123", "entity_type": "general"}),
        MagicMock(data=[{"id": "abc-123"}]),
    ]

    result = await memory.call_tool("memory_delete", {"entity_name": "Old Memory"})
    content = result.structured_content

    assert content["deleted"] is True


async def test_memory_delete_blocks_foundational_without_force(mock_db):
    mock_db.execute.return_value = MagicMock(data={"id": "abc-123", "entity_type": "self"})

    result = await memory.call_tool("memory_delete", {"entity_name": "Matt"})
    content = result.structured_content

    assert content["deleted"] is False
    assert "warning" in content
    assert "force=True" in content["warning"]


async def test_memory_delete_foundational_with_force(mock_db):
    mock_db.execute.side_effect = [
        MagicMock(data={"id": "abc-123", "entity_type": "self"}),
        MagicMock(data=[{"id": "abc-123"}]),
    ]

    result = await memory.call_tool("memory_delete", {"entity_name": "Matt", "force": True})
    content = result.structured_content

    assert content["deleted"] is True


async def test_memory_update_only_patches_specified_fields(mock_db):
    existing = {
        "id": "abc-123",
        "entity_name": "My Memory",
        "emotional_resonance": 0.5,
        "entity_type": "general",
        "memory_content": {"observations": ["original obs"], "content": "original obs"},
    }
    mock_db.execute.side_effect = [
        MagicMock(data=existing),
        MagicMock(data=[existing]),
    ]

    await memory.call_tool("memory_update", {
        "entity_name": "My Memory",
        "emotional_resonance": 0.9,
    })

    update_patch = mock_db.update.call_args[0][0]
    assert update_patch["emotional_resonance"] == 0.9
    assert "entity_name" not in update_patch
    assert "memory_content" not in update_patch


async def test_memory_update_appends_observations_on_foundational(mock_db):
    existing = {
        "id": "abc-123",
        "entity_name": "Matt",
        "emotional_resonance": 1.0,
        "entity_type": "self",
        "memory_content": {"observations": ["original obs"], "content": "original obs"},
    }
    mock_db.execute.side_effect = [
        MagicMock(data=existing),
        MagicMock(data=[existing]),
    ]

    result = await memory.call_tool("memory_update", {
        "entity_name": "Matt",
        "observations": ["new obs"],
    })
    content = result.structured_content

    assert "warning" in content
    assert "force=True" in content["warning"]
    merged = mock_db.update.call_args[0][0]["memory_content"]["observations"]
    assert merged == ["original obs", "new obs"]


async def test_memory_update_replaces_foundational_observations_with_force(mock_db):
    existing = {
        "id": "abc-123",
        "entity_name": "Matt",
        "emotional_resonance": 1.0,
        "entity_type": "self",
        "memory_content": {"observations": ["original obs"], "content": "original obs"},
    }
    mock_db.execute.side_effect = [
        MagicMock(data=existing),
        MagicMock(data=[existing]),
    ]

    result = await memory.call_tool("memory_update", {
        "entity_name": "Matt",
        "observations": ["replacement obs"],
        "force": True,
    })
    content = result.structured_content

    assert "warning" not in content
    merged = mock_db.update.call_args[0][0]["memory_content"]["observations"]
    assert merged == ["replacement obs"]


async def test_memories_get_ids_reports_missing(mock_db):
    mock_db.execute.return_value = MagicMock(data=[
        {"entity_name": "Leda Wolf", "id": "uuid-leda"},
    ])

    result = await memory.call_tool("memories_get_ids", {
        "entity_names": ["Leda Wolf", "Missing Entity"],
    })
    content = result.structured_content

    assert content["found"]["Leda Wolf"] == "uuid-leda"
    assert "Missing Entity" in content["missing"]
    assert content["totalFound"] == 1
    assert content["totalRequested"] == 2
