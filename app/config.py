from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    # --- Engine (OMNIVOICE_* prefix) -----------------------------------------
    omnivoice_model: str = Field(
        default="k2-fsa/OmniVoice",
        description="HuggingFace repo id or local directory for the OmniVoice checkpoint.",
    )
    omnivoice_device: Literal["auto", "cuda", "cpu"] = "auto"
    omnivoice_cuda_index: int = Field(default=0, ge=0)
    omnivoice_dtype: Literal["float16", "bfloat16", "float32"] = "float16"
    omnivoice_load_asr: bool = Field(
        default=False,
        description="Load Whisper for automatic ref_text transcription.",
    )
    omnivoice_asr_model: str = Field(
        default="openai/whisper-large-v3-turbo",
        description="ASR model used when OMNIVOICE_LOAD_ASR=true.",
    )
    omnivoice_prompt_cache_size: int = Field(default=16, ge=1)

    # --- Service-level (no prefix) -------------------------------------------
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "info"
    voices_dir: str = "/voices"
    max_input_chars: int = Field(default=8000, ge=1)
    default_response_format: Literal[
        "mp3", "opus", "aac", "flac", "wav", "pcm"
    ] = "mp3"
    max_concurrency: int = Field(default=1, ge=1)
    max_queue_size: int = Field(default=0, ge=0)
    queue_timeout: float = Field(default=0.0, ge=0.0)
    max_audio_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    cors_enabled: bool = False

    @property
    def voices_path(self) -> Path:
        return Path(self.voices_dir)

    @property
    def resolved_device(self) -> str:
        if self.omnivoice_device == "cpu":
            return "cpu"
        if self.omnivoice_device == "cuda":
            return f"cuda:{self.omnivoice_cuda_index}"
        # auto
        import torch

        if torch.cuda.is_available():
            return f"cuda:{self.omnivoice_cuda_index}"
        return "cpu"

    @property
    def torch_dtype(self):
        import torch

        return {
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
        }[self.omnivoice_dtype]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
