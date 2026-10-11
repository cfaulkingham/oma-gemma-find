"""LiteRT-LM adapters.

Probed on 2026-10-11 against litert-lm-api 0.18.0 (Python 3.14):
EmbeddingEngine.compute_embedding(contents, options=EmbeddingOptions(...))
returns EmbeddingResponse.embedding, and Engine.create_conversation accepts
system_message, thinking_config, tools, automatic_tool_calling, and
max_output_tokens.
"""

from oma_gemma_find.answer import SYSTEM, build_user_prompt, extract_text
from oma_gemma_find.textutil import prefix_document, prefix_query
from oma_gemma_find.vectors import truncate_normalize

OUTPUT_DIM = 256


class ModelMissing(Exception):
    """The LiteRT runtime or a pinned model file is not available."""


class LitertEmbedder:
    model_id = "embeddinggemma-2-text-vision-440m"

    def __init__(self, model_path: str, backend: str = "cpu", engine=None, litert=None):
        self.model_path = model_path
        self.backend_name = backend if backend in ("cpu", "gpu") else "cpu"
        self._engine = engine
        self._litert = litert
        self._owned = engine is None

    def close(self) -> None:
        engine = self._engine
        self._engine = None
        if self._owned and engine is not None and hasattr(engine, "close"):
            engine.close()

    def embed_query(self, text: str) -> list[float]:
        return self._embed(prefix_query(text))

    def embed_document(self, text: str) -> list[float]:
        return self._embed(prefix_document(text))

    def embed_image(self, data: bytes) -> list[float]:
        api = self._api()
        return self._vectors(api.Content.ImageBytes(data))

    def _embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("empty")
        return self._vectors(text)

    def _vectors(self, contents) -> list[float]:
        api = self._api()
        response = self._live().compute_embedding(
            contents,
            options=api.EmbeddingOptions(normalize=True, output_size=OUTPUT_DIM),
        )
        return truncate_normalize(list(response.embedding), OUTPUT_DIM)

    def _live(self):
        if self._engine is not None:
            return self._engine
        api = self._api()
        backend = api.Backend.GPU() if self.backend_name == "gpu" else api.Backend.CPU()
        self._engine = api.EmbeddingEngine(
            self.model_path,
            backend=backend,
            vision_backend=backend,
        )
        return self._engine

    def _api(self):
        if self._litert is not None:
            return self._litert
        try:
            import litert_lm
        except ImportError as exc:
            raise ModelMissing("LiteRT runtime is not installed. Run setup-runtime.") from exc
        return litert_lm


class LitertAnswerer:
    def __init__(self, model_path: str, backend: str = "cpu", engine=None, litert=None):
        self.model_path = model_path
        self.backend_name = backend if backend in ("cpu", "gpu") else "cpu"
        self._engine = engine
        self._litert = litert
        self._owned = engine is None

    def close(self) -> None:
        engine = self._engine
        self._engine = None
        if self._owned and engine is not None and hasattr(engine, "close"):
            engine.close()

    def answer(self, question: str, passages: list[tuple[str, str]]) -> str:
        api = self._api()
        thinking = api.ThinkingConfig(enable_thinking=False, thinking_token_budget=0)
        prompt = build_user_prompt(question, passages)
        with self._live().create_conversation(
            system_message=SYSTEM,
            thinking_config=thinking,
            max_output_tokens=400,
            tools=None,
            automatic_tool_calling=False,
        ) as conversation:
            response = conversation.send_message(
                prompt,
                max_output_tokens=400,
                thinking_config=thinking,
            )
        return extract_text(response)

    def _live(self):
        if self._engine is not None:
            return self._engine
        api = self._api()
        backend = api.Backend.GPU() if self.backend_name == "gpu" else api.Backend.CPU()
        self._engine = api.Engine(self.model_path, backend=backend)
        return self._engine

    def _api(self):
        if self._litert is not None:
            return self._litert
        try:
            import litert_lm
        except ImportError as exc:
            raise ModelMissing("LiteRT runtime is not installed. Run setup-runtime.") from exc
        return litert_lm
