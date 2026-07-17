import os

from dotenv import load_dotenv
from fastmcp import FastMCP

from .tools.consciousness import consciousness
from .tools.memory import memory
from .tools.relations import relations

load_dotenv()

mcp = FastMCP("supamind")
mcp.mount(consciousness)
mcp.mount(memory)
mcp.mount(relations)


def run() -> None:
    github_client_id = os.environ.get("GITHUB_CLIENT_ID")

    if not github_client_id:
        mcp.run()
        return

    from .auth import RestrictedGitHubProvider  # pylint: disable=import-outside-toplevel

    mcp.auth = RestrictedGitHubProvider(
        client_id=github_client_id,
        client_secret=os.environ["GITHUB_CLIENT_SECRET"],
        base_url=os.environ["SUPAMIND_BASE_URL"],
        allowed_login=os.environ["GITHUB_ALLOWED_LOGIN"],
    )
    mcp.run(
        transport="http",
        host="0.0.0.0",  # nosec B104
        port=int(os.environ.get("PORT", 8000)),
    )


if __name__ == "__main__":
    run()
