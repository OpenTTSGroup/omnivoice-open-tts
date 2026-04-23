from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

import numpy as np

from app.config import Settings


log = logging.getLogger(__name__)


# Generation kwargs that ``OmniVoice.generate`` accepts directly. Unknown
# entries are dropped by ``OmniVoiceGenerationConfig.from_dict``, but we
# whitelist here to keep the surface area explicit.
_ENGINE_KWARG_KEYS = frozenset(
    {
        "num_step",
        "guidance_scale",
        "t_shift",
        "denoise",
        "layer_penalty_factor",
        "position_temperature",
        "class_temperature",
        "audio_chunk_duration",
        "audio_chunk_threshold",
        "preprocess_prompt",
        "postprocess_output",
    }
)


def _collect_engine_kwargs(extra: dict[str, Any]) -> dict[str, Any]:
    """Keep only non-None, whitelisted entries to forward to ``generate``."""
    return {k: v for k, v in extra.items() if v is not None and k in _ENGINE_KWARG_KEYS}


class TTSEngine:
    """Async HTTP-friendly wrapper around ``omnivoice.OmniVoice``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._device = settings.resolved_device

        import torch  # noqa: F401 — ensure torch is importable before model load

        from omnivoice import OmniVoice

        self._model = OmniVoice.from_pretrained(
            settings.omnivoice_model,
            device_map=self._device,
            dtype=settings.torch_dtype,
            load_asr=settings.omnivoice_load_asr,
            asr_model_name=settings.omnivoice_asr_model,
        )
        self._sample_rate = int(self._model.sampling_rate)

        # LRU cache of reusable ``VoiceClonePrompt`` objects keyed by
        # ``(ref_audio_path, ref_mtime)``. ``ref_mtime is None`` (multipart
        # uploads) bypasses the cache — the temp file is single-use.
        self._prompt_cache: dict[tuple[str, float], Any] = {}
        self._prompt_cache_order: list[tuple[str, float]] = []
        self._prompt_cache_max = settings.omnivoice_prompt_cache_size
        self._prompt_lock = threading.Lock()

        # Eagerly compute language table; OmniVoice ships a static mapping.
        try:
            from omnivoice.utils.lang_map import LANG_NAME_TO_ID

            self._languages: list[tuple[str, str]] = sorted(
                ((code, name) for name, code in LANG_NAME_TO_ID.items()),
                key=lambda kv: kv[1],
            )
        except Exception:
            log.exception("failed to load OmniVoice language table")
            self._languages = []

    # ------------------------------------------------------------------
    # Public attributes

    @property
    def device(self) -> str:
        return self._device

    @property
    def dtype_str(self) -> str:
        return self._settings.omnivoice_dtype

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def model_id(self) -> str:
        return self._settings.omnivoice_model

    @property
    def builtin_voices_list(self) -> list[str]:
        return []

    def list_languages(self) -> list[tuple[str, str]]:
        return list(self._languages)

    # ------------------------------------------------------------------
    # Voice-clone prompt cache

    def _get_or_build_prompt(
        self, ref_audio: str, ref_mtime: Optional[float], ref_text: Optional[str]
    ):
        """Return a ``VoiceClonePrompt`` for ``(ref_audio, ref_mtime)``.

        When ``ref_mtime is None`` (temp uploads) we always rebuild and do not
        insert into the cache.
        """
        if ref_mtime is None:
            return self._model.create_voice_clone_prompt(
                ref_audio=ref_audio, ref_text=ref_text
            )

        key = (ref_audio, ref_mtime)
        with self._prompt_lock:
            cached = self._prompt_cache.get(key)
            if cached is not None:
                try:
                    self._prompt_cache_order.remove(key)
                except ValueError:
                    pass
                self._prompt_cache_order.append(key)
                return cached

        prompt = self._model.create_voice_clone_prompt(
            ref_audio=ref_audio, ref_text=ref_text
        )

        with self._prompt_lock:
            self._prompt_cache[key] = prompt
            self._prompt_cache_order.append(key)
            while len(self._prompt_cache_order) > self._prompt_cache_max:
                old_key = self._prompt_cache_order.pop(0)
                self._prompt_cache.pop(old_key, None)

        return prompt

    # ------------------------------------------------------------------
    # Output helpers

    @staticmethod
    def _first_mono(audios: list[np.ndarray]) -> np.ndarray:
        if not audios:
            return np.zeros(0, dtype=np.float32)
        arr = np.asarray(audios[0])
        if arr.ndim > 1:
            arr = arr.reshape(-1)
        return arr.astype(np.float32, copy=False)

    # ------------------------------------------------------------------
    # Clone synthesis (via file:// voices and /v1/audio/clone)

    async def synthesize_clone(
        self,
        text: str,
        *,
        ref_audio: str,
        ref_text: str,
        ref_mtime: Optional[float] = None,
        instructions: Optional[str] = None,
        speed: float = 1.0,
        language: Optional[str] = None,
        **extra: Any,
    ) -> np.ndarray:
        if instructions:
            log.warning(
                "instructions ignored: OmniVoice uses strict attribute vocabulary; "
                "use /v1/audio/design to control voice attributes",
            )

        gen_kwargs = _collect_engine_kwargs(extra)
        duration = extra.get("duration")

        def _run() -> np.ndarray:
            prompt = self._get_or_build_prompt(ref_audio, ref_mtime, ref_text)
            audios = self._model.generate(
                text=text,
                voice_clone_prompt=prompt,
                language=language,
                speed=speed if duration is None else None,
                duration=duration,
                **gen_kwargs,
            )
            return self._first_mono(audios)

        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # Voice-design synthesis (text + attribute description)

    async def synthesize_design(
        self,
        text: str,
        *,
        instruct: Optional[str],
        speed: float = 1.0,
        language: Optional[str] = None,
        **extra: Any,
    ) -> np.ndarray:
        gen_kwargs = _collect_engine_kwargs(extra)
        duration = extra.get("duration")
        # Empty/whitespace-only instruct collapses to None → auto voice mode.
        effective_instruct = instruct.strip() if isinstance(instruct, str) else None
        if not effective_instruct:
            effective_instruct = None

        def _run() -> np.ndarray:
            audios = self._model.generate(
                text=text,
                instruct=effective_instruct,
                language=language,
                speed=speed if duration is None else None,
                duration=duration,
                **gen_kwargs,
            )
            return self._first_mono(audios)

        return await asyncio.to_thread(_run)
