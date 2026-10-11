"""LLM backend using llama-cpp-python for local inference."""

from __future__ import annotations

import logging
from typing import Optional, Callable, Generator

logger = logging.getLogger(__name__)


class LLMBackend:
    """Wraps llama-cpp-python for local model inference.

    Provides a unified interface for generating text with streaming support,
    configurable sampling parameters, and model lifecycle management.
    """

    def __init__(self) -> None:
        self._model = None
        self._model_path: str = ""
        self._n_ctx: int = 8192
        self._n_gpu_layers: int = -1  # -1 = auto
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded and self._model is not None

    @property
    def model_path(self) -> str:
        return self._model_path

    @property
    def context_size(self) -> int:
        return self._n_ctx

    def load_model(
        self,
        model_path: str,
        n_ctx: int = 8192,
        n_gpu_layers: int = -1,
        **kwargs,
    ) -> None:
        """Load a GGUF model from disk.

        Args:
            model_path: Path to the .gguf model file.
            n_ctx: Context window size (tokens).
            n_gpu_layers: Number of layers to offload to GPU (-1 = all).
            **kwargs: Extra args passed to llama_cpp.Llama().
        """
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError(
                "llama-cpp-python is not installed. "
                "Install it with: pip install llama-cpp-python"
            )

        if self._model is not None:
            self.unload_model()

        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers

        logger.info("Loading model from %s (n_ctx=%d, n_gpu_layers=%d)",
                     model_path, n_ctx, n_gpu_layers)

        self._model = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
            **kwargs,
        )
        self._is_loaded = True
        logger.info("Model loaded successfully.")

    def unload_model(self) -> None:
        """Free the model from memory."""
        if self._model is not None:
            del self._model
            self._model = None
            self._is_loaded = False
            self._model_path = ""
            logger.info("Model unloaded.")

    def generate(
        self,
        system_prompt: str = "",
        user_prompt: str = "",
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        max_tokens: int = 4096,
        repeat_penalty: float = 1.1,
        stop: list[str] | None = None,
        stream: bool = True,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Generate text completion.

        Args:
            system_prompt: System-level instructions.
            user_prompt: The user prompt / input.
            temperature: Sampling temperature.
            top_p: Nucleus sampling threshold.
            top_k: Top-K sampling threshold.
            max_tokens: Maximum tokens to generate.
            repeat_penalty: Penalty for repeating tokens.
            stop: List of stop sequences.
            stream: Whether to stream tokens.
            on_token: Callback for each streamed token.

        Returns:
            The full generated text.
        """
        if not self.is_loaded:
            raise RuntimeError("No model loaded. Call load_model() first.")

        messages = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        if user_prompt.strip():
            messages.append({"role": "user", "content": user_prompt})

        if stream and on_token:
            return self._generate_stream(
                messages, temperature, top_p, top_k,
                max_tokens, repeat_penalty, stop, on_token,
            )
        else:
            return self._generate_sync(
                messages, temperature, top_p, top_k,
                max_tokens, repeat_penalty, stop,
            )

    def _generate_sync(
        self, messages, temperature, top_p, top_k,
        max_tokens, repeat_penalty, stop,
    ) -> str:
        resp = self._model.create_chat_completion(
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
            repeat_penalty=repeat_penalty,
            stop=stop or [],
            stream=False,
        )
        return resp["choices"][0]["message"]["content"]

    def _generate_stream(
        self, messages, temperature, top_p, top_k,
        max_tokens, repeat_penalty, stop, on_token,
    ) -> str:
        collected = []
        stream = self._model.create_chat_completion(
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
            repeat_penalty=repeat_penalty,
            stop=stop or [],
            stream=True,
        )
        for chunk in stream:
            delta = chunk["choices"][0].get("delta", {})
            token_text = delta.get("content", "")
            if token_text:
                collected.append(token_text)
                on_token(token_text)
        return "".join(collected)

    def count_tokens(self, text: str) -> int:
        """Estimate token count for a text string."""
        if not self.is_loaded:
            # Rough estimate: ~4 chars per token for English
            return len(text) // 4
        return len(self._model.tokenize(text.encode("utf-8")))

    def get_model_info(self) -> dict:
        """Return metadata about the loaded model."""
        if not self.is_loaded:
            return {"loaded": False}
        desc = self._model.metadata
        return {
            "loaded": True,
            "path": self._model_path,
            "n_ctx": self._n_ctx,
            "n_gpu_layers": self._n_gpu_layers,
        }