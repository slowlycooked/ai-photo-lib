from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_project, require_project_manager
from ..models.project import Project
from ..schemas.project_query_planner_settings import (
    QueryPlannerTestRequest,
    QueryPlannerTestResponse,
    ProjectQueryPlannerSettingsResponse,
    ProjectQueryPlannerSettingsUpdate,
)
from ..services.query_understanding_service import understand_query
from ..services.search.query_planner.llm_query_planner import resolve_query_plan_llm_first
from ..services.search.settings_resolver import SearchSettingsResolver
from ..services.project_query_planner_settings_service import (
    get_or_create_project_query_planner_settings,
    reset_project_query_planner_settings,
    update_project_query_planner_settings,
)

router = APIRouter(
    prefix="/projects/{project_id}/query-planner-settings",
    tags=["query-planner-settings"],
)


@router.get("", response_model=ProjectQueryPlannerSettingsResponse)
def get_query_planner_settings(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectQueryPlannerSettingsResponse:
    row = get_or_create_project_query_planner_settings(db, project_id)
    return ProjectQueryPlannerSettingsResponse.model_validate(row)


@router.put("", response_model=ProjectQueryPlannerSettingsResponse)
def put_query_planner_settings(
    project_id: int,
    body: ProjectQueryPlannerSettingsUpdate,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
) -> ProjectQueryPlannerSettingsResponse:
    updates = body.model_dump(exclude_none=True)
    if "ai_service_profile_id" in body.model_fields_set:
        updates["ai_service_profile_id"] = body.ai_service_profile_id
    row = update_project_query_planner_settings(db, project_id, updates)
    return ProjectQueryPlannerSettingsResponse.model_validate(row)


@router.post("/reset", response_model=ProjectQueryPlannerSettingsResponse)
def post_reset_query_planner_settings(
    project_id: int,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
) -> ProjectQueryPlannerSettingsResponse:
    row = reset_project_query_planner_settings(db, project_id)
    return ProjectQueryPlannerSettingsResponse.model_validate(row)


@router.post("/test", response_model=QueryPlannerTestResponse)
def post_test_query_planner(
    project_id: int,
    body: QueryPlannerTestRequest,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
) -> QueryPlannerTestResponse:
    settings = SearchSettingsResolver.resolve(db, project_id)
    plan = resolve_query_plan_llm_first(
        body.query.strip(),
        project_id=project_id,
        settings=settings,
        understander=understand_query,
        include_raw_output=True,
    )

    parsed_query_plan = {
        "intent": plan.intent,
        "search_mode": plan.search_mode,
        "normalized_query": plan.normalized_query,
        "semantic_query_text": plan.semantic_query_text,
        "exact_terms": plan.exact_terms,
        "expanded_terms": plan.expanded_terms,
        "support_terms": plan.support_terms,
        "broad_terms": plan.broad_terms,
        "negative_terms": plan.negative_terms,
        "filters": plan.filters,
        "metadata_filters": plan.metadata_filters,
        "semantic_tags": plan.semantic_tags,
        "concept_terms": plan.concept_terms,
        "core_facets": plan.core_facets,
        "query_constraints": plan.query_constraints,
    }

    return QueryPlannerTestResponse(
        query=body.query,
        planner_debug=plan.planner_debug,
        parsed_query_plan=parsed_query_plan,
    )
