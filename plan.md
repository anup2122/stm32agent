# Workflow Plan Template

## Purpose

This file defines the canonical structure and lifecycle for the request-specific `plan.md` artifact used by the long-horizon STM32 workflow.

The runtime system should generate a per-request `plan.md` near the active project or IOC path. This root document is the reference template for that generated artifact.

## Goals

- provide a human-readable progress file for long-running work
- preserve machine-readable workflow state for deterministic orchestration
- record core-first then pluggable-feature progression
- support resume, retry, and diagnosis after failures

## Required Sections

Each generated `plan.md` should contain these human-readable sections:

1. `# Workflow Plan`
2. `## Summary`
3. `## Current Increment`
4. `## Open Questions`
5. `## Assumptions`
6. `## Stage History`

At the end of the file, it must also include an embedded machine-readable state block delimited by these markers:

- `<!-- plan-state:start -->`
- `<!-- plan-state:end -->`

The payload between those markers should be a JSON object wrapped in a fenced `json` block.

## Human-Readable Template

```markdown
# Workflow Plan

## Summary
- Workflow status: `planned`
- Current stage: `requirements`
- Board: `NUCLEO-L476RG`
- MCU: `STM32L476RGTx`

## Current Increment
- ID: `increment-core-001`
- Title: Enable the first core feature increment
- Feature IDs: core-uart-device-to-pc

## Open Questions
- None

## Assumptions
- Host serial console will use USART2 on the board default pins.

## Stage History
- `2026-04-24T00:00:00Z` `requirements` `completed`: Requirements decomposition completed.
```

## Embedded Machine State Template

```markdown
<!-- plan-state:start -->
```json
{
  "plan_version": "2026-04-24.phase3.plan.v1",
  "contract_version": "2026-04-24.phase3.v1",
  "source_prompt": "Create a NUCLEO-L476RG project that sends data to PC.",
  "target": {
    "board_id": "NUCLEO-L476RG",
    "mcu": "STM32L476RGTx"
  },
  "defaults": {
    "toolchain": "STM32CubeIDE",
    "project_style": "ioc_incremental",
    "language": "c"
  },
  "planning": {
    "horizon": "long_horizon",
    "core_first": true,
    "increment_strategy": "single_slice",
    "feature_progression": "core_then_pluggable",
    "plan_format": "markdown_embedded_json",
    "status_file": "plan.md"
  },
  "current_increment": {
    "id": "increment-core-001",
    "title": "Enable the first core feature increment",
    "feature_ids": ["core-uart-device-to-pc"],
    "kind": "core"
  },
  "core_features": [],
  "pluggable_features": [],
  "execution_policy": {},
  "assumptions": [],
  "open_questions": [],
  "workflow_status": "planned",
  "current_stage": "requirements",
  "current_stage_message": "Requirements decomposition created the first deterministic contract.",
  "current_stage_details": {},
  "failure_count": 0,
  "stage_history": [],
  "created_utc": "2026-04-24T00:00:00Z",
  "last_updated_utc": "2026-04-24T00:00:00Z",
  "last_heartbeat_utc": "2026-04-24T00:00:00Z"
}
```
<!-- plan-state:end -->
```

## Status Lifecycle

The `workflow_status` field should use a narrow status set:

- `planned`: request decomposition completed and execution has not meaningfully started
- `in_progress`: the current stage is actively running
- `completed`: the full planned scope for the current request is complete
- `failed`: the current stage failed and requires repair or clarification
- `blocked`: progress cannot continue until an external dependency or user clarification is resolved

## Stage Lifecycle

The `current_stage` field should move through a deterministic sequence such as:

1. `requirements`
2. `ioc_builder`
3. `cubemx`
4. `build`
5. `artifact_resolution`
6. `flash`
7. `debug`
8. `runtime_validation`

Additional stages are allowed when needed, but they should stay domain-local and precise.

## Update Rules

1. every major workflow transition must update `current_stage`, `current_stage_message`, and `last_updated_utc`
2. heartbeat-style refreshes may update live status fields without appending history entries
3. terminal or milestone transitions should append a `stage_history` event
4. failures must increment `failure_count`
5. repairs should preserve prior history instead of rewriting it
6. when IOC Builder runs, status details should preserve any `cubemx_validation` evidence produced during IOC acceptance checks

## Resume Rules

When a workflow resumes from an existing `plan.md`, the system should:

1. parse the embedded JSON state
2. trust the machine-readable state as the orchestration source of truth
3. use the human-readable sections only for operator review
4. continue from the earliest unresolved or failed deterministic stage

## Design Constraint

`plan.md` is not a freeform note file. It is a controlled workflow artifact with both human-readable and machine-readable responsibilities.