import asyncio
import json
import re
import time
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import jsonschema
import ollama

from app.config import settings
from app.logging_config import fields, get_logger
from app.services.ai_settings import PROVIDERS, AIConfig, load_ai_config
from app.services.ai_usage import record_ai_usage

_provider_slots = asyncio.Semaphore(max(1, settings.AI_MAX_CONCURRENT_REQUESTS))
_rate_gate = asyncio.Lock()
_last_provider_request = 0.0
logger = get_logger("ai")


class AIProviderHTTPError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int,
        retry_after_seconds: int | None = None,
        code: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        # Provider-specific error code, e.g. Groq's "tool_use_failed".
        self.code = code


def _retry_after_seconds(response: httpx.Response, error: dict[str, Any]) -> int | None:
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return max(1, min(3600, int(float(retry_after))))
        except ValueError:
            try:
                return max(1, min(3600, int(parsedate_to_datetime(retry_after).timestamp() - time.time())))
            except (TypeError, ValueError, OverflowError):
                pass
    metadata = error.get("metadata")
    metadata_headers = metadata.get("headers", {}) if isinstance(metadata, dict) else {}
    if not isinstance(metadata_headers, dict):
        metadata_headers = {}
    reset = response.headers.get("x-ratelimit-reset") or metadata_headers.get("X-RateLimit-Reset") or metadata_headers.get("x-ratelimit-reset")
    if reset:
        try:
            reset_value = float(reset)
            reset_epoch = reset_value / 1000 if reset_value > 10_000_000_000 else reset_value
            return max(1, min(3600, int(reset_epoch - time.time()) + 2))
        except (TypeError, ValueError):
            return None
    return None


def _usage_counts(data: dict[str, Any]) -> tuple[int, int]:
    """Extract input/output tokens from OpenAI, Anthropic, or Google shapes."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        usage = data.get("usageMetadata")
    if not isinstance(usage, dict):
        return (0, 0)
    source = usage.get("tokens") if isinstance(usage.get("tokens"), dict) else usage
    if not isinstance(source, dict):
        return (0, 0)
    input_tokens = 0
    output_tokens = 0
    for key in ("prompt_tokens", "input_tokens", "promptTokenCount"):
        value = source.get(key)
        if isinstance(value, int):
            input_tokens = value
            break
    for key in ("completion_tokens", "output_tokens", "candidatesTokenCount"):
        value = source.get(key)
        if isinstance(value, int):
            output_tokens = value
            break
    return (input_tokens, output_tokens)


def _token_usage(data: dict[str, Any]) -> str:
    """Render provider token usage in one comparable shape across APIs."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        usage = data.get("usageMetadata")
    if not isinstance(usage, dict):
        return "not reported"
    # Cohere nests real counts under usage.tokens next to its billed units.
    source = usage.get("tokens") if isinstance(usage.get("tokens"), dict) else usage
    if not isinstance(source, dict):
        return "not reported"

    def number(*keys: str) -> int | None:
        for container in (source, usage):
            for key in keys:
                value = container.get(key)
                if isinstance(value, (int, float)):
                    return int(value)
        return None

    input_tokens = number("input_tokens", "prompt_tokens", "promptTokenCount")
    output_tokens = number("output_tokens", "completion_tokens", "candidatesTokenCount")
    total_tokens = number("total_tokens", "totalTokenCount")
    cached_tokens = number("cached_tokens", "cache_read_input_tokens", "cachedContentTokenCount")
    details = usage.get("prompt_tokens_details")
    if cached_tokens is None and isinstance(details, dict) and isinstance(details.get("cached_tokens"), (int, float)):
        cached_tokens = int(details["cached_tokens"])
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return "not reported"
    return fields(
        in_tokens=input_tokens,
        out_tokens=output_tokens,
        total_tokens=total_tokens if total_tokens is not None else (input_tokens or 0) + (output_tokens or 0),
        cached_tokens=cached_tokens,
    )


def _preview(text: str, limit: int = 240) -> str:
    """One-line excerpt for diagnosing malformed provider responses."""
    collapsed = " ".join(text.split())
    return collapsed[:limit] + ("…" if len(collapsed) > limit else "")


def _http_error_message(
    provider: str,
    status_code: int,
    limit_source: str | None,
    retry_after: int | None,
    provider_message: str | None = None,
) -> str:
    if provider == "openrouter" and status_code == 429:
        if limit_source == "openrouter_free_tier_daily":
            return "OpenRouter's daily free-model allowance is exhausted. Try again after it resets, or select a paid model/provider."
        if limit_source == "openrouter_free_tier_per_minute":
            if retry_after:
                return f"OpenRouter's shared free-model request limit was reached. Wait about {retry_after} seconds, then try again."
            return "OpenRouter's shared free-model request limit was reached. Wait for the limit window to reset, then try again."
        if limit_source == "upstream_provider_shared_pool":
            return "The selected model's provider is temporarily at capacity. Try again later or choose another model."
        return "OpenRouter rate-limited this request. Wait a little and try again, or choose another model."
    if status_code == 429:
        return f"{provider} rate-limited this request. Wait a little and try again."
    message = f"{provider} returned HTTP {status_code}."
    # The provider's own explanation is the only way to diagnose a 4xx, so keep it.
    return f"{message} {provider_message}" if provider_message else message


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["character", "location", "item", "world_rule", "worldbuilding", "power_system", "plot_thread"]},
                    # Bounds keep a small local model from looping inside one
                    # string until the output budget truncates the JSON.
                    "name": {"type": "string", "maxLength": 160},
                    "description": {"type": "string", "maxLength": 1200},
                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                    "source_quote": {"type": "string", "maxLength": 800},
                },
                "required": ["category", "name", "description", "confidence", "source_quote"],
                "additionalProperties": False,
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "draft_line": {"type": "integer", "minimum": 1},
                    "draft_quote": {"type": "string", "maxLength": 600},
                    "evidence_id": {"type": "string", "maxLength": 80},
                    "earlier_quote": {"type": "string", "maxLength": 1200},
                    "explanation": {"type": "string", "maxLength": 500},
                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "required": ["draft_line", "draft_quote", "evidence_id", "earlier_quote", "explanation", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["entries", "findings"],
    "additionalProperties": False,
}

# Each task asks for one array only. Sending the combined schema made the model
# fill the unused array too, which cost output tokens and latency on every call.
ENTRIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"entries": ANALYSIS_SCHEMA["properties"]["entries"]},
    "required": ["entries"],
    "additionalProperties": False,
}

FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"findings": ANALYSIS_SCHEMA["properties"]["findings"]},
    "required": ["findings"],
    "additionalProperties": False,
}


def embed_texts(texts: list[str], task: str = "document") -> list[list[float]]:
    if not texts:
        return []
    client = ollama.Client(host=settings.OLLAMA_BASE_URL)
    if settings.EMBEDDING_MODEL.startswith("nomic-embed-text"):
        prefix = "search_query: " if task == "query" else "search_document: "
        texts = [prefix + text for text in texts]
    elif settings.EMBEDDING_MODEL.startswith("qwen3-embedding") and task == "query":
        texts = [
            "Instruct: Retrieve earlier story passages that establish facts relevant to this scene.\nQuery: " + text
            for text in texts
        ]
    vectors: list[list[float]] = []
    started = time.monotonic()
    for start in range(0, len(texts), 8):
        batch_input = texts[start : start + 8]
        if settings.EMBEDDING_MODEL.startswith("qwen3-embedding"):
            response = client.embed(
                model=settings.EMBEDDING_MODEL,
                input=batch_input,
                dimensions=settings.EMBEDDING_DIMENSIONS,
            )
        else:
            response = client.embed(model=settings.EMBEDDING_MODEL, input=batch_input)
        batch = getattr(response, "embeddings", None)
        if batch is None:
            batch = response.get("embeddings", [])
        if len(batch) != len(batch_input):
            raise RuntimeError("Ollama returned an unexpected number of embeddings.")
        if any(len(vector) != settings.EMBEDDING_DIMENSIONS for vector in batch):
            raise RuntimeError(
                "Embedding dimensions do not match EMBEDDING_DIMENSIONS. "
                "The configured Ollama model and pgvector column must use the same dimension."
            )
        vectors.extend([[float(value) for value in vector] for vector in batch])
    logger.info(
        "[embed] done %s",
        fields(
            model=settings.EMBEDDING_MODEL,
            task=task,
            texts=len(texts),
            dimensions=settings.EMBEDDING_DIMENSIONS,
            elapsed=f"{time.monotonic() - started:.2f}s",
        ),
    )
    return vectors


def embed_queries(texts: list[str]) -> list[list[float]]:
    return embed_texts(texts, task="query")


def _gemini_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_gemini_schema(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _gemini_schema(item)
            for key, item in value.items()
            if key not in {"additionalProperties", "minimum", "maximum"}
        }
    return value


def _cohere_schema(value: Any) -> Any:
    """Remove JSON Schema keywords Cohere Structured Outputs does not support."""
    if isinstance(value, list):
        return [_cohere_schema(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _cohere_schema(item)
            for key, item in value.items()
            if key not in {"minimum", "maximum"}
        }
    return value


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        value = "\n".join(
            part.get("text", "")
            for part in value
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    if not isinstance(value, str):
        raise TypeError("The response did not contain JSON text.")

    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip(), flags=re.IGNORECASE)
    try:
        # Small local models occasionally emit a literal newline or tab inside a
        # string. That is invalid JSON but obvious to repair, and rejecting the
        # whole scene for it trains writers to ignore local checks.
        result = json.loads(content, strict=False)
    except json.JSONDecodeError:
        # Some compatible endpoints wrap JSON in a short preamble despite JSON mode.
        start = content.find("{")
        if start < 0:
            raise
        result, _ = json.JSONDecoder(strict=False).raw_decode(content[start:])
    if not isinstance(result, dict):
        raise TypeError("The response JSON was not an object.")
    return result


def _analysis_result(response_data: dict[str, Any], protocol: str) -> dict[str, Any]:
    try:
        if protocol == "anthropic":
            tool_use = next(item for item in response_data["content"] if item.get("type") == "tool_use")
            result = tool_use["input"]
        elif protocol == "google":
            parts = response_data["candidates"][0]["content"]["parts"]
            function_call = next(part["functionCall"] for part in parts if "functionCall" in part)
            result = function_call["args"]
        elif protocol == "cohere":
            result = _json_object(response_data["message"].get("content"))
        elif protocol == "cohere_compat":
            message = response_data["choices"][0]["message"]
            result = _json_object(message.get("content"))
        else:
            message = response_data["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                arguments = tool_calls[0]["function"]["arguments"]
                result = _json_object(arguments)
            else:
                result = _json_object(message.get("content"))
    except (KeyError, IndexError, TypeError, StopIteration, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "The selected AI provider did not return valid structured JSON. "
            "Check that the selected model supports JSON or tool responses."
        ) from exc
    if not isinstance(result, dict):
        raise RuntimeError("The selected AI provider returned an unexpected analysis format.")
    return result



async def _ollama_structured(
    config: AIConfig,
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    *,
    purpose: str,
    schema_name: str,
    call_id: str,
    started: float,
    timeout_seconds: float,
    user_id: UUID,
    story_id: UUID | None,
) -> dict[str, Any]:
    """Call Ollama's JSON-schema-constrained chat endpoint.

    Model output is untrusted input: the schema is enforced again in Python
    because a small model can still emit a plausible object with a missing key.
    """
    endpoint = f"{config.base_url.rstrip('/')}/api/chat"
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": schema,
        "options": {
            "temperature": 0.1,
            "num_ctx": settings.OLLAMA_NUM_CTX,
            "num_predict": settings.OLLAMA_NUM_PREDICT,
        },
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
    }
    last_error: Exception | None = None
    for attempt in range(2):
        request_started = time.monotonic()
        try:
            async with _provider_slots:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout_seconds, connect=15)
                ) as client:
                    response = await client.post(endpoint, json=payload)
        except httpx.TimeoutException as exc:
            logger.warning(
                "[%s] timeout   %s",
                call_id,
                fields(
                    purpose=purpose,
                    limit=f"{timeout_seconds:g}s",
                    error=type(exc).__name__,
                ),
            )
            raise AIProviderHTTPError(
                f"Ollama did not answer within {timeout_seconds:g} seconds. "
                "Check that the local model is loaded, or choose a smaller model.",
                504,
            ) from exc
        except httpx.TransportError as exc:
            logger.warning(
                "[%s] unreachable %s",
                call_id,
                fields(
                    purpose=purpose,
                    base_url=config.base_url,
                    error=type(exc).__name__,
                ),
            )
            raise AIProviderHTTPError(
                f"Ollama is not reachable at {config.base_url}. "
                "Start Ollama and check the base URL in AI settings.",
                503,
            ) from exc

        latency = time.monotonic() - request_started
        if response.is_error:
            try:
                detail = str(response.json().get("error") or "")
            except (ValueError, AttributeError):
                detail = ""
            message = f"Ollama returned HTTP {response.status_code}."
            if detail:
                message = f"{message} {detail[:400]}"
            logger.warning(
                "[%s] rejected  %s",
                call_id,
                fields(
                    purpose=purpose,
                    status=response.status_code,
                    latency=f"{latency:.2f}s",
                    provider_message=detail[:400] or None,
                ),
            )
            raise AIProviderHTTPError(message, response.status_code)

        content = ""
        try:
            data = response.json()
            content = data["message"]["content"]
            result = _json_object(content)
            jsonschema.validate(instance=result, schema=schema)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
            last_error = exc
            logger.warning(
                "[%s] invalid   %s",
                call_id,
                fields(
                    purpose=purpose,
                    attempt=attempt + 1,
                    schema=schema_name,
                    latency=f"{latency:.2f}s",
                    reason=str(exc)[:300],
                    preview=_preview(content) if content else None,
                ),
            )
            if attempt == 0:
                continue
            raise RuntimeError(
                "Ollama returned JSON that did not match the requested schema. "
                "Try again, or choose a stronger local model."
            ) from exc

        prompt_tokens = data.get("prompt_eval_count")
        output_tokens = data.get("eval_count")
        await record_ai_usage(
            user_id=user_id,
            story_id=story_id,
            purpose=purpose,
            provider=config.provider,
            model=config.model,
            input_tokens=int(prompt_tokens or 0),
            output_tokens=int(output_tokens or 0),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        logger.info(
            "[%s] done      %s",
            call_id,
            fields(
                purpose=purpose,
                status=response.status_code,
                schema=schema_name,
                model=config.model,
                latency=f"{latency:.2f}s",
                total=f"{time.monotonic() - started:.2f}s",
                in_tokens=prompt_tokens,
                out_tokens=output_tokens,
                total_tokens=(prompt_tokens or 0) + (output_tokens or 0)
                if prompt_tokens is not None or output_tokens is not None
                else None,
                tokens_per_second=round(output_tokens / latency, 1)
                if output_tokens and latency > 0
                else None,
            ),
        )
        return result
    raise RuntimeError("Ollama did not return usable JSON.") from last_error


async def structured_ai_json(
    system_prompt: str,
    user_prompt: str,
    user_id: UUID,
    purpose: str = "analysis",
    schema: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
    schema_name: str | None = None,
    story_id: UUID | None = None,
) -> dict[str, Any]:
    """Call the user's selected provider and return its structured analysis."""
    started = time.monotonic()
    call_id = uuid4().hex[:6]
    payload_schema = schema or ANALYSIS_SCHEMA
    config = await load_ai_config(user_id)
    preset = PROVIDERS[config.provider]
    effective_timeout = timeout_seconds or settings.OPENROUTER_TIMEOUT_SECONDS
    logger.info(
        "[%s] start     %s",
        call_id,
        fields(
            purpose=purpose,
            provider=config.provider,
            model=config.model,
            protocol=config.protocol,
            schema=schema_name or "+".join(str(key) for key in payload_schema.get("properties", {})),
            system_chars=len(system_prompt),
            prompt_chars=len(user_prompt),
            timeout=f"{effective_timeout:g}s",
        ),
    )
    endpoint = ""
    headers: dict[str, str]
    payload: dict[str, Any]
    params: dict[str, str] | None = None
    description = "Return the requested manuscript analysis as structured data."

    if config.protocol == "ollama":
        return await _ollama_structured(
            config,
            system_prompt,
            user_prompt,
            payload_schema,
            purpose=purpose,
            schema_name=schema_name or "+".join(str(key) for key in payload_schema.get("properties", {})),
            call_id=call_id,
            started=started,
            timeout_seconds=effective_timeout,
            user_id=user_id,
            story_id=story_id,
        )

    if config.protocol == "anthropic":
        endpoint = f"{config.base_url.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": config.model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "tools": [{"name": "submit_analysis", "description": description, "input_schema": payload_schema}],
            "tool_choice": {"type": "tool", "name": "submit_analysis"},
            "temperature": 0.1,
        }
    elif config.protocol == "google":
        model_path = quote(config.model, safe="-._:")
        endpoint = f"{config.base_url.rstrip('/')}/models/{model_path}:generateContent"
        headers = {"content-type": "application/json", "x-goog-api-key": config.api_key}
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "tools": [{"functionDeclarations": [{
                "name": "submit_analysis",
                "description": description,
                "parameters": _gemini_schema(payload_schema),
            }]}],
            "toolConfig": {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": ["submit_analysis"]}},
            "generationConfig": {"temperature": 0.1},
        }
    elif config.protocol == "cohere":
        endpoint = f"{config.base_url.rstrip('/')}/chat"
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object", "schema": _cohere_schema(payload_schema)},
            "max_tokens": 4000,
            "temperature": 0.1,
        }
    elif config.protocol == "cohere_compat":
        endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object", "schema": _cohere_schema(payload_schema)},
            "max_tokens": 4000,
            "temperature": 0.1,
        }
    else:
        endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        if config.provider == "openrouter":
            headers.update({"HTTP-Referer": "http://localhost:3000", "X-Title": "Stillroom Writing Studio"})
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "tools": [{
                "type": "function",
                "function": {"name": "submit_analysis", "description": description, "parameters": payload_schema},
            }],
            "tool_choice": {"type": "function", "function": {"name": "submit_analysis"}},
            "temperature": 0.1,
        }

    global _last_provider_request
    min_interval = 4.0 if config.provider == "openrouter" else 0.2
    queued_from = time.monotonic()
    # Space out request starts (OpenRouter's free-model cap is shared across all
    # free models and can include traffic outside this app), then allow a few
    # requests to wait on the provider at the same time.
    async with _rate_gate:
        wait_seconds = min_interval - (time.monotonic() - _last_provider_request)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        _last_provider_request = time.monotonic()
    async with _provider_slots:
        queued = time.monotonic() - queued_from
        request_started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(effective_timeout, connect=15)) as client:
                response = await client.post(endpoint, headers=headers, json=payload, params=params)
        except httpx.TimeoutException as exc:
            logger.warning(
                "[%s] timeout   %s",
                call_id,
                fields(
                    purpose=purpose,
                    waited=f"{queued:.2f}s",
                    limit=f"{effective_timeout:g}s",
                    error=type(exc).__name__,
                ),
            )
            raise AIProviderHTTPError(
                f"The AI provider did not answer within {effective_timeout:g} seconds. "
                "Try again, or choose a faster model in AI settings.",
                504,
            ) from exc
        except httpx.TransportError as exc:
            logger.warning(
                "[%s] unreachable %s",
                call_id,
                fields(
                    purpose=purpose,
                    provider=config.provider,
                    error=type(exc).__name__,
                ),
            )
            raise AIProviderHTTPError(
                f"Could not reach {config.provider}. Check your network connection "
                "and the provider base URL in AI settings.",
                503,
            ) from exc
        latency = time.monotonic() - request_started
    if queued >= 0.05:
        logger.info(
            "[%s] queue     %s",
            call_id,
            fields(purpose=purpose, waited=f"{queued:.2f}s", min_interval=f"{min_interval:g}s"),
        )
    if response.is_error:
        try:
            error_data = response.json().get("error", {})
        except (ValueError, AttributeError):
            error_data = {}
        if not isinstance(error_data, dict):
            error_data = {}
        metadata = error_data.get("metadata")
        limit_source = metadata.get("limit_source") if isinstance(metadata, dict) else None
        retry_after = _retry_after_seconds(response, error_data) if response.status_code == 429 else None
        provider_code = error_data.get("code") or error_data.get("type")
        raw_message = error_data.get("message")
        provider_message = " ".join(str(raw_message).split())[:400] if raw_message else None
        message = _http_error_message(
            config.provider, response.status_code, limit_source, retry_after, provider_message
        )
        # Log only provider, status, rate-limit category, and the provider's own
        # error text (never request bodies or credentials).
        logger.warning(
            "[%s] rejected  %s",
            call_id,
            fields(
                purpose=purpose,
                status=response.status_code,
                latency=f"{latency:.2f}s",
                limit_source=limit_source or "unknown",
                code=provider_code,
                retry_after=retry_after,
                provider_message=provider_message,
                message=message,
            ),
        )
        raise AIProviderHTTPError(
            message,
            response.status_code,
            retry_after,
            str(provider_code) if provider_code else None,
        )
    try:
        response_data = response.json()
    except ValueError as exc:
        logger.error(
            "[%s] bad_json  %s",
            call_id,
            fields(
                purpose=purpose,
                status=response.status_code,
                latency=f"{latency:.2f}s",
                response_chars=len(response.text),
                preview=_preview(response.text),
            ),
        )
        raise RuntimeError(f"{preset.label} returned invalid JSON.") from exc
    logger.debug("[%s] raw       %s", call_id, response.text)
    try:
        result = _analysis_result(response_data, config.protocol)
    except Exception as exc:
        logger.error(
            "[%s] parse     %s",
            call_id,
            fields(
                purpose=purpose,
                ok=False,
                reason=str(exc),
                latency=f"{latency:.2f}s",
                response_chars=len(response.text),
                preview=_preview(response.text),
            ),
        )
        raise
    logger.info(
        "[%s] done      %s",
        call_id,
        fields(
            purpose=purpose,
            status=response.status_code,
            latency=f"{latency:.2f}s",
            total=f"{time.monotonic() - started:.2f}s",
            keys="+".join(str(key) for key in result),
        ),
    )
    logger.info("[%s] usage     %s", call_id, _token_usage(response_data))
    input_tokens, output_tokens = _usage_counts(response_data)
    await record_ai_usage(
        user_id=user_id,
        story_id=story_id,
        purpose=purpose,
        provider=config.provider,
        model=config.model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return result
