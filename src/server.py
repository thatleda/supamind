from fastmcp import FastMCP

from tools.consciousness import consciousness
from tools.memory import memory
from tools.relations import relations

# GitHub OAuth support (GitHubOAuthProvider) is planned for a future FastMCP release.
# See README for HTTP deployment security options.
mcp = FastMCP("supamind")
mcp.mount(consciousness)
mcp.mount(memory)
mcp.mount(relations)


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
