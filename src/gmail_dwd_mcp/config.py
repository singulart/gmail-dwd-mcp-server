import os
from dataclasses import dataclass

DEFAULT_GMAIL_API_NUM_RETRIES = 3
DEFAULT_GMAIL_HYDRATE_MAX_CONCURRENCY = 5


def gmail_api_num_retries_from_env() -> int:
    """Gmail API client retries passed to HttpRequest.execute(num_retries=...)."""
    return max(int(os.environ.get("GMAIL_API_NUM_RETRIES", str(DEFAULT_GMAIL_API_NUM_RETRIES))), 0)


def gmail_hydrate_max_concurrency_from_env() -> int:
    """Upper bound on parallel ``threads.get`` calls per batch."""
    return max(
        int(
            os.environ.get(
                "GMAIL_HYDRATE_MAX_CONCURRENCY",
                str(DEFAULT_GMAIL_HYDRATE_MAX_CONCURRENCY),
            )
        ),
        1,
    )


@dataclass(frozen=True)
class Settings:
    """Runtime configuration from environment variables."""

    ssm_parameter_name: str
    aws_region: str | None
    wif_cache_ttl_seconds: int
    gmail_api_num_retries: int
    gmail_hydrate_max_concurrency: int

    @classmethod
    def from_env(cls) -> "Settings":
        name = os.environ.get("GCP_WIF_CREDENTIAL_CONFIG_SSM_PARAMETER")
        if not name:
            raise RuntimeError(
                "GCP_WIF_CREDENTIAL_CONFIG_SSM_PARAMETER must be set to the SSM parameter name "
                "holding the Google Workload Identity Federation JSON config."
            )
        ttl = int(os.environ.get("GMAIL_WIF_CACHE_TTL_SECONDS", "3600"))
        return cls(
            ssm_parameter_name=name,
            aws_region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
            wif_cache_ttl_seconds=max(ttl, 0),
            gmail_api_num_retries=gmail_api_num_retries_from_env(),
            gmail_hydrate_max_concurrency=gmail_hydrate_max_concurrency_from_env(),
        )


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    # Required to read HTML signatures from users.settings.sendAs.
    "https://www.googleapis.com/auth/gmail.settings.basic",
]
