# Phase 1 Refactor Plan

## Purpose

This document turns Phase 1 of [modular-agent-architecture.md](C:/stm32/stm32agent/docs/modular-agent-architecture.md) into a concrete refactor plan for the current repo.

Phase 1 has three ordered goals:

1. introduce stable internal contracts
2. split the codebase into clearer packages without breaking the current MCP surface
3. add a first local CubeMX DB indexing layer

This phase is deliberately about structure and interfaces, not about adding many new STM32 feature families.

## Scope Boundary

This phase will improve architecture, safety, and extensibility.

This phase will not:

- replace the current prompt heuristics with a full LLM intent layer
- implement the final generic IOC compiler
- add a full retrieval corpus repo
- change MCP tool names or remove current entrypoints
- attempt a risky all-at-once rewrite

## Why This Refactor Is Needed Now

The current repo already has strong domain coverage, but the main modules are still too large and cross-coupled for the broader agent responsibilities.

Current large files:

- [src/stm32cubep_mcp/debug/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/debug/server.py) at about `80 KB`
- [src/stm32cubep_mcp/cube_programmer/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/cube_programmer/server.py) at about `77 KB`
- [src/stm32cubep_mcp/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/server.py) at about `75 KB`
- [src/stm32cubep_mcp/orchestrator/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/orchestrator/server.py) at about `72 KB`
- [src/stm32cubep_mcp/cubemx/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/cubemx/server.py) at about `60 KB`
- [src/stm32cubep_mcp/requirements/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/requirements/server.py) at about `40 KB`

That shape makes it harder to:

- let subagents work on isolated concerns
- introduce a generic intent layer without breaking execution
- evolve bug-fix workflows independently of project-generation workflows
- treat live debugging as a first-class capability

## Phase 1 Outcome

At the end of this phase, the repo should have:

- explicit internal data contracts for tasks, intent, plans, project state, IOC operations, and observations
- thinner MCP-facing server files that delegate to services or workflows
- a read-only local CubeMX DB index that can answer baseline, board, MCU, pin, and selected DMA questions
- compatibility wrappers so the current MCP surface and most tests still pass during the transition

## Refactor Strategy

This phase should be executed as a staged refactor with compatibility shims.

Important rule:

- new modules are introduced first
- old modules become facades second
- behavior changes are minimized until structure is stable

The repo should never be in a state where a large package move and a major behavior change happen together.

## Workstream 1: Internal Contracts First

### Goal

Create a small set of internal Python models that all workflows can share.

### Recommended Representation

Use `dataclasses` with explicit validation helpers and `to_dict()` or `from_dict()` adapters.

Reason:

- cleaner than raw dicts for internal code
- no extra dependency needed
- still easy to bridge to MCP JSON payloads
- better stepping stone than a full framework migration

### New Package

Create:

```text
src/stm32cubep_mcp/project_model/
  __init__.py
  agent_task.py
  intent_bundle.py
  plan_state.py
  project_state.py
  ioc_operations.py
  observations.py
  adapters.py
  validators.py
```

### Initial Contracts To Add

#### `AgentTask`

Purpose:

- canonical task input for application workflows

Suggested fields:

- `task_id`
- `task_kind`
- `source_prompt`
- `board_id`
- `mcu`
- `project_context_kind`
- `existing_project_path`
- `requested_actions`
- `constraints`

#### `IntentBundle`

Purpose:

- structured intent produced by prompt analysis or future LLM parsing

Suggested fields:

- `intent_kind`
- `confidence`
- `core_requirements`
- `optional_requirements`
- `interface_intents`
- `runtime_expectations`
- `assumptions`
- `open_questions`

#### `PlanState`

Purpose:

- canonical persisted progress model

Suggested fields:

- `plan_version`
- `plan_id`
- `workflow_kind`
- `increments`
- `current_increment_id`
- `completed_increment_ids`
- `failed_increment_ids`
- `attempt_history`
- `stuck_counter`
- `needs_user_review`

#### `ProjectState`

Purpose:

- canonical view of project paths and active artifacts

Suggested fields:

- `project_name`
- `project_root`
- `managed_copy_root`
- `ioc_path`
- `script_path`
- `cubeide_project_path`
- `workspace_path`
- `build_artifact_path`
- `board_id`
- `mcu`
- `clock_summary`

#### `IocOperation`

Purpose:

- generic unit of IOC mutation

Suggested fields:

- `op_id`
- `kind`
- `target`
- `value`
- `reason`
- `source_requirement_ids`

#### `Observation`

Purpose:

- normalized evidence from build, flash, serial, or debug phases

Suggested fields:

- `stage`
- `source`
- `severity`
- `summary`
- `details`
- `log_path`
- `facts`
- `repair_hints`

### Adapters To Add

Add transitional adapters that convert current dict-based shapes into the new contracts.

Examples:

- `contract_from_legacy_requirements_dict(...)`
- `plan_state_from_plan_markdown(...)`
- `project_state_from_project_metadata(...)`
- `legacy_requirements_dict_from_intent_bundle(...)`

### Current Files To Integrate First

The first integration points should be:

- [src/stm32cubep_mcp/requirements_ioc_contract.py](C:/stm32/stm32agent/src/stm32cubep_mcp/requirements_ioc_contract.py)
- [src/stm32cubep_mcp/requirements/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/requirements/server.py)
- [src/stm32cubep_mcp/orchestrator/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/orchestrator/server.py)

### Specific Refactor Tasks

1. Add the new `project_model` package and model classes.
2. Keep [requirements_ioc_contract.py](C:/stm32/stm32agent/src/stm32cubep_mcp/requirements_ioc_contract.py) temporarily, but make it delegate to the new models and validators where possible.
3. Update plan persistence code to round-trip through `PlanState`.
4. Update orchestrator increment handling to read `PlanState` and `ProjectState` instead of raw dicts where practical.

### Acceptance Criteria

- no MCP tool signature changes
- current plan file format still loads
- current tests for plan and increment handling still pass
- new unit tests exist for model validation and adapter round-trips

## Workstream 2: Package Split With Compatibility Facades

### Goal

Split large server modules into packages aligned with transport, application workflows, tool adapters, and shared services.

### Compatibility Rule

Existing MCP-facing modules should remain in place during this phase and import the extracted logic from new modules.

That means:

- [src/stm32cubep_mcp/orchestrator/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/orchestrator/server.py) stays as the MCP wrapper for now
- [src/stm32cubep_mcp/build/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/build/server.py) stays as the MCP wrapper for now
- same for `cubemx`, `cube_programmer`, and `debug`

### Target Packages To Introduce In Phase 1

```text
src/stm32cubep_mcp/
  application/
    __init__.py
    workflows/
    services/
  tools/
    __init__.py
  intent/
    __init__.py
  shared_core/
    __init__.py
```

I recommend using `shared_core/` instead of reusing `shared/` immediately because the repo already has [shared.py](C:/stm32/stm32agent/src/stm32cubep_mcp/shared.py), and this avoids an import collision during migration.

### Package Split Order

#### Step 2.1: Split `shared.py`

Current file:

- [shared.py](C:/stm32/stm32agent/src/stm32cubep_mcp/shared.py)

New modules:

```text
shared_core/
  config_loader.py
  jsonc.py
  host.py
  paths.py
  logs.py
  schema_validation.py
```

Keep [shared.py](C:/stm32/stm32agent/src/stm32cubep_mcp/shared.py) as a facade that re-exports stable helpers while callers migrate.

#### Step 2.2: Split `requirements`

Current files:

- [requirements/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/requirements/server.py)
- [requirements/policy.py](C:/stm32/stm32agent/src/stm32cubep_mcp/requirements/policy.py)

New modules:

```text
intent/
  classifiers.py
  target_detection.py
  project_context.py
  prompt_analysis.py
  policy.py
application/services/
  plan_service.py
```

Move:

- prompt classification and target detection into `intent/*`
- markdown plan persistence into `application/services/plan_service.py`

Keep [requirements/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/requirements/server.py) as the MCP wrapper and compatibility facade.

#### Step 2.3: Split `ioc_builder`

Current files:

- [ioc_builder/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/ioc_builder/server.py)
- [ioc_builder/ioc_construct.py](C:/stm32/stm32agent/src/stm32cubep_mcp/ioc_builder/ioc_construct.py)
- [ioc_builder/ioc_model.py](C:/stm32/stm32agent/src/stm32cubep_mcp/ioc_builder/ioc_model.py)
- [ioc_builder/ioc_mutate.py](C:/stm32/stm32agent/src/stm32cubep_mcp/ioc_builder/ioc_mutate.py)
- [ioc_builder/ioc_validate.py](C:/stm32/stm32agent/src/stm32cubep_mcp/ioc_builder/ioc_validate.py)
- [ioc_builder/st_mcu_catalog.py](C:/stm32/stm32agent/src/stm32cubep_mcp/ioc_builder/st_mcu_catalog.py)
- [ioc_builder/st_seed_catalog.py](C:/stm32/stm32agent/src/stm32cubep_mcp/ioc_builder/st_seed_catalog.py)

New modules:

```text
ioc/
  baseline_selector.py
  mutator.py
  validator.py
  model.py
  operation_ir.py
  script_builder.py
  board_catalog.py
  mcu_catalog.py
```

In this phase, `operation_ir.py` can exist with only the initial `IocOperation` model and simple helper constructors. The full compiler can come later.

Keep [ioc_builder/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/ioc_builder/server.py) as the MCP wrapper and transitional facade.

#### Step 2.4: Split Tool Adapters Out Of Server Modules

Current files:

- [build/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/build/server.py)
- [cubemx/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/cubemx/server.py)
- [cube_programmer/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/cube_programmer/server.py)
- [debug/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/debug/server.py)

New modules:

```text
tools/
  cubeide_adapter.py
  cubemx_adapter.py
  programmer_adapter.py
  stlink_gdb_adapter.py
```

Move:

- executable discovery
- process spawning
- command construction
- log handling
- exit-code interpretation

Do not move high-level workflow logic here.

#### Step 2.5: Split Application Workflows Out Of The Orchestrator

Current file:

- [orchestrator/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/orchestrator/server.py)

New modules:

```text
application/workflows/
  generate_project.py
  extend_project.py
  build_flash_test.py
  live_debug.py
application/services/
  workflow_state.py
  artifact_service.py
  failure_service.py
```

Move:

- feature-delivery loop into `generate_project.py`
- build-then-flash orchestration into `build_flash_test.py`
- debug session orchestration into `live_debug.py`

Keep [orchestrator/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/orchestrator/server.py) as the MCP entrypoint and routing facade.

### Suggested Pull Request Slices

To keep risk manageable, split the package refactor into small PR-sized slices:

1. `shared.py` extraction only
2. `project_model` and plan service introduction
3. `tools/*` adapter extraction
4. `application/workflows/*` extraction from orchestrator
5. `ioc/*` extraction without behavior change

### Acceptance Criteria

- old imports still work
- MCP tool names and output shape stay stable
- no end-to-end feature should regress because of imports alone
- tests continue passing after each slice, not only at the end

## Workstream 3: Local CubeMX DB Indexing

### Goal

Introduce a first-class read-only indexing layer for the local CubeMX database.

This is the foundation for a generic future system because it reduces hard-coded STM32 knowledge in Python and makes the local tool installation part of the deterministic backend.

### Why Local CubeMX DB Comes In Phase 1

This machine already has rich local CubeMX data under:

- [db/mcu](</C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/db/mcu>)
- [db/mcu/config](</C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/db/mcu/config>)
- [db/mcu/config/llConfig](</C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/db/mcu/config/llConfig>)
- [db/plugins/boardmanager/boards](</C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/db/plugins/boardmanager/boards>)

This local data is richer than the public GitHub `STM32_open_pin_data` repo and should become the primary metadata source.

### Scope For The First Index

Do not try to index everything at once.

The first index should support only these queries:

1. list available board baseline IOCs
2. resolve board ID to baseline IOC path
3. resolve MCU refname to family, line, package, and IP list
4. resolve MCU pin to supported signal names
5. resolve signal name to candidate pins
6. list available IP config files for an MCU family
7. resolve basic DMA LL mapping entries

### New Modules

Create:

```text
src/stm32cubep_mcp/knowledge/cubemx_db/
  __init__.py
  indexer.py
  models.py
  cache.py
  query.py
  sources.py
```

### Cache Strategy

Cache normalized JSON under the workspace, not inside the CubeMX installation directory.

Recommended path:

- `generated/_cache/cubemx_db/<index-version>/`

This keeps the local installation read-only from the repo's point of view.

### Index Inputs

First-pass inputs:

- `db/plugins/boardmanager/boards/*.ioc`
- `db/mcu/*.xml`
- selected files from `db/mcu/config/*.xml`
- selected files from `db/mcu/config/llConfig/*.xml`

### Index Output Models

Suggested cached JSON groups:

- `boards.json`
- `mcu_catalog.json`
- `pin_signal_index.json`
- `family_config_index.json`
- `dma_ll_mapping.json`

### Integration Points

After the index exists, integrate it in shadow mode first.

That means:

- `ioc_builder` or future `ioc/baseline_selector.py` can query the index for board baselines
- existing hard-coded or direct-file logic stays in place as fallback until validated

### Initial Queries To Support

Recommended query functions:

- `list_board_iocs()`
- `find_board_baseline(board_id)`
- `find_mcu(refname)`
- `signals_for_pin(mcu_refname, pin_name)`
- `pins_for_signal(mcu_refname, signal_name)`
- `list_family_config_files(family_key)`
- `dma_request_mappings(family_key)`

### Testing Strategy

Add two kinds of tests:

1. fixture-based unit tests using small XML and IOC samples under `tests/fixtures/cubemx_db/`
2. optional local integration tests that run only when the local CubeMX install exists

This keeps CI realistic while still allowing richer host-side validation.

### Acceptance Criteria

- indexing can run without mutating the CubeMX install
- queries return stable normalized data
- board baselines for `NUCLEO-L476RG` resolve through the index
- index failures are reported cleanly and do not break the whole MCP server

## Sequence Of Execution

This is the recommended execution order for the real refactor:

1. add `project_model` contracts and adapters
2. route plan persistence through `PlanState`
3. extract `shared.py` into `shared_core/*`
4. extract tool adapters into `tools/*`
5. extract application workflows out of `orchestrator/server.py`
6. extract `ioc_builder` internals into `ioc/*`
7. add read-only CubeMX DB index and query modules
8. wire `baseline_selector` to consult the local DB index first

This order keeps behavior stable while increasing modularity quickly.

## Definition Of Done For Phase 1

Phase 1 is complete when all of the following are true:

- the current MCP surface still works
- internal contracts exist and are used in at least plan handling and orchestration boundaries
- the main `server.py` files are visibly thinner and delegate to extracted modules
- local CubeMX board baselines can be resolved through the new DB index
- the repo is ready for Phase 2 work on a generic IOC operation compiler

## Recommended First Implementation Slice

If we start coding immediately after this plan, I recommend this exact first slice:

1. create `project_model/` with `PlanState`, `ProjectState`, `Observation`, and adapters
2. extract plan persistence from [requirements/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/requirements/server.py) into `application/services/plan_service.py`
3. keep [requirements/server.py](C:/stm32/stm32agent/src/stm32cubep_mcp/requirements/server.py) as a wrapper over the new service
4. add unit tests for plan model round-trip and compatibility with the current `plan.md` format

That slice is small, useful, and low-risk. It also creates the first real seam for the larger refactor.
