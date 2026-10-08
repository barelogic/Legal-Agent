#!/usr/bin/env bash
# Prefetch every model + dataset before the venue (run once, network ON).
# Verifies with `ollama list` / `ollama show` and HF cache; never guesses tags.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Ollama =="
ollama list
echo "---"
# Verified default (local `ollama show` + library page https://ollama.com/library/llama3.1):
# llama3.1:8b, Q4_K_M, ctx 131072 (library lists 128K), 4.9GB.
ollama pull llama3.1:8b
ollama show llama3.1:8b | head -n 12
echo "---"
ollama list

echo "== Embeddings (sentence-transformers, CUDA torch present) =="
/home/frost/legal-agent/.venv/bin/python - <<'EOF'
from sentence_transformers import SentenceTransformer
for mid in ("BAAI/bge-m3",):
    m = SentenceTransformer(mid, device="cuda")
    print(mid, "ok, dim:", m.get_sentence_embedding_dimension())
EOF

echo "== Datasets / corpus raws =="
/home/frost/legal-agent/.venv/bin/python corpus/fetch_statutes.py
/home/frost/legal-agent/.venv/bin/python corpus/fetch_judgments.py --target 20
/home/frost/legal-agent/.venv/bin/python corpus/fetch_hf_legal.py
/home/frost/legal-agent/.venv/bin/python corpus/fetch_court_tars.py --sc-years 2024 --hc-bench 2020 court=19_16 bench=calcutta_original_side
/home/frost/legal-agent/.venv/bin/python corpus/make_case_files.py
/home/frost/legal-agent/.venv/bin/python corpus/build_corpus.py
/home/frost/legal-agent/.venv/bin/python eval/build_queries.py
echo "prefetch done. Next: test once with the network OFF (see docs/local_llm.md)."
