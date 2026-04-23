#!/usr/bin/env bash
set -euo pipefail

# Engine defaults
: "${OMNIVOICE_MODEL:=k2-fsa/OmniVoice}"
: "${OMNIVOICE_DEVICE:=auto}"
: "${OMNIVOICE_DTYPE:=float16}"
: "${OMNIVOICE_LOAD_ASR:=false}"

# Service-level defaults
: "${VOICES_DIR:=/voices}"
: "${HOST:=0.0.0.0}"
: "${PORT:=8000}"
: "${LOG_LEVEL:=info}"
: "${CORS_ENABLED:=false}"

export OMNIVOICE_MODEL OMNIVOICE_DEVICE OMNIVOICE_DTYPE OMNIVOICE_LOAD_ASR \
       VOICES_DIR HOST PORT LOG_LEVEL CORS_ENABLED

if [ "$#" -eq 0 ]; then
  exec uvicorn app.server:app --host "$HOST" --port "$PORT" --log-level "$LOG_LEVEL"
fi
exec "$@"
