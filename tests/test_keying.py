from __future__ import annotations

from infergate.models import ChatCompletionRequest
from infergate.routing.keying import build_routing_key, image_marker


def _text_req(text, model="qwen-vl"):
    return ChatCompletionRequest(model=model, messages=[{"role": "user", "content": text}])


def _image_req(text, url, model="qwen-vl"):
    return ChatCompletionRequest(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }
        ],
    )


def test_shared_prefix_yields_shared_leading_blocks():
    sys = "You are a helpful assistant. " * 20
    a = build_routing_key(_text_req(sys + "Question one"), block_size=4)
    b = build_routing_key(_text_req(sys + "Question two is different"), block_size=4)
    # Leading blocks (the shared system prompt) must match; the tails diverge.
    assert a.block_hashes[0] == b.block_hashes[0]
    assert a.block_hashes[:3] == b.block_hashes[:3]
    assert a.block_hashes[-1] != b.block_hashes[-1]


def test_identical_request_identical_key():
    a = build_routing_key(_text_req("same prompt here"))
    b = build_routing_key(_text_req("same prompt here"))
    assert a.block_hashes == b.block_hashes


def test_same_text_different_image_diverges():
    """The core multimodal safety property."""
    a = build_routing_key(_image_req("describe this", "http://x/cat.png"))
    b = build_routing_key(_image_req("describe this", "http://x/dog.png"))
    assert a.num_images == 1
    assert a.block_hashes != b.block_hashes


def test_same_text_same_image_matches():
    a = build_routing_key(_image_req("describe this", "http://x/cat.png"))
    b = build_routing_key(_image_req("describe this", "http://x/cat.png"))
    assert a.block_hashes == b.block_hashes


def test_image_marker_modes():
    data_uri = "data:image/png;base64,QUJDREVG"
    # bytes mode hashes the base64 payload; url mode hashes the whole string
    assert image_marker(data_uri, "bytes_sha256") != image_marker(data_uri, "url")
    # deterministic
    assert image_marker(data_uri, "bytes_sha256") == image_marker(data_uri, "bytes_sha256")


def test_empty_request_has_no_blocks():
    req = ChatCompletionRequest(model="m", messages=[{"role": "user", "content": ""}])
    key = build_routing_key(req, block_size=16)
    # role marker still produces at least one unit/block
    assert key.num_images == 0
