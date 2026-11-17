"""
Async Ollama client wrapper.
Supports streaming and non-streaming chat completions.
"""
import asyncio
import logging
from typing import AsyncIterator, Optional

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


async def is_ollama_online() -> bool:
    """Check if the Ollama server is running."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(settings.OLLAMA_URL)
            return resp.status_code == 200
    except Exception:
        return False


async def list_models() -> list[str]:
    """Return names of all locally available Ollama models."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{settings.OLLAMA_URL}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        logger.warning(f"Could not list Ollama models: {e}")
        return []


async def is_model_available(model: str) -> bool:
    """Check if the specified model is installed in Ollama."""
    try:
        available = await list_models()
        return any(m == model or m.startswith(f"{model}:") or model.startswith(f"{m}:") for m in available)
    except Exception:
        return False


async def chat_stream(
    prompt: str,
    system: str = "",
    context: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncIterator[str]:
    """
    Stream a chat response from Ollama token-by-token.
    Yields string chunks as they arrive.
    """
    model = model or settings.DEFAULT_LLM_MODEL
    temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
    
    # Cap num_ctx to 2048 to prevent CUDA_Host buffer allocation OOM on CPU/low-VRAM systems
    num_ctx = min(getattr(settings, "LLM_NUM_CTX", 2048), 2048)

    # Configurable and validated generation limit - clamp within context window
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        max_tokens = min(settings.LLM_MAX_TOKENS, num_ctx - 256)
    else:
        max_tokens = min(max_tokens, num_ctx - 256)

    # Check Ollama status and model availability concurrently
    online, available = await asyncio.gather(
        is_ollama_online(),
        is_model_available(model),
    )
    if not online:
        yield f"\n\n⚠️ **Ollama is not running.** Please start it with `ollama serve` and ensure `{model}` is pulled."
        return
    if not available:
        installed = await list_models()
        models_str = ", ".join(f"`{m}`" for m in installed) if installed else "none"
        yield f"\n\n⚠️ **Model `{model}` is not available in Ollama.** Available models: {models_str}. Run `ollama pull {model}`."
        return

    messages = []
    if system:
        messages.append({"role": "system", "content": system})

    # Only include context if not already present in the prompt
    if context and context.strip() and context.strip() not in prompt:
        prompt = f"{context.strip()}\n\n{prompt}"

    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": num_ctx,
            "num_thread": 6,
        },
    }

    try:
        client_timeout = httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=30.0)
        async with httpx.AsyncClient(timeout=client_timeout) as client:
            async with client.stream(
                "POST",
                f"{settings.OLLAMA_URL}/api/chat",
                json=payload,
            ) as response:
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        import json
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if not token and chunk.get("message", {}).get("thinking"):
                                token = chunk.get("message", {}).get("thinking", "")
                            if token:
                                yield token
                            if chunk.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
                else:
                    err_bytes = await response.aread()
                    err_str = err_bytes.decode("utf-8", errors="ignore")
                    logger.error(f"Ollama returned {response.status_code}: {err_str}")
                    # If memory constraint or buffer error, retry with num_ctx=1024
                    if response.status_code == 500 and any(k in err_str for k in ("out-of-memory", "CUDA_Host", "buffer", "allocate")) and num_ctx > 1024:
                        logger.warning("Ollama OOM detected, retrying with num_ctx=1024...")
                        payload["options"]["num_ctx"] = 1024
                        payload["options"]["num_predict"] = min(max_tokens, 768)
                        async with client.stream(
                            "POST",
                            f"{settings.OLLAMA_URL}/api/chat",
                            json=payload,
                        ) as retry_resp:
                            if retry_resp.status_code == 200:
                                async for line in retry_resp.aiter_lines():
                                    if not line.strip():
                                        continue
                                    import json
                                    try:
                                        chunk = json.loads(line)
                                        token = chunk.get("message", {}).get("content", "")
                                        if not token and chunk.get("message", {}).get("thinking"):
                                            token = chunk.get("message", {}).get("thinking", "")
                                        if token:
                                            yield token
                                        if chunk.get("done", False):
                                            break
                                    except json.JSONDecodeError:
                                        continue
                                return
                            else:
                                retry_err = (await retry_resp.aread()).decode("utf-8", errors="ignore")
                                raise RuntimeError(f"Ollama error: {retry_err}")
                    else:
                        raise RuntimeError(f"Ollama error ({response.status_code}): {err_str}")
    except httpx.ConnectError:
        yield f"\n\n⚠️ **Ollama is not running.** Please start it with `ollama serve` and ensure `{model}` is pulled."
    except Exception as e:
        logger.error(f"Ollama streaming error: {e}")
        yield f"\n\n⚠️ **LLM Error:** {str(e)}"


async def chat_complete(
    prompt: str,
    system: str = "",
    context: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Non-streaming chat completion. Returns the full response string."""
    chunks = []
    async for token in chat_stream(
        prompt,
        system=system,
        context=context,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        chunks.append(token)
    return "".join(chunks)
