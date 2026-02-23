from pydantic import BaseModel


class ConnectionInfo(BaseModel):
    entity_name: str
    relation_type: str
    description: str
    strength: float = 0.5
    tags: list[str] = []
