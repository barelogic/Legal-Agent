"""Eval package: data + evaluation side (branch eval/data-eval).

Only new files under eval/. Never touches contracts/schemas.py.
"""

from eval.corpus_sources import build_corpus, corpus_registry
from eval.gold import build_gold, load_gold
from eval.judge import get_judge_model, judge_answers
from eval.metrics_grounded import groundedness_report
from eval.metrics_retrieval import retrieval_report
from eval.systems import run_system

__all__ = [
    "build_corpus",
    "corpus_registry",
    "build_gold",
    "load_gold",
    "get_judge_model",
    "judge_answers",
    "groundedness_report",
    "retrieval_report",
    "run_system",
]
