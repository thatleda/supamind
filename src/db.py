import os

from dotenv import load_dotenv
from supabase import Client, create_client

_client: Client | None = None  # pylint: disable=invalid-name


def get_supabase() -> Client:
    global _client  # pylint: disable=global-statement
    if _client is None:
        load_dotenv()
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _client
