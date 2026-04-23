# omnivoice-open-tts

**English** · [中文](./README.zh.md)

OpenAI-compatible HTTP TTS service built on top of
[OmniVoice](https://github.com/k2-fsa/OmniVoice), the massively multilingual
(600+ languages) zero-shot diffusion LM-style TTS model from k2-fsa. Ships as
a single CUDA container image on GHCR.

Implements the [Open TTS spec](https://github.com/OpenTTSGroup/open-tts-spec):

- `POST /v1/audio/speech` — OpenAI-compatible synthesis (voice cloning via `file://…`)
- `POST /v1/audio/clone` — one-shot zero-shot cloning (multipart upload)
- `POST /v1/audio/design` — voice design by attribute description (no reference audio)
- `GET  /v1/audio/voices` — list file-based voices
- `GET  /v1/audio/voices/preview?id=...` — download a reference WAV
- `GET  /v1/audio/languages` — the 600+ supported languages
- `GET  /healthz` — engine status, capabilities, concurrency snapshot

Six output formats (`mp3`, `opus`, `aac`, `flac`, `wav`, `pcm`); mono
`float32` encoded server-side. Voices live on disk as
`${VOICES_DIR}/<id>.{wav,txt,yml}` triples.

## Quick start

```bash
mkdir -p voices cache

# (Optional) drop a 3–10 s reference WAV plus its transcript for clone voices:
cp ~/my-ref.wav voices/alice.wav
echo "This is the transcript of the reference clip." > voices/alice.txt

docker run --rm --gpus all -p 8000:8000 \
  -v "$PWD/voices:/voices:ro" \
  -v "$PWD/cache:/root/.cache" \
  ghcr.io/openttsgroup/omnivoice-open-tts:latest
```

First boot downloads the model weights from HuggingFace to `/root/.cache`.
Mount the cache directory to avoid repeat downloads. `/healthz` reports
`status="loading"` until the engine is ready. If the HuggingFace connection
is slow, set `HF_ENDPOINT=https://hf-mirror.com` on the container.

```bash
# Voice clone via a file voice
curl -X POST localhost:8000/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"Hello from OmniVoice.","voice":"file://alice","response_format":"mp3"}' \
  -o out.mp3

# Voice design — no reference audio needed
curl -X POST localhost:8000/v1/audio/design \
  -H 'Content-Type: application/json' \
  -d '{"input":"Hello from OmniVoice.","instruct":"female, young adult, british"}' \
  -o out.mp3

# Auto voice — omit instruct
curl -X POST localhost:8000/v1/audio/design \
  -H 'Content-Type: application/json' \
  -d '{"input":"Hello from OmniVoice."}' \
  -o out.mp3
```

## Capabilities

| capability | value | notes |
|---|---|---|
| `clone` | `true` | zero-shot via `voice="file://..."` or `POST /v1/audio/clone` |
| `streaming` | `false` | OmniVoice has no built-in streaming path; `/v1/audio/realtime` is not exposed |
| `design` | `true` | `POST /v1/audio/design` with an attribute description |
| `languages` | `true` | 600+ languages via `GET /v1/audio/languages` |
| `builtin_voices` | `false` | OmniVoice has no fixed speaker IDs; use file voices or voice design |

## Environment variables

### Engine (prefixed `OMNIVOICE_`)

| variable | default | description |
|---|---|---|
| `OMNIVOICE_MODEL` | `k2-fsa/OmniVoice` | HuggingFace repo id or local path |
| `OMNIVOICE_DEVICE` | `auto` | `auto` / `cuda` / `cpu` |
| `OMNIVOICE_CUDA_INDEX` | `0` | GPU index when multiple are visible |
| `OMNIVOICE_DTYPE` | `float16` | `float16` / `bfloat16` / `float32` |
| `OMNIVOICE_LOAD_ASR` | `false` | Load Whisper so `/v1/audio/clone` can auto-transcribe empty `prompt_text` |
| `OMNIVOICE_ASR_MODEL` | `openai/whisper-large-v3-turbo` | ASR model id used when `LOAD_ASR=true` |
| `OMNIVOICE_PROMPT_CACHE_SIZE` | `16` | LRU size for per-voice `VoiceClonePrompt` caches |

### Service-level (no prefix)

| variable | default | description |
|---|---|---|
| `HOST` | `0.0.0.0` | |
| `PORT` | `8000` | |
| `LOG_LEVEL` | `info` | uvicorn log level |
| `VOICES_DIR` | `/voices` | scan root for file-based voices |
| `MAX_INPUT_CHARS` | `8000` | 413 above this |
| `DEFAULT_RESPONSE_FORMAT` | `mp3` | |
| `MAX_CONCURRENCY` | `1` | in-flight synthesis ceiling |
| `MAX_QUEUE_SIZE` | `0` | 0 = unbounded queue |
| `QUEUE_TIMEOUT` | `0` | seconds; 0 = unbounded wait |
| `MAX_AUDIO_BYTES` | `20971520` | upload limit for `/v1/audio/clone` |
| `CORS_ENABLED` | `false` | mount an open `CORSMiddleware` on every endpoint |

## Compose

See [`docker/docker-compose.example.yml`](docker/docker-compose.example.yml).

## API request parameters

GET endpoints (`/healthz`, `/v1/audio/voices`, `/v1/audio/voices/preview`,
`/v1/audio/languages`) take no body and at most a single `id` query parameter
— see the
[Open TTS spec](https://github.com/OpenTTSGroup/open-tts-spec/blob/main/http-api-spec.md)
for their response shape.

The tables below describe the POST endpoints that accept a request body. The
**Status** column uses a fixed vocabulary:

- **required** — rejected with 422 if missing.
- **supported** — accepted and consumed by OmniVoice.
- **ignored** — accepted for OpenAI compatibility; has no effect.
- **extension** — OmniVoice-specific field, not part of the Open TTS spec.

### `POST /v1/audio/speech` (application/json)

| Field | Type | Default | Status | Notes |
|---|---|---|---|---|
| `model` | string | `null` | ignored | OpenAI compatibility only; accepted and discarded. |
| `input` | string | — | required | 1..`MAX_INPUT_CHARS` chars. Empty ⇒ 422, over limit ⇒ 413. |
| `voice` | string | — | required | Must be `file://<id>`. Bare names and `http(s)://` / `s3://` URIs are rejected (422 / 501). |
| `response_format` | enum | `mp3` | supported | One of `mp3`/`opus`/`aac`/`flac`/`wav`/`pcm`. |
| `speed` | float | `1.0` | supported | Range `[0.25, 4.0]`. Ignored when `duration` is set. |
| `instructions` | string \| null | `null` | ignored | Accepted for OpenAI compatibility, but OmniVoice requires a strict attribute vocabulary — use `/v1/audio/design` to control voice style. |
| `language` | string \| null | `null` | extension | ISO 639-3 code (`en`, `zh`, `cmn`, …) or full name (`English`). See `/v1/audio/languages`. |
| `num_step` | int \| null | `null` | extension | Diffusion steps, `[1, 256]`. Engine default is 32. |
| `guidance_scale` | float \| null | `null` | extension | Classifier-free guidance strength, `[0, 10]`. |
| `duration` | float \| null | `null` | extension | Fixed output duration in seconds, `[0.1, 600]`. Overrides `speed`. |
| `t_shift` | float \| null | `null` | extension | Diffusion time-step shift, `[0, 1]`. |
| `denoise` | bool \| null | `null` | extension | Prepend `<\|denoise\|>` token for cleaner output. |

### `POST /v1/audio/clone` (multipart/form-data)

| Field | Type | Default | Status | Notes |
|---|---|---|---|---|
| `audio` | file | — | required | Extension in `.wav/.mp3/.flac/.ogg/.opus/.m4a/.aac/.webm`. Over `MAX_AUDIO_BYTES` ⇒ 413. Never persisted to `${VOICES_DIR}`. |
| `prompt_text` | string | — | required | Reference-clip transcript. Empty ⇒ 422. If you enable `OMNIVOICE_LOAD_ASR` this is still required at the HTTP boundary; auto-transcription is handled inside the model only when you use the Python API directly. |
| `input` | string | — | required | Same semantics as `/speech.input`. |
| `response_format` | string | `mp3` | supported | Same as `/speech`. |
| `speed` | float | `1.0` | supported | Range `[0.25, 4.0]`. |
| `instructions` | string \| null | `null` | ignored | Same as `/speech.instructions`. |
| `model` | string | `null` | ignored | OpenAI compatibility only. |
| `language`, `num_step`, `guidance_scale`, `duration`, `t_shift`, `denoise` | — | `null` | extension | Same semantics as on `/speech`. |

### `POST /v1/audio/design` (application/json)

| Field | Type | Default | Status | Notes |
|---|---|---|---|---|
| `input` | string | — | required | Same semantics as `/speech.input`. |
| `instruct` | string \| null | `null` | supported | Voice attributes from OmniVoice's vocabulary (e.g. `female, low pitch, british`, or Chinese dialects such as `女，青年，四川话`). `null` or empty ⇒ auto voice. See the [upstream voice-design doc](https://github.com/k2-fsa/OmniVoice/blob/master/docs/voice-design.md). |
| `response_format` | string | `mp3` | supported | Same as `/speech`. |
| `speed` | float | `1.0` | supported | Range `[0.25, 4.0]`. Ignored when `duration` is set. |
| `language`, `num_step`, `guidance_scale`, `duration`, `t_shift`, `denoise` | — | `null` | extension | Same semantics as on `/speech`. |

## Voices

Drop triples into `${VOICES_DIR}`:

- `<id>.wav` — 3–10 s reference clip. Same language as the target text works best.
- `<id>.txt` — transcript of the clip, UTF-8.
- `<id>.yml` — optional metadata (name, gender, age, language, accent, tags, description).

Then reference the voice as `file://<id>` from `/v1/audio/speech`.

## Known limitations

- **No streaming.** OmniVoice does not expose a streaming decoder, so
  `/v1/audio/realtime` is not registered; requests hit 404. Long texts still
  work — the engine automatically chunks long-form inputs (`audio_chunk_*`
  knobs in the upstream generation config) and cross-fades internally.
- **`instructions` is ignored.** OmniVoice uses a strict attribute vocabulary
  (see `docs/voice-design.md` upstream), so the OpenAI-style free-form
  `instructions` field cannot be routed safely. Use `/v1/audio/design` with
  `instruct` for voice-attribute control.
- **Clone mode always needs a transcript.** OmniVoice's voice cloning takes
  *both* reference audio and reference text; if you have no transcript,
  enable `OMNIVOICE_LOAD_ASR=true` and transcribe upstream before calling
  `/v1/audio/clone`.
- **First call per voice pays the prompt-building cost.** Subsequent requests
  hit the `VoiceClonePrompt` LRU (`OMNIVOICE_PROMPT_CACHE_SIZE`). Multipart
  uploads through `/v1/audio/clone` are single-use and bypass the cache.
