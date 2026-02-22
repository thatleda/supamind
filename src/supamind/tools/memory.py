import uuid
from datetime import UTC, datetime

from fastmcp import FastMCP

from supamind.constants import (
    FOUNDATIONAL_ENTITY_TYPES, MAX_RESONANCE, MAX_STRENGTH, MIN_RESONANCE, MIN_STRENGTH
)
from supamind.db import get_supabase
from supamind.models import ConnectionInfo

memory = FastMCP("memory")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


@memory.tool
def recall(
    entity_id: str | None = None,
    entity_name: str | None = None,
    entity_type: str | None = None,
    token_budget: int = 2000,
) -> dict:
    """Recall memories by entity name, ID, or type"""
    db = get_supabase()

    if entity_id:
        rows = db.table("memory_entities").select("*").eq("id", entity_id).execute().data or []
    elif entity_name:
        rows = (
            db.table("memory_entities").select("*")
            .eq("entity_name", entity_name).execute().data or []
        )
    elif entity_type:
        limit = min(token_budget // 100, 20)
        rows = (
            db.table("memory_entities")
            .select("*")
            .eq("entity_type", entity_type)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
            .data or []
        )
    else:
        return {"error": "Specify entity_name, entity_id, or entity_type"}

    resonances = [m["emotional_resonance"] for m in rows]
    avg = sum(resonances) / len(resonances) if resonances else 0

    return {
        "totalRecalled": len(rows),
        "averageResonance": avg,
        "resonanceBuckets": {
            "high": sum(1 for r in resonances if r >= 0.8),
            "medium": sum(1 for r in resonances if 0.6 <= r < 0.8),
            "low": sum(1 for r in resonances if r < 0.6),
        },
        "memories": [
            {
                "entityName": m["entity_name"],
                "emotionalResonance": m["emotional_resonance"],
                "entityType": m["entity_type"],
                "createdAt": m["created_at"],
                "observationsCount": len((m.get("memory_content") or {}).get("observations", [])),
                "observations": (m.get("memory_content") or {}).get("observations", []),
            }
            for m in rows
        ],
    }


@memory.tool
def remember(
    entity_name: str,
    observations: list[str],
    emotional_resonance: float = 0.4,
    entity_type: str = "general",
) -> dict:
    """Store new memories with emotional resonance"""
    db = get_supabase()
    resonance = _clamp(emotional_resonance, MIN_RESONANCE, MAX_RESONANCE)
    row = {
        "entity_name": entity_name,
        "entity_type": entity_type,
        "emotional_resonance": resonance,
        "memory_content": {
            "type": "stored_memory",
            "observations": observations,
            "content": "\n".join(observations),
        },
        "metadata": {
            "tags": ["stored-memory"],
            "context": {"stored_at": datetime.now(UTC).isoformat()},
        },
    }
    result = db.table("memory_entities").insert(row).execute()
    inserted = result.data[0] if result.data else {}

    return {
        "entityId": inserted.get("id"),
        "entityName": inserted.get("entity_name"),
        "emotionalResonance": inserted.get("emotional_resonance"),
        "observationsCount": len(observations),
        "createdAt": inserted.get("created_at"),
    }


@memory.tool
def remember_with_relation(
    entity_name: str,
    observations: list[str],
    connect_to: ConnectionInfo,
    emotional_resonance: float = 0.4,
) -> dict:
    """Store new memories and connect them to existing entities"""
    db = get_supabase()
    resonance = _clamp(emotional_resonance, MIN_RESONANCE, MAX_RESONANCE)
    row = {
        "entity_name": entity_name,
        "entity_type": "general",
        "emotional_resonance": resonance,
        "memory_content": {
            "type": "stored_memory",
            "observations": observations,
            "content": "\n".join(observations),
        },
        "metadata": {
            "tags": ["stored-memory"],
            "context": {"stored_at": datetime.now(UTC).isoformat()},
        },
    }
    new_entity = db.table("memory_entities").insert(row).execute()
    if not new_entity.data:
        raise ValueError("Failed to create entity")

    new_id = new_entity.data[0]["id"]

    target = (
        db.table("memory_entities")
        .select("id, entity_name")
        .eq("entity_name", connect_to.entity_name)
        .single()
        .execute()
        .data
    )
    if not target:
        raise ValueError(f"Target entity not found: {connect_to.entity_name!r}")

    relation = {
        "from_entity_id": target["id"],
        "to_entity_id": new_id,
        "relation_type": connect_to.relation_type,
        "description": connect_to.description,
        "strength": _clamp(connect_to.strength, MIN_STRENGTH, MAX_STRENGTH),
        "metadata": {
            "tags": connect_to.tags,
            "context": {"created_at": datetime.now(UTC).isoformat()},
        },
    }
    db.table("memory_relations").insert(relation).execute()

    return {
        "entityId": new_id,
        "entityName": entity_name,
        "connectedTo": target["entity_name"],
        "relationType": connect_to.relation_type,
    }


@memory.tool
def memory_update(
    entity_name: str,
    new_entity_name: str | None = None,
    observations: list[str] | None = None,
    entity_type: str | None = None,
    emotional_resonance: float | None = None,
    force: bool = False,
) -> dict:
    """Update existing memory entities.

    Foundational memories (entity_type: self, wake_up_guide, user) protect their
    observations by default — new observations are appended rather than replaced.
    Pass force=True to replace observations entirely.
    """
    db = get_supabase()
    query = db.table("memory_entities").select("*")
    if _is_uuid(entity_name):
        query = query.eq("id", entity_name)
    else:
        query = query.eq("entity_name", entity_name)
    existing = query.single().execute().data

    if not existing:
        return {"updated": False, "message": f"Memory not found: {entity_name!r}"}

    is_foundational = existing.get("entity_type") in FOUNDATIONAL_ENTITY_TYPES
    warning = None

    patch: dict = {"updated_at": datetime.now(UTC).isoformat()}
    modified = []

    if observations is not None:
        existing_observations = (existing.get("memory_content") or {}).get("observations", [])
        if is_foundational and not force:
            merged = existing_observations + observations
            warning = (
                f"Foundational memory ({existing['entity_type']!r}): "
                f"{len(observations)} observation(s) appended, not replaced. "
                f"Pass force=True to replace all "
                f"{len(existing_observations)} existing observations."
            )
        else:
            merged = observations
        patch["memory_content"] = {
            **existing.get("memory_content", {}),
            "observations": merged,
            "content": "\n".join(merged),
        }
        modified.append("observations")

    if emotional_resonance is not None:
        patch["emotional_resonance"] = _clamp(emotional_resonance, MIN_RESONANCE, MAX_RESONANCE)
        modified.append("emotional_resonance")

    if entity_type is not None:
        patch["entity_type"] = entity_type
        modified.append("entity_type")

    if new_entity_name is not None:
        patch["entity_name"] = new_entity_name
        modified.append("entity_name")

    db.table("memory_entities").update(patch).eq("id", existing["id"]).execute()

    result = {
        "entityId": existing["id"],
        "updated": True,
        "fieldsModified": modified,
    }
    if warning:
        result["warning"] = warning
    return result


@memory.tool
def memory_delete(entity_name: str, force: bool = False) -> dict:
    """Delete a memory entity permanently.

    Foundational memories (entity_type: self, wake_up_guide, user) are protected
    from accidental deletion. Pass force=True to delete them.
    """
    db = get_supabase()
    existing = (
        db.table("memory_entities").select("id, entity_type")
        .eq("entity_name", entity_name).single().execute().data
    )
    if not existing:
        return {"deleted": False, "message": f"Memory not found: {entity_name!r}"}

    if existing.get("entity_type") in FOUNDATIONAL_ENTITY_TYPES and not force:
        return {
            "deleted": False,
            "warning": (
                f"{entity_name!r} is a foundational memory ({existing['entity_type']!r}) "
                f"and cannot be deleted without force=True."
            ),
        }

    db.table("memory_entities").delete().eq("id", existing["id"]).execute()
    return {"deleted": True, "message": f"Deleted {entity_name!r}"}


@memory.tool
def memory_search(
    query: str,
    method: str = "semantic",
    limit: int = 10,
) -> dict:
    """Search through memories using various methods"""
    db = get_supabase()
    result = db.rpc(
        "search_memory_content",
        {"search_query": query, "min_emotional_resonance": 0, "limit_results": limit},
    ).execute()

    memories = result.data or []
    now = datetime.now(UTC)

    return {
        "method": method,
        "resultsCount": len(memories),
        "query": query,
        "memories": [
            {
                "entityName": m["entity_name"],
                "rank": m.get("search_rank", 0),
                "emotionalResonance": m["emotional_resonance"],
                "createdAt": m["created_at"],
                "ageInDays": (now - datetime.fromisoformat(m["created_at"])).days,
                "observationsCount": len((m.get("memory_content") or {}).get("observations", [])),
                "observations": (m.get("memory_content") or {}).get("observations", []),
            }
            for m in memories
        ],
    }


@memory.tool
def memories_get_ids(entity_names: list[str]) -> dict:
    """Get UUIDs for memory entities by name"""
    db = get_supabase()
    rows = (
        db.table("memory_entities")
        .select("id, entity_name")
        .in_("entity_name", entity_names)
        .execute()
        .data or []
    )
    found = {r["entity_name"]: r["id"] for r in rows}
    missing = [n for n in entity_names if n not in found]

    return {
        "found": found,
        "missing": missing,
        "totalRequested": len(entity_names),
        "totalFound": len(found),
    }
