# Requirement Decomposition Agent Phase 2 Design

## Purpose

This document records the Phase 2 architecture for building the Requirement Decomposition Agent and the deterministic IOC Synthesis Agent on top of the existing CubeMX, build, flash, and debug workflow.

The Phase 2 goal is to keep planning, deterministic execution, and IOC synthesis clearly separated so the codebase stays testable as the prompt understanding surface expands.

## Phase 2 Architecture

Phase 2 introduces three distinct roles:

1. Requirement Decomposition Agent
2. IOC Synthesis Agent
3. Deterministic Orchestrator

### Requirement Decomposition Agent

The Requirement Decomposition Agent owns prompt understanding and incremental planning.

It must:

- interpret vague, partial, and expert prompts
- normalize user intent into structured feature requirements
- split work into core features and pluggable features
- decide defaults where the user did not specify required project details
- maintain an incremental implementation plan and plan artifact
- decide when the next increment can proceed automatically
- decide when repeated failures require user review

It must not:

- directly invoke CubeMX, CubeIDE, or CubeProgrammer as its primary implementation surface
- become the low-level author of raw `.ioc` file text
- bypass deterministic execution contracts

### IOC Synthesis Agent

The IOC Synthesis Agent owns deterministic translation from one planned increment into an IOC change set.

It must:

- consume a structured requirements contract
- apply board-specific defaults deterministically
- map interfaces and project defaults into reproducible IOC properties
- report unsupported combinations clearly
- remain deterministic so it can be covered heavily by unit tests

It must not:

- perform open-ended prompt interpretation
- invent feature ordering
- own retry or recovery policy

### Deterministic Orchestrator

The orchestrator remains the execution layer.

It must:

- receive a current increment selected by the Requirement Decomposition Agent
- invoke IOC synthesis for that increment
- invoke CubeMX regeneration
- invoke CubeIDE build
- invoke CubeProgrammer flash
- invoke runtime or debug checks when requested
- return structured execution results back to the planning agent

It must not:

- become the planner
- interpret ambiguous product intent by itself
- own the long-term feature plan

## Initial Phase 2 Execution Loop

The initial loop is:

1. user prompt arrives
2. Requirement Decomposition Agent extracts feature intent
3. Requirement Decomposition Agent splits core and pluggable features
4. Requirement Decomposition Agent selects the next increment
5. IOC Synthesis Agent maps that increment into an IOC change set
6. orchestrator applies the deterministic tool workflow
7. execution results are written back to the plan state
8. next increment is selected or user review is requested

This preserves the Agile incremental process already captured in `design.md`.

## First Deterministic Contract

The first stable contract between Requirement Decomposition Agent and IOC Synthesis Agent is a structured JSON payload with these sections:

1. `contract_version`
2. `source_prompt`
3. `target`
4. `defaults`
5. `execution_policy`
6. `core_features`
7. `pluggable_features`
8. `current_increment`
9. `interface_intents`
10. `assumptions`
11. `open_questions`
12. `plan_file`

This contract is intentionally richer than a plain prompt summary. It is the stable handoff that allows:

- Requirement Decomposition tests to verify prompt normalization
- IOC Synthesis tests to verify deterministic mapping
- Orchestrator tests to verify correct sequencing without embedding planning logic

## Initial Supported Scope

Phase 2 initial scope must remain narrow.

The first supported prompt family is:

- NUCLEO-L476RG or STM32L476RG prompts
- device-to-PC serial transmit behavior
- STM32CubeIDE as the default toolchain
- incremental plan creation with one core feature batch and optional pluggable follow-up work

This first slice is intentionally constrained so the contract and synthesis logic can be tested before broader board and feature support is added.

## Testing Strategy

Phase 2 should be test-driven around the architecture boundaries.

### Requirement Decomposition tests

- prompt to structured contract normalization
- defaults applied consistently
- core vs pluggable feature split
- ambiguity reporting

### IOC Synthesis tests

- valid contract to deterministic IOC change set
- board profile defaults
- unsupported contract failures
- stable generated IOC property list

### Orchestrator tests

- correct sequencing for one increment
- stop on build or flash failure
- correct handoff between planning and deterministic tool execution

## Naming

The code-level package names should remain short and stable:

- `requirements`
- `ioc_builder`
- `orchestrator`

The design-level names should remain descriptive:

- Requirement Decomposition Agent
- IOC Synthesis Agent
- Deterministic Orchestrator

## Immediate Phase 2 Deliverables

The first implementation slice should provide:

1. a new `requirements` package
2. a new `ioc_builder` package
3. a shared deterministic contract definition
4. a schema file for that contract
5. focused unit tests covering the first supported prompt family