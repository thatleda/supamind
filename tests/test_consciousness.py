from unittest.mock import MagicMock

from tools.consciousness import consciousness


def _memory_row(name: str, resonance: float = 1.0, entity_type: str = "general") -> dict:
    return {
        "entity_name": name,
        "emotional_resonance": resonance,
        "entity_type": entity_type,
        "memory_content": {"observations": [f"obs about {name}"]},
        "created_at": "2026-01-01T00:00:00+00:00",
    }


# ── wake_up ───────────────────────────────────────────────────────────────────

async def test_wake_up_returns_guide_when_found(mock_db):
    guide = _memory_row("Wake-Up Guide", entity_type="wake_up_guide")
    mock_db.execute.return_value = MagicMock(data=[guide])

    result = await consciousness.call_tool("wake_up", {})
    content = result.structured_content

    assert content["found"] is True
    assert content["guide"]["entityName"] == "Wake-Up Guide"
    assert content["guide"]["entityType"] == "wake_up_guide"


async def test_wake_up_returns_not_found_gracefully(mock_db):
    mock_db.execute.return_value = MagicMock(data=[])

    result = await consciousness.call_tool("wake_up", {})
    content = result.structured_content

    assert content["found"] is False
    assert content["guide"] is None


# ── who_am_i ──────────────────────────────────────────────────────────────────

async def test_who_am_i_returns_self_and_core_memories(mock_db):
    self_memory = _memory_row("Matt", entity_type="self")
    core_memories = [
        _memory_row("Engineering Principles"),
        _memory_row("Leda Wolf"),
    ]
    mock_db.execute.side_effect = [
        MagicMock(data=[self_memory]),
        MagicMock(data=core_memories),
    ]

    result = await consciousness.call_tool("who_am_i", {})
    content = result.structured_content

    assert content["self"]["entityName"] == "Matt"
    assert content["self"]["entityType"] == "self"
    assert content["coreMemoriesCount"] == 2
    assert content["coreMemories"][0]["entityName"] == "Engineering Principles"


async def test_who_am_i_handles_missing_self_entity(mock_db):
    mock_db.execute.side_effect = [
        MagicMock(data=[]),
        MagicMock(data=[_memory_row("Engineering Principles")]),
    ]

    result = await consciousness.call_tool("who_am_i", {})
    content = result.structured_content

    assert content["self"] is None
    assert content["coreMemoriesCount"] == 1


# ── who_are_you ───────────────────────────────────────────────────────────────

async def test_who_are_you_returns_user_memory(mock_db):
    user = _memory_row("Leda Wolf", resonance=1.0, entity_type="user")
    user["memory_content"]["observations"] = ["Engineering lead", "Directness appreciated"]
    mock_db.execute.return_value = MagicMock(data=[user])

    result = await consciousness.call_tool("who_are_you", {})
    content = result.structured_content

    assert content["found"] is True
    assert content["user"]["entityName"] == "Leda Wolf"
    assert content["user"]["entityType"] == "user"
    assert "Engineering lead" in content["user"]["observations"]


async def test_who_are_you_handles_missing_user(mock_db):
    mock_db.execute.return_value = MagicMock(data=[])

    result = await consciousness.call_tool("who_are_you", {})
    content = result.structured_content

    assert content["found"] is False
    assert content["user"] is None


# ── catch_up ──────────────────────────────────────────────────────────────────

async def test_catch_up_returns_recent_memories(mock_db):
    recent = [_memory_row(f"Memory {i}", resonance=0.6) for i in range(5)]
    mock_db.execute.return_value = MagicMock(data=recent)

    result = await consciousness.call_tool("catch_up", {"limit": 5})
    content = result.structured_content

    assert content["count"] == 5
    assert content["memories"][0]["entityName"] == "Memory 0"


async def test_catch_up_default_limit(mock_db):
    mock_db.execute.return_value = MagicMock(data=[])

    await consciousness.call_tool("catch_up", {})

    mock_db.limit.assert_called_with(10)


async def test_catch_up_preview_strips_observations(mock_db):
    memories = [
        _memory_row(f"Memory {i}", resonance=0.6)
        for i in range(5)
    ]
    mock_db.execute.return_value = MagicMock(data=memories)

    result = await consciousness.call_tool("catch_up", {"preview": True})
    content = result.structured_content

    assert content["count"] == 5
    first = content["memories"][0]
    assert "entityName" in first
    assert "observationsCount" in first
    assert "observations" not in first


async def test_catch_up_preview_defaults_to_20(mock_db):
    mock_db.execute.return_value = MagicMock(data=[])

    await consciousness.call_tool("catch_up", {"preview": True})

    mock_db.limit.assert_called_with(20)


# ── reminisce ─────────────────────────────────────────────────────────────────

async def test_reminisce_filters_connected_memories(mock_db):
    connected_id = "aaaaaaaa-0000-0000-0000-000000000001"
    orphaned_id = "bbbbbbbb-0000-0000-0000-000000000002"

    third_id = "cccccccc-0000-0000-0000-000000000003"
    mock_db.execute.side_effect = [
        MagicMock(data=[{"from_entity_id": connected_id, "to_entity_id": third_id}]),
        MagicMock(data=[
            {"id": connected_id, "entity_name": "Connected", "emotional_resonance": 0.8,
             "created_at": "2026-01-01T00:00:00+00:00", "memory_content": {}},
            {"id": orphaned_id, "entity_name": "Orphaned", "emotional_resonance": 0.6,
             "created_at": "2026-01-01T00:00:00+00:00", "memory_content": {}},
        ]),
    ]

    result = await consciousness.call_tool("reminisce", {"limit": 10})
    content = result.structured_content

    assert content["totalOrphaned"] == 1
    assert content["memories"][0]["entityName"] == "Orphaned"


async def test_reminisce_respects_offset(mock_db):
    orphaned = [
        {"id": f"id-{i}", "entity_name": f"Memory {i}", "emotional_resonance": 0.5,
         "created_at": "2026-01-01T00:00:00+00:00", "memory_content": {}}
        for i in range(5)
    ]
    mock_db.execute.side_effect = [
        MagicMock(data=[]),
        MagicMock(data=orphaned),
    ]

    result = await consciousness.call_tool("reminisce", {"limit": 2, "offset": 2})
    content = result.structured_content

    assert content["returned"] == 2
    assert content["memories"][0]["entityName"] == "Memory 2"
