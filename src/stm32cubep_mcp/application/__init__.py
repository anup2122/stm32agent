"""Application-layer services and workflows.

This package is the orchestration layer between the MCP server modules and the
lower-level STM32 helpers, adapters, and contract utilities.

The package is split into two halves:

- ``services/`` contains reusable, mostly stateless functions for one focused
	concern such as prompt routing, project-config normalization, IOC planning,
	CubeMX host/runtime handling, artifact selection, and plan-state management.
- ``workflows/`` composes those services into larger user-facing flows such as
	build-then-flash, CubeMX regeneration, live debug question answering, and
	prompt-driven feature delivery.

In practice, the server modules call into this package to keep MCP tool handlers
thin. A workflow here typically coordinates multiple domain tools, while the
services package provides the shared building blocks and state-shaping helpers
used by those workflows.

Representative flow examples:

- ``workflows/prompt_router.py`` classifies a natural-language request and
	dispatches it to the correct domain workflow.
- ``workflows/generate_project.py`` runs the full prompt-to-contract,
	IOC-materialization, CubeMX, build, flash, and runtime-validation pipeline.
- ``services/project_config_service.py`` fills or normalizes project metadata
	needed by the workflows.
- ``services/workflow_state.py`` derives incremental execution state from the
	requirements contract and plan artifacts.
"""
