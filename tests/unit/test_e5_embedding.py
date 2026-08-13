from __future__ import annotations

import asyncio
import math
import threading
from pathlib import Path
from typing import Any

import pytest

from app.core.embedding import (
    E5_MAX_SEQUENCE_LENGTH,
    E5_MODEL_ID,
    E5_MODEL_REVISION,
    EMBEDDING_DIMENSION,
    E5Embedding,
    EmbeddingClient,
    EmbeddingInfrastructureError,
    EmbeddingRequest,
)


class FakeSentenceTransformer:
    def __init__(self) -> None:
        self.max_seq_length = E5_MAX_SEQUENCE_LENGTH
        self.device = "cpu"
        self.encode_calls: list[tuple[list[str], dict[str, Any]]] = []
        self.encode_error: BaseException | None = None
        self.encode_waiter: asyncio.Event | None = None

    def get_embedding_dimension(self) -> int:
        return EMBEDDING_DIMENSION

    def encode(self, inputs: list[str], **kwargs: Any) -> list[list[float]]:
        self.encode_calls.append((inputs, kwargs))
        if self.encode_error is not None:
            raise self.encode_error
        vectors: list[list[float]] = []
        for index, _text in enumerate(inputs):
            vector = [0.0] * EMBEDDING_DIMENSION
            vector[index % EMBEDDING_DIMENSION] = 1.0
            vectors.append(vector)
        return vectors


class RecordingLoader:
    def __init__(self, model: FakeSentenceTransformer) -> None:
        self.model = model
        self.calls: list[tuple[str, str, str]] = []
        self.error: BaseException | None = None

    def __call__(
        self,
        model_id: str,
        *,
        revision: str,
        cache_folder: str,
    ) -> FakeSentenceTransformer:
        self.calls.append((model_id, revision, cache_folder))
        if self.error is not None:
            raise self.error
        return self.model


def _client(
    tmp_path: Path,
    *,
    model: FakeSentenceTransformer | None = None,
) -> tuple[E5Embedding, RecordingLoader, FakeSentenceTransformer]:
    resolved_model = model or FakeSentenceTransformer()
    loader = RecordingLoader(resolved_model)
    return (
        E5Embedding(
            cache_folder=tmp_path / "hf-cache",
            batch_size=2,
            model_loader=loader,
        ),
        loader,
        resolved_model,
    )


def test_constructor_is_offline_and_satisfies_embedding_protocol(
    tmp_path: Path,
) -> None:
    client, loader, _model = _client(tmp_path)

    assert isinstance(client, EmbeddingClient)
    assert client.is_loaded is False
    assert loader.calls == []
    assert not (tmp_path / "hf-cache").exists()


def test_default_constructor_does_not_load_or_create_cache(tmp_path: Path) -> None:
    client = E5Embedding(cache_folder=tmp_path / "default-cache")

    assert client.is_loaded is False
    assert not (tmp_path / "default-cache").exists()


@pytest.mark.asyncio
async def test_load_uses_fixed_model_revision_and_reports_runtime_metadata(
    tmp_path: Path,
) -> None:
    client, loader, _model = _client(tmp_path)

    metadata = await client.load(timeout_seconds=1.0)

    assert loader.calls == [
        (E5_MODEL_ID, E5_MODEL_REVISION, str(tmp_path / "hf-cache"))
    ]
    assert metadata.model_id == "intfloat/multilingual-e5-small"
    assert metadata.revision == E5_MODEL_REVISION
    assert metadata.dimension == 384
    assert metadata.max_sequence_length == 512
    assert metadata.device == "cpu"
    assert client.is_loaded is True


@pytest.mark.asyncio
async def test_embed_reuses_model_inputs_and_normalized_batch_contract(
    tmp_path: Path,
) -> None:
    client, loader, model = _client(tmp_path)
    request = EmbeddingRequest(
        input_type="passage",
        texts=("first", "second", "third"),
    )

    response = await client.embed(request, timeout_seconds=1.0)

    assert len(loader.calls) == 1
    assert model.encode_calls == [
        (
            ["passage: first", "passage: second", "passage: third"],
            {
                "batch_size": 2,
                "show_progress_bar": False,
                "convert_to_numpy": True,
                "normalize_embeddings": True,
            },
        )
    ]
    assert response.model == f"{E5_MODEL_ID}@{E5_MODEL_REVISION}"
    assert response.input_count == 3
    assert response.dimension == EMBEDDING_DIMENSION
    assert len(response.vectors) == 3
    assert all(
        math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0)
        for vector in response.vectors
    )


@pytest.mark.asyncio
async def test_query_prefix_is_added_once_by_existing_request_boundary(
    tmp_path: Path,
) -> None:
    client, _loader, model = _client(tmp_path)

    await client.embed(
        EmbeddingRequest(input_type="query", texts=("BaseModel.dict migration",)),
        timeout_seconds=1.0,
    )

    assert model.encode_calls[0][0] == ["query: BaseModel.dict migration"]


@pytest.mark.asyncio
async def test_repeated_and_concurrent_loads_only_construct_one_model(
    tmp_path: Path,
) -> None:
    client, loader, _model = _client(tmp_path)

    first, second = await asyncio.gather(
        client.load(timeout_seconds=1.0),
        client.load(timeout_seconds=1.0),
    )
    third = await client.load(timeout_seconds=1.0)

    assert first == second == third
    assert len(loader.calls) == 1


@pytest.mark.asyncio
async def test_load_timeout_is_safe_and_does_not_start_a_second_loader(
    tmp_path: Path,
) -> None:
    model = FakeSentenceTransformer()
    calls = 0
    release = threading.Event()

    def slow_loader(
        _model_id: str,
        *,
        revision: str,
        cache_folder: str,
    ) -> FakeSentenceTransformer:
        nonlocal calls
        calls += 1
        release.wait()
        return model

    client = E5Embedding(
        cache_folder=tmp_path / "hf-cache",
        model_loader=slow_loader,
    )

    with pytest.raises(EmbeddingInfrastructureError, match="timed out"):
        await client.load(timeout_seconds=0.001)

    release.set()
    await client.load(timeout_seconds=1.0)
    assert calls == 1


@pytest.mark.asyncio
async def test_expected_loader_failure_is_sanitized_and_retryable(
    tmp_path: Path,
) -> None:
    client, loader, _model = _client(tmp_path)
    loader.error = OSError("token=secret private/cache/path")

    with pytest.raises(EmbeddingInfrastructureError) as captured:
        await client.load(timeout_seconds=1.0)

    assert "secret" not in str(captured.value)
    assert "private" not in str(captured.value)
    loader.error = None
    assert (await client.load(timeout_seconds=1.0)).dimension == 384
    assert len(loader.calls) == 2


@pytest.mark.asyncio
async def test_programming_loader_error_propagates(tmp_path: Path) -> None:
    client, loader, _model = _client(tmp_path)
    loader.error = TypeError("programming defect")

    with pytest.raises(TypeError, match="programming defect"):
        await client.load(timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_inference_timeout_is_reported_without_blocking_event_loop(
    tmp_path: Path,
) -> None:
    model = FakeSentenceTransformer()
    release = threading.Event()

    def blocking_encode(
        inputs: list[str],
        **kwargs: Any,
    ) -> list[list[float]]:
        release.wait()
        vector = [0.0] * 384
        vector[0] = 1.0
        return [vector]

    model.encode = blocking_encode  # type: ignore[method-assign]
    client, _loader, _model = _client(tmp_path, model=model)

    with pytest.raises(EmbeddingInfrastructureError, match="timed out"):
        await client.embed(
            EmbeddingRequest(input_type="query", texts=("query",)),
            timeout_seconds=0.001,
        )
    release.set()


@pytest.mark.asyncio
async def test_expected_inference_error_is_sanitized(tmp_path: Path) -> None:
    model = FakeSentenceTransformer()
    model.encode_error = OSError("token=secret private/cache/path")
    client, _loader, _model = _client(tmp_path, model=model)

    with pytest.raises(EmbeddingInfrastructureError) as captured:
        await client.embed(
            EmbeddingRequest(input_type="query", texts=("query",)),
            timeout_seconds=1.0,
        )

    assert "secret" not in str(captured.value)
    assert "private" not in str(captured.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformation",
    ["wrong_count", "wrong_dimension", "not_normalized", "non_finite"],
)
async def test_malformed_model_output_fails_safely(
    tmp_path: Path,
    malformation: str,
) -> None:
    model = FakeSentenceTransformer()

    def malformed_encode(
        inputs: list[str],
        **kwargs: Any,
    ) -> list[list[float]]:
        if malformation == "wrong_count":
            return []
        if malformation == "wrong_dimension":
            return [[1.0] * 383]
        if malformation == "not_normalized":
            return [[1.0] * 384]
        vector = [0.0] * 384
        vector[0] = float("nan")
        return [vector]

    model.encode = malformed_encode  # type: ignore[method-assign]
    client, _loader, _model = _client(tmp_path, model=model)

    with pytest.raises(EmbeddingInfrastructureError):
        await client.embed(
            EmbeddingRequest(input_type="query", texts=("query",)),
            timeout_seconds=1.0,
        )


@pytest.mark.asyncio
async def test_programming_encode_error_propagates(tmp_path: Path) -> None:
    model = FakeSentenceTransformer()
    model.encode_error = TypeError("programming defect")
    client, _loader, _model = _client(tmp_path, model=model)

    with pytest.raises(TypeError, match="programming defect"):
        await client.embed(
            EmbeddingRequest(input_type="query", texts=("query",)),
            timeout_seconds=1.0,
        )
