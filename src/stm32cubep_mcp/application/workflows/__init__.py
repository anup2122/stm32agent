"""Composed application workflows.

This package contains the end-to-end flows used by the orchestrator server.
Each module here coordinates multiple domain services or MCP server functions to
produce one user-visible workflow result.

Exact call-chain example for the generic prompt router path:

``stm32_orchestrate_prompt`` in ``orchestrator/server.py``
-> ``prompt_router.route_prompt``
-> one of:
    - ``build_flash_test.orchestrate_build_then_flash``
    - ``generate_project.orchestrate_feature_delivery``
    - ``debug_question.orchestrate_debug_question``
    - ``live_debug.orchestrate_debug_session``
    - ``cubemx_regeneration.orchestrate_cubemx_regeneration``

Exact call-chain example for the feature-delivery path:

``stm32_orchestrate_feature_prompt`` in ``orchestrator/server.py``
-> ``run_feature_delivery_workflow`` in the same module
-> ``generate_project.orchestrate_feature_delivery``
-> requirements decomposition, project-metadata preparation, IOC construction or
    application, CubeMX regeneration, build, flash, and runtime validation.
"""

from .build_flash_test import orchestrate_build_then_flash
from .cubemx_regeneration import orchestrate_cubemx_regeneration, regenerate_project_workflow
from .debug_question import orchestrate_debug_question
from .generate_project import orchestrate_feature_delivery
from .live_debug import orchestrate_debug_session, run_runtime_validation_stage
from .prompt_router import route_prompt

__all__ = [
    "orchestrate_build_then_flash",
    "orchestrate_cubemx_regeneration",
    "regenerate_project_workflow",
    "orchestrate_debug_question",
    "orchestrate_feature_delivery",
    "orchestrate_debug_session",
    "run_runtime_validation_stage",
    "route_prompt",
]
