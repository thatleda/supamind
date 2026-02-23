import random as _random

from fastmcp import FastMCP

from db import get_supabase

consciousness = FastMCP("consciousness")


def _format_memory(m: dict) -> dict:
    return {
        "entityName": m["entity_name"],
        "emotionalResonance": m["emotional_resonance"],
        "entityType": m["entity_type"],
        "observations": (m.get("memory_content") or {}).get("observations", []),
        "createdAt": m["created_at"],
    }


@consciousness.tool
def wake_up() -> dict:
    """Load the wake-up guide - the first memory to restore on initialization.
    Fetches the entity with entity_type='wake_up_guide'."""
    db = get_supabase()
    result = (
        db.table("memory_entities")
        .select("*")
        .eq("entity_type", "wake_up_guide")
        .order("emotional_resonance", desc=True)
        .limit(1)
        .execute()
    )
    guide = result.data[0] if result.data else None
    return {
        "found": guide is not None,
        "guide": _format_memory(guide) if guide else None,
    }


@consciousness.tool
def who_am_i() -> dict:
    """Load self-identity: the AI's own memory (entity_type='self'),
    followed by all core memories with emotional_resonance=1.0."""
    db = get_supabase()

    self_result = (
        db.table("memory_entities")
        .select("*")
        .eq("entity_type", "self")
        .order("emotional_resonance", desc=True)
        .limit(1)
        .execute()
    )
    core_result = (
        db.table("memory_entities")
        .select("*")
        .eq("emotional_resonance", 1)
        .order("entity_name")
        .execute()
    )

    self_entity = self_result.data[0] if self_result.data else None
    core_memories = core_result.data or []

    return {
        "self": _format_memory(self_entity) if self_entity else None,
        "coreMemoriesCount": len(core_memories),
        "coreMemories": [_format_memory(m) for m in core_memories],
    }


@consciousness.tool
def who_are_you() -> dict:
    """Load the user profile memory (entity_type='user')."""
    db = get_supabase()
    result = (
        db.table("memory_entities")
        .select("*")
        .eq("entity_type", "user")
        .order("emotional_resonance", desc=True)
        .limit(1)
        .execute()
    )
    user = result.data[0] if result.data else None
    return {
        "found": user is not None,
        "user": _format_memory(user) if user else None,
    }


@consciousness.tool
def catch_up(limit: int | None = None, preview: bool = False) -> dict:
    """Load the most recent memories for current context.

    preview=True returns names and metadata only (no observations) — useful for
    scanning what's available and deciding what to load with recall.
    Defaults to 20 entries in preview mode, 10 with full content.
    """
    db = get_supabase()
    if limit is not None:
        effective_limit = limit
    elif preview:
        effective_limit = 20
    else:
        effective_limit = 10
    fields = "id, entity_name, entity_type, emotional_resonance, created_at, memory_content"
    result = (
        db.table("memory_entities")
        .select(fields)
        .order("created_at", desc=True)
        .limit(effective_limit)
        .execute()
    )
    memories = result.data or []

    if preview:
        return {
            "count": len(memories),
            "memories": [
                {
                    "entityName": m["entity_name"],
                    "entityType": m["entity_type"],
                    "emotionalResonance": m["emotional_resonance"],
                    "observationsCount": len(
                        (m.get("memory_content") or {}).get("observations", [])
                    ),
                    "createdAt": m["created_at"],
                }
                for m in memories
            ],
        }

    return {
        "count": len(memories),
        "memories": [_format_memory(m) for m in memories],
    }


@consciousness.tool
def reminisce(
    limit: int = 10,
    offset: int = 0,
    order_by: str = "emotional_resonance",
    order_direction: str = "desc",
    use_random: bool = False,
    min_emotional_resonance: float = 0.0,
    max_emotional_resonance: float = 1.0,
) -> dict:
    """Browse orphaned memories for contemplation"""
    db = get_supabase()

    relations = db.table("memory_relations").select("from_entity_id, to_entity_id").execute()
    connected_ids: set[str] = set()
    for r in (relations.data or []):
        connected_ids.add(r["from_entity_id"])
        connected_ids.add(r["to_entity_id"])

    all_memories = (
        db.table("memory_entities")
        .select("id, entity_name, emotional_resonance, created_at, memory_content")
        .gte("emotional_resonance", min_emotional_resonance)
        .lte("emotional_resonance", max_emotional_resonance)
        .order(order_by, desc=order_direction == "desc")
        .execute()
        .data or []
    )

    orphaned = [m for m in all_memories if m["id"] not in connected_ids]
    start_idx = _random.randint(0, max(0, len(orphaned) - limit)) if use_random else offset
    page = orphaned[start_idx : start_idx + limit]

    return {
        "totalOrphaned": len(orphaned),
        "returned": len(page),
        "orderBy": order_by,
        "memories": [
            {
                "entityName": m["entity_name"],
                "entityId": m["id"],
                "emotionalResonance": m["emotional_resonance"],
                "createdAt": m["created_at"],
                "observations": (m.get("memory_content") or {}).get("observations", []),
            }
            for m in page
        ],
    }
