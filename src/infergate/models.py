"""OpenAI-compatible request/response schemas.

These mirror the subset of the OpenAI Chat Completions API that the gateway
supports, so existing OpenAI client SDKs work against InferGate unchanged.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[str] = None
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: Optional[int] = None
    stream: bool = False
    stop: Optional[Union[str, List[str]]] = None
    user: Optional[str] = None
    # Accept and ignore unknown fields rather than 422-ing real clients.
    model_config = {"extra": "allow"}

    def prompt_text(self) -> str:
        """Flatten messages into a stable string for cache keying / mock output."""
        return "\n".join(f"{m.role}: {m.content or ''}" for m in self.messages)


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: Usage = Field(default_factory=Usage)
    # InferGate-specific metadata (non-breaking extra field).
    infergate: Dict[str, Any] = Field(default_factory=dict)


# ---- Streaming chunk schemas ----


class DeltaMessage(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None


class ChatCompletionChunkChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChunkChoice]


# ---- /v1/models ----


class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "infergate"


class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelCard]


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate (~4 chars/token heuristic)."""
    if not text:
        return 0
    return max(1, len(text) // 4)
