#!/usr/bin/env bash
# Local-only eval on the DEV (tunable) split. Never scores holdout.
# Usage: ops/run_local_eval.sh [--top-k 4] [--hf-limit 0]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "${LLM_PROVIDER:-}" != "openai_compatible" ]; then
  echo "refusing: set LLM_PROVIDER=openai_compatible (source ops local env first)" >&2
  exit 2
fi
case "${OPENAI_BASE_URL:-}" in
  http://localhost:11434*|http://127.0.0.1:11434*) ;;
  *) echo "refusing: OPENAI_BASE_URL must be loopback Ollama (got '${OPENAI_BASE_URL:-<unset>}')" >&2; exit 2;;
esac
if [ -n "${GEMINI_LIVE_TEST:-}" ]; then
  echo "refusing: GEMINI_LIVE_TEST must be unset for the local run" >&2
  exit 2
fi

echo "model: ${LLM_MODEL:?set LLM_MODEL} | provider: $LLM_PROVIDER | base: $OPENAI_BASE_URL"
echo "embed: ${EMBED_MODEL:-tfidf-local} | backend: ${RETRIEVAL_BACKEND:-lexical} | top_k: ${TOP_K:-4}"
ollama list | head -n 10
/home/frost/legal-agent/.venv/bin/python eval/run_all.py --hf-limit 0 --top-k "${1:-4}" "$@"
# NOTE: run_all.py scores gold + tunable split only; holdout qids are listed
# but never scored (see tables.md "holdout excluded").
