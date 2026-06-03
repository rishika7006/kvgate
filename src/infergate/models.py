"""OpenAI-compatible request/response schemas.

These mirror the subset of the OpenAI Chat Completions API that the gateway
supports, so existing OpenAI client SDKs work against InferGate unchanged.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    # `content` is either a plain string or the OpenAI multimodal "parts" list:
    #   [{"type": "text", "text": "..."},
    #    {"type": "image_url", "image_url": {"url": "https://..." | "data:image/..."}}]
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[Union[str, List[Any]]] = None
    name: Optional[str] = None

    def text_content(self) -> str:
        """The textual part of the message, flattening multimodal parts."""
        if self.content is None:
            return ""
        if isinstance(self.content, str):
            return self.content
        parts: List[str] = []
        for p in self.content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict) and "text" in p:
                parts.append(p.get("text") or "")
        return " ".join(parts)

    def image_refs(self) -> List[str]:
        """URLs / data-URIs of any images attached to this message, in order."""
        refs: List[str] = []
        if isinstance(self.content, list):
            for p in self.content:
                if isinstance(p, dict) and p.get("type") == "image_url":
                    iu = p.get("image_url")
                    if isinstance(iu, dict):
                        refs.append(iu.get("url", "") or "")
                    elif isinstance(iu, str):
                        refs.append(iu)
        return refs


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
        return "\n".join(f"{m.role}: {m.text_content()}" for m in self.messages)

    def has_images(self) -> bool:
        return any(m.image_refs() for m in self.messages)


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
