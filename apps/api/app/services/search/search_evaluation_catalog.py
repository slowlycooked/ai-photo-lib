"""Default fixed-query regression catalog for search evaluation."""
from __future__ import annotations

from .search_evaluation_service import SearchEvaluationCase


SEARCH_EVALUATION_BASELINES: tuple[SearchEvaluationCase, ...] = (
    SearchEvaluationCase(
        name="semantic indoor baseline",
        query="室内",
        mode="hybrid",
    ),
    SearchEvaluationCase(
        name="night scene baseline",
        query="夜景",
        mode="hybrid",
    ),
    SearchEvaluationCase(
        name="animal entity baseline",
        query="猫",
        mode="hybrid",
    ),
    SearchEvaluationCase(
        name="group photo baseline",
        query="合照",
        mode="hybrid",
    ),
    SearchEvaluationCase(
        name="weather rain baseline",
        query="下雨天",
        mode="hybrid",
    ),
    SearchEvaluationCase(
        name="ocr order number baseline",
        query="订单号",
        mode="keyword",
    ),
)
