from fastmcp.server.auth.providers.github import GitHubProvider


class RestrictedGitHubProvider:
    """GitHub auth wrapper that only authorizes a single GitHub account."""

    def __init__(self, *, allowed_login: str, **kwargs):
        self._allowed_login = allowed_login.strip().lower()
        self.provider = GitHubProvider(**kwargs)

    def __getattr__(self, name: str):
        return getattr(self.provider, name)

    async def verify_token(self, token: str):
        result = await self.provider.verify_token(token)
        if result is None:
            return None
        login = str(result.claims.get("login") or "").lower()
        if login != self._allowed_login:
            return None
        return result
