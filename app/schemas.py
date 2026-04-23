from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ResponseFormat = Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]


class Capabilities(BaseModel):
    clone: bool = Field(description="Zero-shot cloning support.")
    streaming: bool = Field(description="Chunked realtime synthesis support.")
    design: bool = Field(description="Text-only voice design support.")
    languages: bool = Field(description="Explicit language list support.")
    builtin_voices: bool = Field(description="Engine ships built-in voices.")


class ConcurrencySnapshot(BaseModel):
    max: int = Field(description="Global concurrency ceiling.")
    active: int = Field(description="Currently in-flight synthesis jobs.")
    queued: int = Field(description="Waiters blocked on the semaphore.")


class HealthResponse(BaseModel):
    status: Literal["ok", "loading", "error"] = Field(
        description="Engine readiness state."
    )
    model: str = Field(description="Loaded model identifier.")
    sample_rate: int = Field(description="Inference output sample rate (Hz).")
    capabilities: Capabilities = Field(description="Discovered engine capabilities.")
    device: Optional[str] = Field(default=None, description='e.g. "cuda:0" or "cpu".')
    dtype: Optional[str] = Field(default=None, description='e.g. "float16".')
    concurrency: Optional[ConcurrencySnapshot] = Field(
        default=None, description="Live concurrency snapshot."
    )


class VoiceInfo(BaseModel):
    id: str = Field(
        description='Voice identifier. "file://<name>" for disk voices, raw name for built-ins.'
    )
    preview_url: Optional[str] = Field(
        description="Preview URL for file voices; null for built-ins."
    )
    prompt_text: Optional[str] = Field(
        description="Reference transcript for file voices; null for built-ins."
    )
    metadata: Optional[dict[str, Any]] = Field(
        description="Optional metadata dict from <id>.yml."
    )


class VoiceListResponse(BaseModel):
    voices: list[VoiceInfo] = Field(description="Discovered voices.")


class Language(BaseModel):
    key: str = Field(description="Engine-native language identifier (ISO 639-3 or code).")
    name: str = Field(description="Human-readable language name.")


class LanguagesResponse(BaseModel):
    languages: list[Language] = Field(description="Supported synthesis languages.")


# ---------------------------------------------------------------------------
# OmniVoice engine-specific generation fields (extension of the core spec).
#
# All of these are Optional; missing means "use engine default". Validation
# ranges mirror ``omnivoice.models.omnivoice.OmniVoiceGenerationConfig`` and
# the upstream docs/generation-parameters.md sheet.
# ---------------------------------------------------------------------------


class _OmniVoiceGenMixin(BaseModel):
    language: Optional[str] = Field(
        default=None,
        description=(
            "Engine-native language identifier (ISO 639-3 code or full name, "
            "e.g. 'en', 'zh', 'English'). See /v1/audio/languages for the full list."
        ),
    )
    num_step: Optional[int] = Field(
        default=None,
        ge=1,
        le=256,
        description="Diffusion steps. 16 = faster, 32+ = higher quality.",
    )
    guidance_scale: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description="Classifier-free guidance strength.",
    )
    duration: Optional[float] = Field(
        default=None,
        ge=0.1,
        le=600.0,
        description="Target output duration in seconds. Overrides 'speed' when set.",
    )
    t_shift: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Diffusion time-step shift.",
    )
    denoise: Optional[bool] = Field(
        default=None,
        description="Prepend <|denoise|> token for cleaner output.",
    )


class SpeechRequest(_OmniVoiceGenMixin):
    model_config = ConfigDict(extra="ignore")

    model: Optional[str] = Field(
        default=None,
        description="Accepted for OpenAI compatibility; ignored.",
    )
    input: str = Field(
        min_length=1,
        description="Text to synthesize.",
    )
    voice: str = Field(
        description='Must be "file://<id>" — OmniVoice has no built-in voices.'
    )
    response_format: Optional[ResponseFormat] = Field(
        default=None,
        description="Output container/codec; defaults to the service setting.",
    )
    speed: float = Field(
        default=1.0,
        ge=0.25,
        le=4.0,
        description="Playback rate.",
    )
    instructions: Optional[str] = Field(
        default=None,
        description=(
            "Accepted for OpenAI compatibility; ignored by OmniVoice. "
            "Use /v1/audio/design for voice-attribute control."
        ),
    )


class DesignRequest(_OmniVoiceGenMixin):
    model_config = ConfigDict(extra="ignore")

    input: str = Field(
        min_length=1,
        description="Text to synthesize.",
    )
    instruct: Optional[str] = Field(
        default=None,
        description=(
            "Voice attribute description (e.g. 'female, young adult, british'). "
            "Null or empty lets the model pick a voice automatically."
        ),
    )
    response_format: Optional[ResponseFormat] = Field(
        default=None,
        description="Output container/codec; defaults to the service setting.",
    )
    speed: float = Field(
        default=1.0,
        ge=0.25,
        le=4.0,
        description="Playback rate.",
    )
