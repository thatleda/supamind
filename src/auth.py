from fastmcp.server.auth.providers.github import GitHubProvider, GitHubTokenVerifier


class AllowlistedGitHubTokenVerifier(GitHubTokenVerifier):
    def __init__(self, *, allowed_login: str, **kwargs):
        super().__init__(**kwargs)
        self._allowed_login = allowed_login.strip().lower()

    async def verify_token(self, token: str):
        result = await super().verify_token(token)
        if result is None:
            return None
        login = str(result.claims.get("login") or "").lower()
        if login != self._allowed_login:
            return None
        return result


class RestrictedGitHubProvider(GitHubProvider):
    """GitHubProvider that only authorizes a single GitHub account."""

    def __init__(self, *, allowed_login: str, **kwargs):
        super().__init__(**kwargs)
        # pylint: disable=protected-access
        self._token_validator = AllowlistedGitHubTokenVerifier(
            allowed_login=allowed_login,
            required_scopes=self._token_validator.required_scopes,
        )
