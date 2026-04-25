# Structured Requirements Contract

## Purpose

This document defines the exact structured requirements contract exchanged between the Requirement Decomposition Agent and the downstream deterministic execution layers.

It is the interface that the IOC Builder Agent, orchestrator, and status tracking logic should rely on.

## Contract Identity

- Contract version: `2026-04-24.phase3.v1`
- Current schema file: `src/stm32cubep_mcp/schemas/requirements-ioc-contract.schema.json`
- Runtime builder: `src/stm32cubep_mcp/requirements_ioc_contract.py`

## Required Top-Level Fields

The contract must include these top-level fields:

1. `contract_version`
2. `source_prompt`
3. `target`
4. `defaults`
5. `planning`
6. `execution_policy`
7. `core_features`
8. `pluggable_features`
9. `current_increment`
10. `interface_intents`
11. `assumptions`
12. `open_questions`
13. `plan_file`

## Contract Shape

```json
{
  "contract_version": "2026-04-24.phase3.v1",
  "source_prompt": "Create a NUCLEO-L476RG project that sends data to PC and validate it.",
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
  "execution_policy": {
    "mode": "incremental",
    "build_after_each_increment": true,
    "fix_build_before_proceeding": true,
    "flash_after_successful_build": true,
    "runtime_check_after_flash": true,
    "fix_runtime_before_next_increment": true,
    "ask_user_on_repeated_failures": true,
    "ioc_cubemx_validation": "best_effort"
  },
  "core_features": [],
  "pluggable_features": [],
  "current_increment": {
    "id": "increment-core-001",
    "title": "Enable the first core feature increment",
    "feature_ids": ["core-uart-device-to-pc"],
    "kind": "core"
  },
  "interface_intents": [],
  "assumptions": [],
  "open_questions": [],
  "plan_file": "C:/path/to/project/plan.md"
}
```

## Field Semantics

### `target`

This identifies the board and MCU that downstream deterministic layers must use for seed selection, metadata resolution, and validation.

### `defaults`

This captures execution defaults that are not feature-specific, such as toolchain and project style.

### `planning`

This makes the long-horizon execution intent explicit instead of leaving it implied.

Expected meanings:

- `horizon`: identifies the workflow as long-running rather than one-shot
- `core_first`: requires delivery of core capability before pluggable scope
- `increment_strategy`: requires narrow slices instead of multi-feature jumps
- `feature_progression`: preserves the expected ordering model
- `plan_format`: identifies the machine-readable artifact format for status tracking
- `status_file`: identifies the expected plan artifact filename

### `execution_policy`

This tells the orchestrator how to behave after each increment and how strictly validation gates are enforced.

Important field:

- `ioc_cubemx_validation`: controls whether CubeMX IOC acceptance is best-effort or mandatory

Allowed values:

- `best_effort`: if CubeMX is unavailable on the host, IOC validation is recorded as skipped and the workflow may continue
- `required`: if CubeMX is unavailable or rejects the IOC, the IOC Builder must fail the current slice

### `core_features` and `pluggable_features`

These arrays define the feature partition selected by the planning layer. Core features are required for a minimum working system. Pluggable features are optional or follow-on increments.

### `current_increment`

This identifies the exact slice currently being delivered. The orchestrator and IOC Builder should act only on this slice, not on the full backlog at once.

### `interface_intents`

This is the deterministic handoff from planning to hardware-facing configuration. It should contain the concrete interfaces the IOC Builder must realize, such as:

- UART console on a preferred instance
- LED output pin intent
- button interrupt intent

### `assumptions` and `open_questions`

These fields capture unresolved planning context without contaminating deterministic downstream execution. Downstream layers may report them, but should not guess beyond them.

### `plan_file`

This identifies the request-specific `plan.md` artifact that tracks lifecycle, failures, and resumable execution state.

## Contract Rules

1. the Requirement Decomposition Agent owns contract creation
2. the orchestrator consumes the contract but does not invent missing planning structure
3. the IOC Builder consumes deterministic fields only and must not reinterpret the prompt
4. downstream layers should fail clearly when the contract is invalid or underspecified

## Current Phase Scope

For the current implementation phase, the contract should remain narrow and optimized for:

- `NUCLEO-L476RG`
- deterministic IOC construction or mutation
- `device_to_pc_tx`
- incremental follow-on features such as LED and button behavior

## Relationship To Testing

This contract is the main test boundary for:

1. prompt-to-contract decomposition tests
2. schema validation tests
3. IOC Builder planning tests
4. orchestrator execution tests

Any future contract expansion should preserve backward reasoning and should be accompanied by a version update when semantics change materially.