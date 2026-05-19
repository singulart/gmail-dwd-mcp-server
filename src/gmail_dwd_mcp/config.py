import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime configuration from environment variables."""

    ssm_parameter_name: str
    allowed_hosts_ssm_parameter: str | None
    aws_region: str | None
    wif_cache_ttl_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        name = os.environ.get("GMAIL_WIF_SSM_PARAMETER")
        if not name:
            raise RuntimeError(
                "GMAIL_WIF_SSM_PARAMETER must be set to the SSM parameter name "
                "holding the Google Workload Identity Federation JSON config."
            )
        ttl = int(os.environ.get("GMAIL_WIF_CACHE_TTL_SECONDS", "3600"))
        return cls(
            ssm_parameter_name=name,
            allowed_hosts_ssm_parameter=os.environ.get("GMAIL_ALLOWED_HOSTS_SSM_PARAMETER"),
            aws_region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
            wif_cache_ttl_seconds=max(ttl, 0),
        )


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
