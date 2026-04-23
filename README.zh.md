# omnivoice-open-tts

[English](./README.md) · **中文**

基于 [OmniVoice](https://github.com/k2-fsa/OmniVoice)（k2-fsa 团队推出的支持 600+
语言的零样本扩散语言模型式 TTS）构建的兼容 OpenAI 的 HTTP TTS 服务。以单个
CUDA 容器镜像发布在 GHCR。

实现 [Open TTS 规范](https://github.com/OpenTTSGroup/open-tts-spec)：

- `POST /v1/audio/speech` — 兼容 OpenAI 的合成接口（通过 `file://…` 做声音克隆）
- `POST /v1/audio/clone` — 一次性零样本克隆（multipart 上传）
- `POST /v1/audio/design` — 基于声音属性描述的音色设计（无需参考音频）
- `GET  /v1/audio/voices` — 列出本地文件声音
- `GET  /v1/audio/voices/preview?id=...` — 下载参考 WAV
- `GET  /v1/audio/languages` — 600+ 支持语言
- `GET  /healthz` — 引擎状态、能力、并发快照

六种输出格式（`mp3`、`opus`、`aac`、`flac`、`wav`、`pcm`）；服务端以单声道
`float32` 编码。声音以 `${VOICES_DIR}/<id>.{wav,txt,yml}` 三元组形式存放。

## 快速开始

```bash
mkdir -p voices cache

# （可选）放入一段 3–10 秒的参考音频及其文本，用作克隆声音：
cp ~/my-ref.wav voices/alice.wav
echo "参考音频的文本内容。" > voices/alice.txt

docker run --rm --gpus all -p 8000:8000 \
  -v "$PWD/voices:/voices:ro" \
  -v "$PWD/cache:/root/.cache" \
  ghcr.io/openttsgroup/omnivoice-open-tts:latest
```

首次启动会从 HuggingFace 下载模型权重到 `/root/.cache`，挂载该目录可避免重复下载。
`/healthz` 在模型就绪前返回 `status="loading"`。如果 HuggingFace 连接较慢，
可在容器中设置 `HF_ENDPOINT=https://hf-mirror.com`。

```bash
# 通过 file voice 进行声音克隆
curl -X POST localhost:8000/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"你好，这里是 OmniVoice。","voice":"file://alice","response_format":"mp3"}' \
  -o out.mp3

# 音色设计 —— 无需参考音频
curl -X POST localhost:8000/v1/audio/design \
  -H 'Content-Type: application/json' \
  -d '{"input":"你好，这里是 OmniVoice。","instruct":"女，青年，四川话"}' \
  -o out.mp3

# 自动音色 —— 省略 instruct
curl -X POST localhost:8000/v1/audio/design \
  -H 'Content-Type: application/json' \
  -d '{"input":"你好，这里是 OmniVoice。"}' \
  -o out.mp3
```

## 能力

| capability | 取值 | 说明 |
|---|---|---|
| `clone` | `true` | 通过 `voice="file://..."` 或 `POST /v1/audio/clone` 做零样本克隆 |
| `streaming` | `false` | OmniVoice 没有内建流式路径；不注册 `/v1/audio/realtime` |
| `design` | `true` | `POST /v1/audio/design`，用属性描述控制音色 |
| `languages` | `true` | `GET /v1/audio/languages` 列出 600+ 语言 |
| `builtin_voices` | `false` | OmniVoice 无固定 speaker；只能用 file voices 或 voice design |

## 环境变量

### 引擎（前缀 `OMNIVOICE_`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OMNIVOICE_MODEL` | `k2-fsa/OmniVoice` | HuggingFace 仓库 ID 或本地路径 |
| `OMNIVOICE_DEVICE` | `auto` | `auto` / `cuda` / `cpu` |
| `OMNIVOICE_CUDA_INDEX` | `0` | 多 GPU 时选择卡号 |
| `OMNIVOICE_DTYPE` | `float16` | `float16` / `bfloat16` / `float32` |
| `OMNIVOICE_LOAD_ASR` | `false` | 加载 Whisper，供 `/v1/audio/clone` 自动转写空 `prompt_text` |
| `OMNIVOICE_ASR_MODEL` | `openai/whisper-large-v3-turbo` | `LOAD_ASR=true` 时使用的 ASR 模型 |
| `OMNIVOICE_PROMPT_CACHE_SIZE` | `16` | 每个 voice 的 `VoiceClonePrompt` LRU 容量 |

### 服务级（无前缀）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `HOST` | `0.0.0.0` | |
| `PORT` | `8000` | |
| `LOG_LEVEL` | `info` | uvicorn 日志级别 |
| `VOICES_DIR` | `/voices` | file voice 扫描目录 |
| `MAX_INPUT_CHARS` | `8000` | 超过则 413 |
| `DEFAULT_RESPONSE_FORMAT` | `mp3` | |
| `MAX_CONCURRENCY` | `1` | 并发推理上限 |
| `MAX_QUEUE_SIZE` | `0` | 0 = 队列无界 |
| `QUEUE_TIMEOUT` | `0` | 秒；0 = 无限等待 |
| `MAX_AUDIO_BYTES` | `20971520` | `/v1/audio/clone` 上传上限 |
| `CORS_ENABLED` | `false` | `true` 时挂载开放 CORS 中间件 |

## Compose

见 [`docker/docker-compose.example.yml`](docker/docker-compose.example.yml)。

## 接口参数

GET 接口（`/healthz`、`/v1/audio/voices`、`/v1/audio/voices/preview`、
`/v1/audio/languages`）无 body，最多一个 `id` 查询参数，响应结构详见
[Open TTS 规范](https://github.com/OpenTTSGroup/open-tts-spec/blob/main/http-api-spec.md)。

下面表格描述带 body 的 POST 接口。**Status** 列使用固定词汇：

- **required** —— 缺失则 422。
- **supported** —— 被 OmniVoice 真正使用。
- **ignored** —— 为兼容 OpenAI 接受，但不生效。
- **extension** —— OmniVoice 扩展字段，不在 Open TTS 规范内。

### `POST /v1/audio/speech` (application/json)

| 字段 | 类型 | 默认 | Status | 说明 |
|---|---|---|---|---|
| `model` | string | `null` | ignored | 仅为 OpenAI 兼容，值被丢弃。 |
| `input` | string | — | required | 1..`MAX_INPUT_CHARS` 字符。空 ⇒ 422，超限 ⇒ 413。 |
| `voice` | string | — | required | 必须为 `file://<id>`。裸名字和 `http(s)://` / `s3://` 会被拒绝（422 / 501）。 |
| `response_format` | enum | `mp3` | supported | `mp3`/`opus`/`aac`/`flac`/`wav`/`pcm` 之一。 |
| `speed` | float | `1.0` | supported | 范围 `[0.25, 4.0]`。指定 `duration` 时忽略。 |
| `instructions` | string \| null | `null` | ignored | 为 OpenAI 兼容接受。OmniVoice 需要严格的属性词汇，请改用 `/v1/audio/design`。 |
| `language` | string \| null | `null` | extension | ISO 639-3 码（`en`、`zh`、`cmn`…）或全名（`English`）。见 `/v1/audio/languages`。 |
| `num_step` | int \| null | `null` | extension | 扩散步数，`[1, 256]`。默认 32。 |
| `guidance_scale` | float \| null | `null` | extension | classifier-free 引导强度，`[0, 10]`。 |
| `duration` | float \| null | `null` | extension | 固定输出时长（秒），`[0.1, 600]`。设置后覆盖 `speed`。 |
| `t_shift` | float \| null | `null` | extension | 扩散时间步偏移，`[0, 1]`。 |
| `denoise` | bool \| null | `null` | extension | 是否在输入前缀拼接 `<\|denoise\|>` token。 |

### `POST /v1/audio/clone` (multipart/form-data)

| 字段 | 类型 | 默认 | Status | 说明 |
|---|---|---|---|---|
| `audio` | file | — | required | 扩展名必须为 `.wav/.mp3/.flac/.ogg/.opus/.m4a/.aac/.webm`。超过 `MAX_AUDIO_BYTES` ⇒ 413。不会写入 `${VOICES_DIR}`。 |
| `prompt_text` | string | — | required | 参考音频的文本。空 ⇒ 422。即使启用 `OMNIVOICE_LOAD_ASR`，HTTP 层仍要求此字段。 |
| `input` | string | — | required | 同 `/speech.input`。 |
| `response_format` | string | `mp3` | supported | 同 `/speech`。 |
| `speed` | float | `1.0` | supported | 范围 `[0.25, 4.0]`。 |
| `instructions` | string \| null | `null` | ignored | 同 `/speech.instructions`。 |
| `model` | string | `null` | ignored | 仅为 OpenAI 兼容。 |
| `language`、`num_step`、`guidance_scale`、`duration`、`t_shift`、`denoise` | — | `null` | extension | 语义同 `/speech`。 |

### `POST /v1/audio/design` (application/json)

| 字段 | 类型 | 默认 | Status | 说明 |
|---|---|---|---|---|
| `input` | string | — | required | 同 `/speech.input`。 |
| `instruct` | string \| null | `null` | supported | OmniVoice 的属性词汇（如 `female, low pitch, british`、或中文方言 `女，青年，四川话`）。`null` 或空串 ⇒ 自动选声。详见[上游 voice-design 文档](https://github.com/k2-fsa/OmniVoice/blob/master/docs/voice-design.md)。 |
| `response_format` | string | `mp3` | supported | 同 `/speech`。 |
| `speed` | float | `1.0` | supported | 范围 `[0.25, 4.0]`。指定 `duration` 时忽略。 |
| `language`、`num_step`、`guidance_scale`、`duration`、`t_shift`、`denoise` | — | `null` | extension | 语义同 `/speech`。 |

## 声音目录

在 `${VOICES_DIR}` 放置三元组：

- `<id>.wav` —— 3–10 秒参考片段，语言与目标文本一致效果最佳。
- `<id>.txt` —— UTF-8 文本转写。
- `<id>.yml` —— 可选元数据（name/gender/age/language/accent/tags/description）。

然后在 `/v1/audio/speech` 中以 `file://<id>` 引用。

## 已知限制

- **无流式。** OmniVoice 没有流式解码接口，因此本服务不注册
  `/v1/audio/realtime`，相关请求会返回 404。长文本依然可用——引擎会自动切块
  （`audio_chunk_*` 参数见上游生成配置）并做 cross-fade 拼接。
- **`instructions` 字段被忽略。** OmniVoice 要求严格的属性词汇，直接透传 OpenAI
  风格的自然语言 instructions 无法保证稳定结果。如需控制音色，请使用
  `/v1/audio/design` 的 `instruct` 字段。
- **克隆始终需要文本。** OmniVoice 的克隆模式需要 *同时* 提供参考音频与参考文本；
  若确实没有转写文本，请开启 `OMNIVOICE_LOAD_ASR=true` 并在调用前自行转写。
- **首次加载新 voice 需要构建 prompt。** 后续请求命中
  `VoiceClonePrompt` LRU（`OMNIVOICE_PROMPT_CACHE_SIZE` 控制容量）。
  `/v1/audio/clone` 的 multipart 上传为一次性使用，不进入缓存。
