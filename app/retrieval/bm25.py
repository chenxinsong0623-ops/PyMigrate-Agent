"""对固定 Day 9 chunk artifact 提供可独立调用的离线 BM25 检索。"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ingestion.markdown_chunker import (
    CHUNK_ARTIFACT_PATH,
    MarkdownChunk,
    MarkdownChunkingError,
    load_chunk_artifact,
)

BM25_TOP_K_MAX = 8
BM25_K1 = 1.5
BM25_B = 0.75

_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[._-][^\W_]+)*")
_TOKEN_SEPARATOR_PATTERN = re.compile(r"[._-]")


class BM25ArtifactError(RuntimeError):
    """BM25 无法从严格 Day 9 artifact 建立只读内存索引。"""


class BM25SearchResult(BaseModel):
    """供调用方或 RRF 融合消费的严格 BM25 result。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rank: int = Field(gt=0)
    score: float
    chunk_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    heading_path: tuple[str, ...]
    text: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    git_ref: str = Field(min_length=1)
    resolved_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_path: str = Field(min_length=1)
    source_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("score")
    @classmethod
    def validate_score(cls, score: float) -> float:
        if not math.isfinite(score) or score <= 0:
            raise ValueError("BM25 score 必须是大于 0 的有限数值")
        return score


def validate_raw_query(query: str) -> str:
    """验证应用边界接收的是未添加 E5 prefix 的非空原始 query。"""
    if not isinstance(query, str):
        raise TypeError("query 必须是字符串")
    normalized = query.strip()
    if not normalized:
        raise ValueError("query 不能为空")
    if normalized.casefold().startswith(("query:", "passage:")):
        raise ValueError("query 必须是未添加 embedding prefix 的原始文本")
    return normalized


def tokenize_for_bm25(text: str) -> tuple[str, ...]:
    """保留 Python API 复合 token，同时发出其组件以支持部分词法匹配。"""
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(text):
        compound = match.group(0).casefold()
        tokens.append(compound)
        if any(separator in compound for separator in "._-"):
            tokens.extend(
                component
                for component in _TOKEN_SEPARATOR_PATTERN.split(compound)
                if component
            )
    return tuple(tokens)


class BM25Retriever:
    """在内存中索引一份已验证 chunk 序列并执行确定性 BM25 排序。"""

    def __init__(
        self,
        chunks: Sequence[MarkdownChunk],
        *,
        k1: float = BM25_K1,
        b: float = BM25_B,
    ) -> None:
        if not chunks:
            raise ValueError("BM25 corpus 不能为空")
        if (
            isinstance(k1, bool)
            or not isinstance(k1, (int, float))
            or not math.isfinite(k1)
            or k1 <= 0
        ):
            raise ValueError("BM25 k1 必须是大于 0 的有限数值")
        if (
            isinstance(b, bool)
            or not isinstance(b, (int, float))
            or not math.isfinite(b)
            or not 0 <= b <= 1
        ):
            raise ValueError("BM25 b 必须位于 0..1")

        chunk_ids = [chunk.chunk_id for chunk in chunks]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("BM25 corpus chunk_id 必须唯一")

        self._chunks = tuple(chunks)
        self._k1 = float(k1)
        self._b = float(b)
        self._term_frequencies = tuple(
            Counter(tokenize_for_bm25(chunk.text)) for chunk in self._chunks
        )
        self._document_lengths = tuple(
            sum(term_frequency.values()) for term_frequency in self._term_frequencies
        )
        self._average_document_length = sum(self._document_lengths) / len(
            self._document_lengths
        )
        document_frequencies: Counter[str] = Counter()
        for term_frequency in self._term_frequencies:
            document_frequencies.update(term_frequency.keys())
        self._document_frequencies = document_frequencies

    @classmethod
    def from_artifact(
        cls,
        path: Path,
        *,
        k1: float = BM25_K1,
        b: float = BM25_B,
    ) -> BM25Retriever:
        """严格加载 schema v1 artifact；不读取网络或启动外部服务。"""
        try:
            artifact = load_chunk_artifact(path)
        except MarkdownChunkingError as error:
            raise BM25ArtifactError("chunk artifact is missing or invalid") from error
        return cls(artifact.chunks, k1=k1, b=b)

    def search(
        self,
        query: str,
        top_k: int = BM25_TOP_K_MAX,
    ) -> tuple[BM25SearchResult, ...]:
        """执行 BM25 top-k；无正分词法命中时返回空 tuple。"""
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k 必须是整数")
        if not 1 <= top_k <= BM25_TOP_K_MAX:
            raise ValueError("top_k 必须位于 1..8")
        normalized_query = validate_raw_query(query)
        query_terms = tuple(dict.fromkeys(tokenize_for_bm25(normalized_query)))
        if not query_terms:
            raise ValueError("query 必须至少包含一个可检索 token")

        scored: list[tuple[float, int, MarkdownChunk]] = []
        document_count = len(self._chunks)
        for document_order, (chunk, term_frequency, document_length) in enumerate(
            zip(
                self._chunks,
                self._term_frequencies,
                self._document_lengths,
                strict=True,
            )
        ):
            score = 0.0
            for term in query_terms:
                frequency = term_frequency.get(term, 0)
                if frequency == 0:
                    continue
                document_frequency = self._document_frequencies[term]
                inverse_document_frequency = math.log1p(
                    (document_count - document_frequency + 0.5)
                    / (document_frequency + 0.5)
                )
                length_normalization = 1 - self._b
                if self._average_document_length > 0:
                    length_normalization += (
                        self._b * document_length / self._average_document_length
                    )
                denominator = frequency + self._k1 * length_normalization
                score += inverse_document_frequency * (
                    frequency * (self._k1 + 1) / denominator
                )
            if score > 0:
                scored.append((score, document_order, chunk))

        scored.sort(key=lambda item: (-item[0], item[1], item[2].chunk_id))
        return tuple(
            BM25SearchResult(
                rank=rank,
                score=score,
                chunk_id=chunk.chunk_id,
                heading_path=chunk.heading_path,
                text=chunk.text,
                content_sha256=chunk.content_sha256,
                source_id=chunk.source_id,
                source_url=chunk.source_url,
                git_ref=chunk.git_ref,
                resolved_commit_sha=chunk.resolved_commit_sha,
                source_path=chunk.source_path,
                source_snapshot_sha256=chunk.source_snapshot_sha256,
            )
            for rank, (score, _document_order, chunk) in enumerate(
                scored[:top_k], start=1
            )
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="对固定 Day 9 chunk artifact 执行离线 BM25 查询。"
    )
    parser.add_argument(
        "queries", nargs="+", help="一个或多个未加 prefix 的原始 query。"
    )
    parser.add_argument("--top-k", type=int, default=BM25_TOP_K_MAX)
    parser.add_argument("--artifact-path", type=Path, default=Path(CHUNK_ARTIFACT_PATH))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """只在显式 CLI 调用时读取本地 artifact 并输出 JSON lines。"""
    args = _build_parser().parse_args(argv)
    try:
        retriever = BM25Retriever.from_artifact(args.artifact_path)
        for query in args.queries:
            results = retriever.search(query, top_k=args.top_k)
            print(
                json.dumps(
                    {
                        "query": query,
                        "top_k": args.top_k,
                        "results": [
                            result.model_dump(mode="json") for result in results
                        ],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    except (BM25ArtifactError, TypeError, ValueError) as error:
        print(f"bm25_query_failed error_type={type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
