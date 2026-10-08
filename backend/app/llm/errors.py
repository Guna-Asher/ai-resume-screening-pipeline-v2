from enum import StrEnum


class LLMFailure(StrEnum):
    """Normalised failure categories. These (never raw responses) go into results.json."""

    # configuration: the LLM layer is "unavailable"
    NOT_CONFIGURED = "not_configured"
    MISSING_API_KEY = "missing_api_key"
    MISSING_MODEL = "missing_model"
    MISSING_BASE_URL = "missing_base_url"
    # runtime: the call "failed"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"
    API_ERROR = "api_error"
    CONNECTION_ERROR = "connection_error"
    INVALID_JSON = "invalid_json"
    SCHEMA_VALIDATION = "schema_validation"
    UNEXPECTED = "unexpected"


CONFIG_FAILURES = frozenset(
    {
        LLMFailure.NOT_CONFIGURED,
        LLMFailure.MISSING_API_KEY,
        LLMFailure.MISSING_MODEL,
        LLMFailure.MISSING_BASE_URL,
    }
)


class LLMError(Exception):
    """Any LLM-layer problem. ``detail`` must be short and free of secrets / response bodies."""

    def __init__(self, category: LLMFailure, detail: str = "") -> None:
        super().__init__(f"{category.value}: {detail}" if detail else category.value)
        self.category = category
        self.detail = detail
