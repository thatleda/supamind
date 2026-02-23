from unittest.mock import MagicMock

from tools.relations import relations


async def test_connections_recall_all(mock_db):
    mock_db.execute.return_value = MagicMock(data=[
        {
            "id": "rel-1",
            "relation_type": "influenced_by",
            "strength": 0.9,
            "from_entity": {"entity_name": "Matt"},
            "to_entity": {"entity_name": "Leda Wolf"},
        }
    ])

    result = await relations.call_tool("connections_recall", {})
    content = result.structured_content

    assert content["totalConnections"] == 1
    assert content["connections"][0]["from"] == "Matt"
    assert content["connections"][0]["to"] == "Leda Wolf"
    assert content["connections"][0]["relationType"] == "influenced_by"


async def test_connections_recall_for_entity(mock_db):
    entity_response = MagicMock(data={"id": "uuid-matt", "entity_name": "Matt"})
    relations_response = MagicMock(data=[
        {
            "id": "rel-1",
            "relation_type": "mentored_by",
            "description": "Engineering guidance",
            "strength": 0.95,
            "metadata": {"tags": ["core"]},
            "from_entity": {"entity_name": "Matt"},
            "to_entity": {"entity_name": "Leda Wolf"},
        }
    ])

    mock_db.execute.side_effect = [entity_response, relations_response]

    result = await relations.call_tool("connections_recall", {"entity_name": "Matt"})
    content = result.structured_content

    assert content["entityName"] == "Matt"
    assert content["totalConnections"] == 1
    conn = content["connections"][0]
    assert conn["direction"] == "outgoing"
    assert conn["connectedEntity"] == "Leda Wolf"
    assert conn["tags"] == ["core"]


async def test_connections_recall_entity_not_found(mock_db):
    mock_db.execute.return_value = MagicMock(data=None)

    result = await relations.call_tool("connections_recall", {"entity_name": "Ghost"})
    assert "error" in result.structured_content


async def test_connections_remember_creates_relation(mock_db):
    from_entity = MagicMock(data={"id": "uuid-a", "entity_name": "Entity A"})
    to_entity = MagicMock(data={"id": "uuid-b", "entity_name": "Entity B"})
    insert_result = MagicMock(data=[{
        "id": "rel-new",
        "strength": 0.7,
    }])

    mock_db.execute.side_effect = [from_entity, to_entity, insert_result]

    result = await relations.call_tool("connections_remember", {
        "from_entity_id": "uuid-a",
        "to_entity_id": "uuid-b",
        "relation_type": "relates_to",
        "description": "They are connected",
        "strength": 0.7,
    })
    content = result.structured_content

    assert content["from"] == "Entity A"
    assert content["to"] == "Entity B"
    assert content["relationType"] == "relates_to"
    assert content["relationId"] == "rel-new"


async def test_connections_delete_by_relation_id(mock_db):
    mock_db.execute.return_value = MagicMock(data=[{"id": "rel-1"}])

    result = await relations.call_tool("connections_delete", {"relation_id": "rel-1"})
    content = result.structured_content

    assert content["deleted"] is True
    assert content["count"] == 1


async def test_connections_delete_by_entity_pair(mock_db):
    mock_db.execute.return_value = MagicMock(data=[{"id": "rel-1"}, {"id": "rel-2"}])

    result = await relations.call_tool("connections_delete", {
        "from_entity_id": "uuid-a",
        "to_entity_id": "uuid-b",
    })
    content = result.structured_content

    assert content["deleted"] is True
    assert content["count"] == 2


async def test_connections_delete_returns_error_without_sufficient_params():
    result = await relations.call_tool("connections_delete", {})
    assert "error" in result.structured_content
