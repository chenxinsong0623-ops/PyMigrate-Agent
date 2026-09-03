# Third-Party Notices

## Pydantic

- Component: Pydantic official migration documentation
- Upstream repository: https://github.com/pydantic/pydantic
- Requested ref: `v2.13.4`
- Resolved commit: `cf67d4b3193c3fe43ede18612ed62785eee11382`
- Snapshot source: `docs/migration.md`
- Snapshot URL: https://raw.githubusercontent.com/pydantic/pydantic/cf67d4b3193c3fe43ede18612ed62785eee11382/docs/migration.md
- Local snapshot: `data/snapshots/pydantic-v2-migration/migration.md`
- License: MIT
- Preserved license: `third_party/pydantic-LICENSE`
- License source: https://raw.githubusercontent.com/pydantic/pydantic/cf67d4b3193c3fe43ede18612ed62785eee11382/LICENSE

MigrationLens preserves this fixed official document only as its reproducible Pydantic
v1-to-v2 migration knowledge source. Copyright and attribution remain with the
copyright holders identified by Pydantic in the preserved upstream license text.

## Sentence Transformers

- Component: `sentence-transformers==5.6.1`
- Upstream repository: https://github.com/huggingface/sentence-transformers
- Purpose: Load and run the pinned dense embedding model through its public
  `SentenceTransformer` API.
- License: Apache-2.0
- License source: https://github.com/huggingface/sentence-transformers/blob/v5.6.1/LICENSE

The package is installed as a direct runtime dependency. Its transitive dependencies
retain their own upstream licenses and notices.

## LangGraph

- Component: `langgraph==1.2.11`
- Upstream repository: https://github.com/langchain-ai/langgraph
- Purpose: Build the bounded MigrationLens orchestration with the low-level
  `StateGraph` API.
- License: MIT
- License source: https://github.com/langchain-ai/langgraph/blob/1.2.11/LICENSE

MigrationLens uses the low-level graph API directly. It does not add the full
`langchain` agent package as a direct dependency, configure LangSmith tracing, add a
model provider SDK, or use the deprecated `langgraph.prebuilt.create_react_agent`
helper. `langchain-core` and `langsmith` are present transitively in LangGraph's
dependency chain; all transitive packages retain their own upstream licenses and
notices.

## python-multipart

- Component: `python-multipart==0.0.32`
- Upstream repository: https://github.com/Kludex/python-multipart
- Purpose: Parse the bounded `multipart/form-data` ZIP upload accepted by the
  FastAPI analysis endpoint.
- License: Apache-2.0
- License source: https://github.com/Kludex/python-multipart/blob/0.0.32/LICENSE.txt

The package is a direct runtime dependency because FastAPI file/form parameters use
its streaming multipart parser. MigrationLens still performs an independent bounded
read, MIME check, and ZipGuard validation before analysis.

## HTTPX

- Component: `httpx==0.28.1`
- Upstream repository: https://github.com/encode/httpx
- Purpose: Send bounded asynchronous requests from the optional OpenAI-compatible
  LLM runtime adapter; tests inject `MockTransport` and do not access a provider.
- License: BSD-3-Clause
- License source: https://github.com/encode/httpx/blob/0.28.1/LICENSE.md

HTTPX is a direct runtime dependency because production code imports its async client.
The adapter performs no request during dependency construction and uses the timeout
supplied by the existing bounded Agent contract.

## Locust

- Component: `locust==2.46.4`
- Upstream repository: https://github.com/locustio/locust
- Purpose: Run the Day26 HTTP application load profiles at explicit concurrency
  levels without adding load execution to ordinary pytest.
- License: MIT
- License source: https://github.com/locustio/locust/blob/2.46.4/LICENSE

Locust is an optional development dependency. It is not installed in the production
image by `pip install .`, and load tests remain explicit commands rather than unit or
integration test side effects.

## multilingual-e5-small

- Component: `intfloat/multilingual-e5-small`
- Model repository: https://huggingface.co/intfloat/multilingual-e5-small
- Pinned revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- Pinned tree: https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3
- Purpose: Produce normalized 384-dimensional query and passage embeddings for the
  local MigrationLens dense index.
- License declared by the model repository: MIT

Model weights and tokenizer files are runtime cache artifacts under ignored local
storage. They are not redistributed in this repository.
