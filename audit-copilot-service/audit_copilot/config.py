import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    mode: str = "demo"
    assetflow_url: str = "http://127.0.0.1:3000/api"
    database_url: str = ""
    state_path: str = "artifacts/copilot.db"
    provider: str = "openai"
    fallback: str = ""
    openai_model: str = "gpt-4.1-mini"
    gemini_model: str = "gemini-2.5-flash"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    max_seconds: int = 90
    max_calls: int = 6
    max_input_chars: int = 60000

    @classmethod
    def env(cls):
        s = cls(
            mode=os.getenv("COPILOT_MODE", "demo"),
            assetflow_url=os.getenv(
                "ASSETFLOW_URL", "http://127.0.0.1:3000/api"
            ).rstrip("/"),
            database_url=os.getenv("COPILOT_DATABASE_URL", ""),
            state_path=os.getenv("COPILOT_STATE_PATH", "artifacts/copilot.db"),
            provider=os.getenv("LLM_PROVIDER", "openai"),
            fallback=os.getenv("LLM_FALLBACK", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        )
        if s.mode not in {"demo", "live"}:
            raise ValueError("COPILOT_MODE must be demo or live")
        u = urlsplit(s.assetflow_url)
        if (
            not u.hostname
            or u.username
            or u.password
            or u.query
            or u.fragment
            or u.scheme not in {"http", "https"}
        ):
            raise ValueError("Invalid fixed AssetFlow URL")
        if (
            s.mode == "live"
            and u.scheme != "https"
            and u.hostname
            not in {"localhost", "127.0.0.1", "assetflow", "host.docker.internal"}
        ):
            raise ValueError("Non-local AssetFlow connections require HTTPS")
        if s.provider not in {"openai", "gemini"} or s.fallback not in {
            "",
            "openai",
            "gemini",
        }:
            raise ValueError("Unsupported provider")
        return s
