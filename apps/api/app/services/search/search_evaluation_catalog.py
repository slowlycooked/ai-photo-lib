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


SEARCH_PLANNER_DEBUG_EVALUATION_SET: tuple[SearchEvaluationCase, ...] = (
    SearchEvaluationCase(
        name="planner compound time place activity",
        query="去年张家口滑雪",
        mode="hybrid",
    ),
    SearchEvaluationCase(
        name="planner pure metadata time camera",
        query="去年1月 iPhone 拍的照片",
        mode="hybrid",
    ),
    SearchEvaluationCase(
        name="planner people relationship group",
        query="妈妈和孩子的合照",
        mode="hybrid",
    ),
    SearchEvaluationCase(
        name="planner compound place weather night",
        query="上海下雨天夜景",
        mode="hybrid",
    ),
    SearchEvaluationCase(
        name="planner object negative constraint",
        query="有猫但不是狗",
        mode="hybrid",
    ),
    SearchEvaluationCase(
        name="planner pure metadata date place",
        query="2024年12月在日本拍的照片",
        mode="hybrid",
    ),
)
