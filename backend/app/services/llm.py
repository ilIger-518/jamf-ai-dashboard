"""LLM provider abstraction for local Ollama and custom OpenAI-compatible APIs."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

UseCase = str


def describe_llm_target(settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    if cfg.ai_provider == "custom":
        return f"custom:{cfg.custom_ai_model}"
    return f"local:{cfg.ollama_model}"


def describe_embedding_target(settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    if cfg.embedding_provider == "custom":
        return f"custom:{cfg.custom_embedding_model}"
    return f"local:{cfg.embedding_model_name}"


def _custom_chat_model(cfg: Settings, use_case: UseCase) -> str:
    if use_case == "scrape":
        return cfg.custom_scrape_model or cfg.custom_ai_model
    return cfg.custom_ai_model


def _custom_api_key(cfg: Settings, use_case: UseCase) -> str:
    if use_case == "chat":
        return cfg.custom_chat_api_key or cfg.custom_ai_api_key
    if use_case == "scrape":
        return cfg.custom_scrape_api_key or cfg.custom_ai_api_key
    if use_case == "embedding":
        return cfg.custom_embedding_api_key or cfg.custom_ai_api_key
    return cfg.custom_ai_api_key


def _validate_custom_config(cfg: Settings, use_case: UseCase) -> None:
    if not cfg.custom_ai_base_url.strip():
        raise HTTPException(status_code=503, detail="Custom AI base URL is not configured.")
    if use_case in {"chat", "scrape"} and not _custom_chat_model(cfg, use_case).strip():
        raise HTTPException(status_code=503, detail="Custom AI model is not configured.")
    if use_case == "embedding" and not cfg.custom_embedding_model.strip():
        raise HTTPException(status_code=503, detail="Custom embedding model is not configured.")
    if not _custom_api_key(cfg, use_case).strip():
        raise HTTPException(status_code=503, detail=f"Custom {use_case} API key is not configured.")


def _openai_chat_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _extract_openai_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise HTTPException(
            status_code=502,
            detail="Custom AI returned an unexpected response payload. Check backend logs.",
        )
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise HTTPException(
            status_code=502,
            detail="Custom AI returned an unexpected response payload. Check backend logs.",
        )
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "".join(parts)
    raise HTTPException(
        status_code=502,
        detail="Custom AI returned an unexpected response payload. Check backend logs.",
    )


async def complete_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float | None = None,
    timeout: float | None = None,
    use_case: UseCase = "chat",
) -> str:
    cfg = get_settings()
    request_timeout = float(timeout or cfg.llm_timeout_seconds)
    temp = cfg.llm_temperature if temperature is None else temperature

    if cfg.ai_provider == "custom":
        return await _complete_custom(cfg, messages, temp, request_timeout, use_case=use_case)
    return await _complete_ollama(cfg, messages, temp, request_timeout)


async def stream_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float | None = None,
    timeout: httpx.Timeout | None = None,
    use_case: UseCase = "chat",
) -> AsyncIterator[str]:
    cfg = get_settings()
    temp = cfg.llm_temperature if temperature is None else temperature

    if cfg.ai_provider == "custom":
        async for chunk in _stream_custom(cfg, messages, temp, timeout, use_case=use_case):
            yield chunk
        return

    async for chunk in _stream_ollama(cfg, messages, temp, timeout):
        yield chunk


async def embed_texts(texts: list[str], *, num_thread: int | None = None) -> list[list[float]]:
    cfg = get_settings()
    if cfg.embedding_provider == "custom":
        return await _embed_custom(cfg, texts)
    return await _embed_ollama(cfg, texts, num_thread=num_thread)


async def _complete_ollama(
    cfg: Settings,
    messages: list[dict[str, str]],
    temperature: float,
    timeout: float,
) -> str:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{cfg.ollama_base_url}/api/chat",
                json={
                    "model": cfg.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            response.raise_for_status()
            payload = response.json()
            message = payload.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str):
                logger.error("Unexpected Ollama response payload: %s", payload)
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Ollama returned an unexpected response payload. "
                        "Check backend logs and verify the selected model can answer chat requests."
                    ),
                )
            return content
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Ollama is not reachable at {cfg.ollama_base_url}. "
                "Make sure the Ollama container is running and the model is pulled."
            ),
        )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail=(
                "The AI model took too long to respond. "
                "Try a shorter prompt, or increase LLM_TIMEOUT_SECONDS."
            ),
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Model '{cfg.ollama_model}' is not available. "
                    f"Pull it with: docker exec -it ollama ollama pull {cfg.ollama_model}"
                ),
            )
        logger.error("Ollama error: %s — %s", exc.response.status_code, exc.response.text)
        raise HTTPException(status_code=502, detail="Ollama returned an error. Check backend logs.")
    except ValueError as exc:
        logger.exception("Invalid Ollama JSON response: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Ollama returned invalid JSON. Check backend logs.",
        )


async def _stream_ollama(
    cfg: Settings,
    messages: list[dict[str, str]],
    temperature: float,
    timeout: httpx.Timeout | None,
) -> AsyncIterator[str]:
    request_timeout = timeout or httpx.Timeout(
        connect=10.0,
        read=float(cfg.llm_timeout_seconds),
        write=30.0,
        pool=30.0,
    )
    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            async with client.stream(
                "POST",
                f"{cfg.ollama_base_url}/api/chat",
                json={
                    "model": cfg.ollama_model,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": temperature},
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    evt = json.loads(line)
                    if not isinstance(evt, dict):
                        logger.error("Unexpected Ollama stream event payload: %s", evt)
                        raise HTTPException(
                            status_code=502,
                            detail="Ollama returned an invalid stream event. Check backend logs.",
                        )
                    chunk = (evt.get("message") or {}).get("content") or ""
                    if chunk:
                        yield chunk
                    if evt.get("done"):
                        break
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Ollama is not reachable at {cfg.ollama_base_url}. "
                "Make sure the Ollama container is running and the model is pulled."
            ),
        )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail=(
                "The AI model took too long to respond. "
                "Try a shorter prompt, or increase LLM_TIMEOUT_SECONDS."
            ),
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Model '{cfg.ollama_model}' is not available. "
                    f"Pull it with: docker exec -it ollama ollama pull {cfg.ollama_model}"
                ),
            )
        logger.error("Ollama error: %s — %s", exc.response.status_code, exc.response.text)
        raise HTTPException(status_code=502, detail="Ollama returned an error. Check backend logs.")
    except ValueError as exc:
        logger.exception("Invalid Ollama stream JSON response: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Ollama returned invalid JSON while streaming. Check backend logs.",
        )


async def _complete_custom(
    cfg: Settings,
    messages: list[dict[str, str]],
    temperature: float,
    timeout: float,
    *,
    use_case: UseCase,
) -> str:
    _validate_custom_config(cfg, use_case)
    url = _openai_chat_url(cfg.custom_ai_base_url)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {_custom_api_key(cfg, use_case)}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _custom_chat_model(cfg, use_case),
                    "messages": messages,
                    "temperature": temperature,
                    "stream": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
            return _extract_openai_message_content(payload)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Custom AI provider is not reachable at {cfg.custom_ai_base_url}.",
        )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail="The external AI provider took too long to respond.",
        )
    except httpx.HTTPStatusError as exc:
        logger.error("Custom AI error: %s — %s", exc.response.status_code, exc.response.text)
        raise HTTPException(
            status_code=502,
            detail="Custom AI provider returned an error. Check backend logs.",
        )
    except ValueError as exc:
        logger.exception("Invalid custom AI JSON response: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Custom AI provider returned invalid JSON. Check backend logs.",
        )


async def _stream_custom(
    cfg: Settings,
    messages: list[dict[str, str]],
    temperature: float,
    timeout: httpx.Timeout | None,
    *,
    use_case: UseCase,
) -> AsyncIterator[str]:
    _validate_custom_config(cfg, use_case)
    url = _openai_chat_url(cfg.custom_ai_base_url)
    request_timeout = timeout or httpx.Timeout(
        connect=10.0,
        read=float(cfg.llm_timeout_seconds),
        write=30.0,
        pool=30.0,
    )

    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            async with client.stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {_custom_api_key(cfg, use_case)}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _custom_chat_model(cfg, use_case),
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    evt = json.loads(payload)
                    choices = evt.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    delta = choices[0].get("delta")
                    if not isinstance(delta, dict):
                        continue
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield content
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Custom AI provider is not reachable at {cfg.custom_ai_base_url}.",
        )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail="The external AI provider took too long to respond.",
        )
    except httpx.HTTPStatusError as exc:
        logger.error("Custom AI error: %s — %s", exc.response.status_code, exc.response.text)
        raise HTTPException(
            status_code=502,
            detail="Custom AI provider returned an error. Check backend logs.",
        )
    except ValueError as exc:
        logger.exception("Invalid custom AI stream JSON response: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Custom AI provider returned invalid JSON while streaming. Check backend logs.",
        )


async def _embed_ollama(
    cfg: Settings,
    texts: list[str],
    num_thread: int | None = None,
) -> list[list[float]]:
    embeddings: list[list[float]] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for text in texts:
            payload: dict[str, Any] = {
                "model": cfg.embedding_model_name,
                "prompt": text,
            }
            if num_thread is not None:
                payload["options"] = {"num_thread": max(1, int(num_thread))}
            resp = await client.post(
                f"{cfg.ollama_base_url}/api/embeddings",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            embedding = data.get("embedding")
            if not isinstance(embedding, list):
                logger.error("Unexpected Ollama embedding payload: %s", data)
                raise HTTPException(
                    status_code=502,
                    detail="Ollama returned an unexpected embedding payload. Check backend logs.",
                )
            embeddings.append(embedding)
    return embeddings


async def _embed_custom(cfg: Settings, texts: list[str]) -> list[list[float]]:
    _validate_custom_config(cfg, "embedding")

    base = cfg.custom_ai_base_url.strip().rstrip("/")
    if base.endswith("/embeddings"):
        url = base
    elif base.endswith("/v1"):
        url = f"{base}/embeddings"
    else:
        url = f"{base}/v1/embeddings"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {_custom_api_key(cfg, 'embedding')}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg.custom_embedding_model,
                    "input": texts,
                },
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("data")
            if not isinstance(items, list):
                logger.error("Unexpected custom embedding payload: %s", payload)
                raise HTTPException(
                    status_code=502,
                    detail="Custom AI provider returned an unexpected embedding payload. Check backend logs.",
                )
            embeddings: list[list[float]] = []
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                    logger.error("Unexpected custom embedding item: %s", item)
                    raise HTTPException(
                        status_code=502,
                        detail="Custom AI provider returned an unexpected embedding payload. Check backend logs.",
                    )
                embeddings.append(item["embedding"])
            return embeddings
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Custom AI provider is not reachable at {cfg.custom_ai_base_url}.",
        )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail="The external embedding provider took too long to respond.",
        )
    except httpx.HTTPStatusError as exc:
        logger.error("Custom embedding error: %s — %s", exc.response.status_code, exc.response.text)
        raise HTTPException(
            status_code=502,
            detail="Custom AI provider returned an embedding error. Check backend logs.",
        )
    except ValueError as exc:
        logger.exception("Invalid custom embedding JSON response: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Custom AI provider returned invalid embedding JSON. Check backend logs.",
        )
