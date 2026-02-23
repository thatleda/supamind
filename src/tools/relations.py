from datetime import UTC, datetime

from fastmcp import FastMCP

from constants import MAX_STRENGTH, MIN_STRENGTH
from db import get_supabase

relations = FastMCP("relations")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@relations.tool
def connections_recall(entity_name: str | None = None) -> dict:
    """Get relationship connections for a memory entity"""
    db = get_supabase()

    if not entity_name:
        rows = (
            db.table("memory_relations")
            .select(
                "id, relation_type, strength,"
                " from_entity:from_entity_id(entity_name),"
                " to_entity:to_entity_id(entity_name)"
            )
            .order("strength", desc=True)
            .execute()
            .data or []
        )
        return {
            "totalConnections": len(rows),
            "connections": [
                {
                    "from": (r.get("from_entity") or {}).get("entity_name"),
                    "to": (r.get("to_entity") or {}).get("entity_name"),
                    "relationType": r["relation_type"],
                    "strength": r["strength"],
                }
                for r in rows
            ],
        }

    entity = (
        db.table("memory_entities")
        .select("id, entity_name")
        .eq("entity_name", entity_name)
        .single()
        .execute()
        .data
    )
    if not entity:
        return {"error": f"Entity not found: {entity_name!r}"}

    rows = (
        db.table("memory_relations")
        .select(
            "id, relation_type, description, strength, metadata,"
            " from_entity:from_entity_id(entity_name),"
            " to_entity:to_entity_id(entity_name)"
        )
        .or_(f"from_entity_id.eq.{entity['id']},to_entity_id.eq.{entity['id']}")
        .order("strength", desc=True)
        .execute()
        .data or []
    )

    return {
        "entityName": entity_name,
        "totalConnections": len(rows),
        "connections": [
            {
                "direction": (
                    "outgoing"
                    if (r.get("from_entity") or {}).get("entity_name") == entity_name
                    else "incoming"
                ),
                "connectedEntity": (
                    (r.get("to_entity") or {}).get("entity_name")
                    if (r.get("from_entity") or {}).get("entity_name") == entity_name
                    else (r.get("from_entity") or {}).get("entity_name")
                ),
                "relationType": r["relation_type"],
                "description": r.get("description"),
                "strength": r["strength"],
                "tags": (r.get("metadata") or {}).get("tags", []),
            }
            for r in rows
        ],
    }


@relations.tool
def connections_remember(
    from_entity_id: str,
    to_entity_id: str,
    relation_type: str,
    description: str,
    strength: float = 0.5,
    tags: list[str] | None = None,
) -> dict:
    """Create a new relationship between memory entities"""
    db = get_supabase()

    from_entity = (
        db.table("memory_entities").select("id, entity_name")
        .eq("id", from_entity_id).single().execute().data
    )
    if not from_entity:
        raise ValueError(f"From entity not found: {from_entity_id!r}")

    to_entity = (
        db.table("memory_entities").select("id, entity_name")
        .eq("id", to_entity_id).single().execute().data
    )
    if not to_entity:
        raise ValueError(f"To entity not found: {to_entity_id!r}")

    row = {
        "from_entity_id": from_entity_id,
        "to_entity_id": to_entity_id,
        "relation_type": relation_type,
        "description": description,
        "strength": _clamp(strength, MIN_STRENGTH, MAX_STRENGTH),
        "metadata": {
            "tags": tags or [],
            "context": {"created_at": datetime.now(UTC).isoformat()},
        },
    }
    result = db.table("memory_relations").insert(row).execute()
    inserted = result.data[0] if result.data else {}

    return {
        "relationId": inserted.get("id"),
        "from": from_entity["entity_name"],
        "to": to_entity["entity_name"],
        "relationType": relation_type,
        "strength": inserted.get("strength"),
    }


@relations.tool
def connections_delete(
    relation_id: str | None = None,
    from_entity_id: str | None = None,
    to_entity_id: str | None = None,
    relation_type: str | None = None,
) -> dict:
    """Delete a relationship between memory entities"""
    db = get_supabase()

    if relation_id:
        result = db.table("memory_relations").delete().eq("id", relation_id).execute()
        count = len(result.data or [])
        return {"deleted": count > 0, "count": count}

    if from_entity_id and to_entity_id:
        query = (
            db.table("memory_relations")
            .delete()
            .eq("from_entity_id", from_entity_id)
            .eq("to_entity_id", to_entity_id)
        )
        if relation_type:
            query = query.eq("relation_type", relation_type)
        result = query.execute()
        count = len(result.data or [])
        return {"deleted": count > 0, "count": count}

    return {"error": "Provide relation_id, or both from_entity_id and to_entity_id"}
