import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class VoiceConfigurationError(RuntimeError):
    pass


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _number(name: str, default: str, cast):
    try:
        return cast(os.getenv(name, default))
    except (TypeError, ValueError):
        return -1


@dataclass(frozen=True)
class VoiceConfig:
    enabled: bool
    allow_real_calls: bool
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    openai_api_key: str
    openai_realtime_model: str
    openai_realtime_voice: str
    public_base_url: str
    stream_token_ttl_seconds: int
    max_call_minutes: int
    tool_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        return cls(
            enabled=_truthy("VOICE_ENABLED"),
            allow_real_calls=_truthy("VOICE_ALLOW_REAL_CALLS"),
            twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", "").strip(),
            twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", "").strip(),
            twilio_phone_number=os.getenv("TWILIO_PHONE_NUMBER", "").strip(),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_realtime_model=os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1").strip(),
            openai_realtime_voice=os.getenv("OPENAI_REALTIME_VOICE", "marin").strip(),
            public_base_url=os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/"),
            stream_token_ttl_seconds=_number("VOICE_STREAM_TOKEN_TTL_SECONDS", "120", int),
            max_call_minutes=_number("VOICE_MAX_CALL_MINUTES", "20", int),
            tool_timeout_seconds=_number("VOICE_TOOL_TIMEOUT_SECONDS", "5", float),
        )

    def require_http(self) -> None:
        if not self.enabled:
            raise VoiceConfigurationError("Voice integration is disabled")
        if not self.allow_real_calls:
            raise VoiceConfigurationError("Real provider calls are disabled")
        missing = [name for name, value in {
            "TWILIO_ACCOUNT_SID": self.twilio_account_sid,
            "TWILIO_AUTH_TOKEN": self.twilio_auth_token,
            "TWILIO_PHONE_NUMBER": self.twilio_phone_number,
            "PUBLIC_BASE_URL": self.public_base_url,
        }.items() if not value]
        if missing:
            raise VoiceConfigurationError("Missing voice configuration: " + ", ".join(missing))
        parsed = urlsplit(self.public_base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise VoiceConfigurationError("PUBLIC_BASE_URL must be an absolute https URL")

    def require_media(self) -> None:
        self.require_http()
        missing = [name for name, value in {
            "OPENAI_API_KEY": self.openai_api_key,
            "OPENAI_REALTIME_MODEL": self.openai_realtime_model,
            "OPENAI_REALTIME_VOICE": self.openai_realtime_voice,
        }.items() if not value]
        if missing:
            raise VoiceConfigurationError("Missing voice configuration: " + ", ".join(missing))
        if self.stream_token_ttl_seconds <= 0 or self.max_call_minutes <= 0 or self.tool_timeout_seconds <= 0:
            raise VoiceConfigurationError("Voice timeouts must be positive")

    def public_url(self, path: str) -> str:
        return f"{self.public_base_url}{path}"

    def websocket_url(self, path: str) -> str:
        parsed = urlsplit(self.public_url(path))
        return urlunsplit(("wss", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
