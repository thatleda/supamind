from unittest.mock import MagicMock

import pytest
from fastmcp.exceptions import ToolError

from src.tools.memory import memory


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


async def test_remember_with_relation_does_not_insert_when_target_missing(mock_db):
    mock_db.execute.return_value = None

    with pytest.raises(ToolError, match="Target entity not found"):
        await memory.call_tool("remember_with_relation", {
            "entity_name": "New Memory",
            "observations": ["obs"],
            "connect_to": {
                "entity_name": "Ghost",
                "relation_type": "relates_to",
                "description": "irrelevant",
            },
        })

    mock_db.insert.assert_not_called()


async def test_remember_with_relation_creates_and_connects(mock_db):
    target_response = MagicMock(data={"id": "uuid-target", "entity_name": "Existing Entity"})
    insert_response = MagicMock(data=[{"id": "uuid-new"}])
    relation_response = MagicMock(data=[{"id": "rel-1"}])
    mock_db.execute.side_effect = [target_response, insert_response, relation_response]

    result = await memory.call_tool("remember_with_relation", {
        "entity_name": "New Memory",
        "observations": ["obs"],
        "connect_to": {
            "entity_name": "Existing Entity",
            "relation_type": "relates_to",
            "description": "irrelevant",
        },
    })
    content = result.structured_content

    assert content["entityId"] == "uuid-new"
    assert content["connectedTo"] == "Existing Entity"


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
    mock_db.execute.return_value = None

    result = await memory.call_tool("memory_delete", {"entity_name": "Nonexistent"})
    content = result.structured_content

    assert content["deleted"] is False


async def test_memory_delete_success(mock_db):
    mock_db.execute.side_effect = [
        MagicMock(data={
            "id": "abc-123", "entity_type": "general", "entity_name": "Old Memory",
            "emotional_resonance": 0.4, "memory_content": {}, "metadata": {},
        }),
        MagicMock(data=[{"id": "version-1"}]),
        MagicMock(data=[{"id": "abc-123"}]),
    ]

    result = await memory.call_tool("memory_delete", {"entity_name": "Old Memory"})
    content = result.structured_content

    assert content["deleted"] is True


async def test_memory_delete_blocks_foundational_without_force(mock_db):
    mock_db.execute.return_value = MagicMock(data={"id": "abc-123", "entity_type": "self"})

    result = await memory.call_tool("memory_delete", {"entity_name": "Test Self"})
    content = result.structured_content

    assert content["deleted"] is False
    assert "warning" in content
    assert "force=True" in content["warning"]


async def test_memory_delete_foundational_with_force(mock_db):
    mock_db.execute.side_effect = [
        MagicMock(data={
            "id": "abc-123", "entity_type": "self", "entity_name": "Test Self",
            "emotional_resonance": 1.0, "memory_content": {}, "metadata": {},
        }),
        MagicMock(data=[{"id": "version-1"}]),
        MagicMock(data=[{"id": "abc-123"}]),
    ]

    result = await memory.call_tool("memory_delete", {"entity_name": "Test Self", "force": True})
    content = result.structured_content

    assert content["deleted"] is True


async def test_memory_update_not_found(mock_db):
    mock_db.execute.return_value = None

    result = await memory.call_tool("memory_update", {
        "entity_name": "Nonexistent",
        "observations": ["obs"],
    })
    content = result.structured_content

    assert content["updated"] is False


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
        MagicMock(data=[{"id": "version-1"}]),
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
        "entity_name": "Test Self",
        "emotional_resonance": 1.0,
        "entity_type": "self",
        "memory_content": {"observations": ["original obs"], "content": "original obs"},
    }
    mock_db.execute.side_effect = [
        MagicMock(data=existing),
        MagicMock(data=[{"id": "version-1"}]),
        MagicMock(data=[existing]),
    ]

    result = await memory.call_tool("memory_update", {
        "entity_name": "Test Self",
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
        "entity_name": "Test Self",
        "emotional_resonance": 1.0,
        "entity_type": "self",
        "memory_content": {"observations": ["original obs"], "content": "original obs"},
    }
    mock_db.execute.side_effect = [
        MagicMock(data=existing),
        MagicMock(data=[{"id": "version-1"}]),
        MagicMock(data=[existing]),
    ]

    result = await memory.call_tool("memory_update", {
        "entity_name": "Test Self",
        "observations": ["replacement obs"],
        "force": True,
    })
    content = result.structured_content

    assert "warning" not in content
    merged = mock_db.update.call_args[0][0]["memory_content"]["observations"]
    assert merged == ["replacement obs"]


async def test_memory_update_saves_snapshot_before_patching(mock_db):
    existing = {
        "id": "abc-123",
        "entity_name": "Test Self",
        "emotional_resonance": 1.0,
        "entity_type": "self",
        "memory_content": {"observations": ["original obs"], "content": "original obs"},
        "metadata": {},
    }
    mock_db.execute.side_effect = [
        MagicMock(data=existing),
        MagicMock(data=[{"id": "version-1"}]),
        MagicMock(data=[existing]),
    ]

    await memory.call_tool("memory_update", {
        "entity_name": "Test Self",
        "observations": ["new obs"],
        "force": True,
    })

    snapshot_row = mock_db.insert.call_args_list[0][0][0]
    assert snapshot_row["entity_id"] == "abc-123"
    assert snapshot_row["memory_content"]["observations"] == ["original obs"]
    assert snapshot_row["label"] == "pre-update"


async def test_memory_versions_lists_saved_snapshots(mock_db):
    mock_db.execute.side_effect = [
        MagicMock(data={"id": "abc-123"}),
        MagicMock(data=[
            {"id": "version-2", "entity_name": "Test Self", "entity_type": "self",
             "emotional_resonance": 1.0, "label": "pre-update",
             "created_at": "2026-01-02T00:00:00+00:00",
             "memory_content": {"observations": ["a", "b"]}},
        ]),
    ]

    result = await memory.call_tool("memory_versions", {"entity_name": "Test Self"})
    content = result.structured_content

    assert content["versionsCount"] == 1
    assert content["versions"][0]["versionId"] == "version-2"
    assert content["versions"][0]["observationsCount"] == 2


async def test_memory_versions_not_found(mock_db):
    mock_db.execute.return_value = None

    result = await memory.call_tool("memory_versions", {"entity_name": "Nonexistent"})
    content = result.structured_content

    assert content["found"] is False


async def test_memory_restore_applies_version_and_snapshots_current(mock_db):
    version = {
        "id": "version-1",
        "entity_id": "abc-123",
        "entity_name": "Test Self",
        "entity_type": "self",
        "emotional_resonance": 1.0,
        "memory_content": {"observations": ["restored obs"]},
        "metadata": {},
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    current = {
        "id": "abc-123",
        "entity_name": "Test Self",
        "entity_type": "self",
        "emotional_resonance": 1.0,
        "memory_content": {"observations": ["current obs"]},
        "metadata": {},
    }
    mock_db.execute.side_effect = [
        MagicMock(data=version),
        MagicMock(data=current),
        MagicMock(data=[{"id": "version-2"}]),
        MagicMock(data=[current]),
    ]

    result = await memory.call_tool("memory_restore", {"version_id": "version-1"})
    content = result.structured_content

    assert content["restored"] is True
    update_patch = mock_db.update.call_args[0][0]
    assert update_patch["memory_content"]["observations"] == ["restored obs"]


async def test_memory_restore_version_not_found(mock_db):
    mock_db.execute.return_value = None

    result = await memory.call_tool("memory_restore", {"version_id": "ghost"})
    content = result.structured_content

    assert content["restored"] is False


async def test_memories_get_ids_reports_missing(mock_db):
    mock_db.execute.return_value = MagicMock(data=[
        {"entity_name": "Test User", "id": "uuid-user"},
    ])

    result = await memory.call_tool("memories_get_ids", {
        "entity_names": ["Test User", "Missing Entity"],
    })
    content = result.structured_content

    assert content["found"]["Test User"] == "uuid-user"
    assert "Missing Entity" in content["missing"]
    assert content["totalFound"] == 1
    assert content["totalRequested"] == 2
