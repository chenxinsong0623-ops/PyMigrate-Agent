import builtins
import math
import socket
from typing import cast

import pytest
from pydantic import ValidationError

from app.core.embedding import (
    EMBEDDING_DIMENSION,
    FAKE_EMBEDDING_MODEL,
    EmbeddingClient,
    EmbeddingRequest,
    EmbeddingResponse,
    FakeEmbedding,
    format_e5_input,
)


def _request(
    *texts: str,
    input_type: str = "query",
) -> EmbeddingRequest:
    return EmbeddingRequest(input_type=input_type, texts=texts)


def test_fake_embedding_satisfies_runtime_client_protocol() -> None:
    assert isinstance(FakeEmbedding(), EmbeddingClient)


def test_query_and_passage_prefixes_are_exact_and_not_mixed() -> None:
    query = _request("如何迁移 BaseModel.dict()", input_type="query")
    passage = _request(
        "Pydantic migration documentation ...",
        input_type="passage",
    )

    assert query.model_inputs == ("query: 如何迁移 BaseModel.dict()",)
    assert passage.model_inputs == ("passage: Pydantic migration documentation ...",)
    assert format_e5_input("query", "原始文本") == "query: 原始文本"
    assert format_e5_input("passage", "原始文本") == "passage: 原始文本"


@pytest.mark.parametrize(
    "prefixed_text",
    [
        "query: 已添加前缀",
        "passage: 已添加前缀",
        "  QUERY: 已添加前缀",
        "  Passage: 已添加前缀",
    ],
)
def test_request_rejects_preformatted_text_to_prevent_double_prefix(
    prefixed_text: str,
) -> None:
    with pytest.raises(ValidationError):
        _request(prefixed_text)


@pytest.mark.asyncio
async def test_fake_embedding_returns_exactly_384_finite_floats() -> None:
    response = await FakeEmbedding().embed(_request("文本"), 1.0)
    vector = response.vectors[0]

    assert response.dimension == EMBEDDING_DIMENSION == 384
    assert len(vector) == 384
    assert all(isinstance(value, float) for value in vector)
    assert all(math.isfinite(value) for value in vector)


@pytest.mark.asyncio
async def test_batch_preserves_count_order_and_repeated_items() -> None:
    fake = FakeEmbedding()
    request = _request("a", "b", "a", input_type="passage")

    response = await fake.embed(request, timeout_seconds=2.5)

    assert request.model_inputs == ("passage: a", "passage: b", "passage: a")
    assert response.input_count == 3
    assert len(response.vectors) == 3
    assert all(len(vector) == 384 for vector in response.vectors)
    assert response.vectors[0] != response.vectors[1]
    assert response.vectors[0] == response.vectors[2]


@pytest.mark.asyncio
async def test_single_item_and_batch_results_are_consistent() -> None:
    fake = FakeEmbedding()

    single = await fake.embed(_request("same", input_type="passage"), 1.0)
    batch = await fake.embed(
        _request("before", "same", "after", input_type="passage"),
        1.0,
    )

    assert single.vectors[0] == batch.vectors[1]


@pytest.mark.asyncio
async def test_repeated_calls_are_deterministic_and_recorded() -> None:
    fake = FakeEmbedding()
    request = _request("确定性", "批量", input_type="query")

    first = await fake.embed(request, 0.75)
    second = await fake.embed(request, timeout_seconds=0.75)

    assert first == second
    assert fake.call_count == 2
    assert fake.calls == [(request, 0.75), (request, 0.75)]


@pytest.mark.asyncio
async def test_same_raw_text_differs_between_query_and_passage() -> None:
    fake = FakeEmbedding()

    query = await fake.embed(_request("相同原始文本", input_type="query"), 1.0)
    passage = await fake.embed(
        _request("相同原始文本", input_type="passage"),
        1.0,
    )

    assert query.vectors[0] != passage.vectors[0]


@pytest.mark.parametrize(
    "texts",
    [
        (),
        ("",),
        ("   ",),
        ("valid", "\t\r\n"),
    ],
)
def test_request_rejects_empty_batch_and_blank_texts(
    texts: tuple[str, ...],
) -> None:
    with pytest.raises(ValidationError):
        EmbeddingRequest(input_type="query", texts=texts)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("input_type", "document"),
        ("input_type", 1),
        ("texts", ("valid", 1)),
        ("extra_field", "forbidden"),
    ],
)
def test_request_rejects_invalid_types_and_extra_fields(
    field: str,
    invalid_value: object,
) -> None:
    values: dict[str, object] = {
        "input_type": "query",
        "texts": ("valid",),
    }
    values[field] = invalid_value

    with pytest.raises(ValidationError):
        EmbeddingRequest.model_validate(values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_timeout",
    [
        0,
        -1,
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        "1.0",
    ],
)
async def test_fake_embedding_rejects_invalid_timeout_without_recording(
    invalid_timeout: object,
) -> None:
    fake = FakeEmbedding()

    with pytest.raises((TypeError, ValueError)):
        await fake.embed(_request("文本"), cast(float, invalid_timeout))

    assert fake.call_count == 0


def test_response_rejects_vector_count_mismatch() -> None:
    vector = tuple(0.0 for _ in range(384))

    with pytest.raises(ValidationError):
        EmbeddingResponse(
            model="fake-test",
            vectors=(vector,),
            input_count=2,
        )


def test_response_rejects_wrong_dimension_and_non_finite_values() -> None:
    with pytest.raises(ValidationError):
        EmbeddingResponse(
            model="fake-test",
            vectors=((0.0,) * 383,),
            input_count=1,
        )

    non_finite = (0.0,) * 383 + (float("nan"),)
    with pytest.raises(ValidationError):
        EmbeddingResponse(
            model="fake-test",
            vectors=(non_finite,),
            input_count=1,
        )


@pytest.mark.asyncio
async def test_fake_model_name_never_claims_real_e5_execution() -> None:
    response = await FakeEmbedding().embed(_request("文本"), 1.0)

    assert response.model == FAKE_EMBEDDING_MODEL == "fake-embedding"
    assert response.model != "intfloat/multilingual-e5-small"


@pytest.mark.asyncio
async def test_fake_embedding_uses_no_network_file_or_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("FakeEmbedding 尝试执行网络或文件 I/O")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(socket, "create_connection", fail_io)
    monkeypatch.setattr(socket.socket, "connect", fail_io)
    monkeypatch.setattr(builtins, "open", fail_io)

    fake = FakeEmbedding()
    response = await fake.embed(_request("完全离线"), 1.0)

    assert response.input_count == 1
    assert fake.call_count == 1
