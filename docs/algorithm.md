# STM32 Agent Planning And Execution Algorithm

## Purpose

This document defines the pre-implementation algorithm for the future requirement decomposition and execution workflow.

## High-Level Algorithm

```text
Algorithm LongHorizonSTM32Workflow
Input: user_request, project_context, optional plan_md
Output: updated plan_md, validated feature increments, execution artifacts

1. Load project context and current plan state.
2. Normalize the user request into a structured requirement draft.
3. Detect ambiguity, missing hardware assumptions, or unclear feature intent.
4. If ambiguity exists, request clarification and return to step 2.
5. Split requested work into:
   a. core features required for a minimal working system
   b. pluggable features that can be added incrementally
6. Order the work so core features execute before pluggable features.
7. Create or update plan.md with:
   a. feature list
   b. current status
   c. current execution slice
   d. known risks and failures
   e. next action
8. Select the smallest current execution slice.
9. Convert the selected slice into a structured requirements contract.
10. Pass the contract to deterministic execution:
    a. seed selection from ST board data or fallback template path
    b. canonical IOC model construction
    c. ST MCU and IP metadata resolution
    d. deterministic IOC mutation
    e. Python structural IOC validation
    f. CubeMX IOC acceptance check
    g. CubeMX regeneration
    h. project build
    i. target flash
    j. debug and runtime inspection
11. If any step fails:
    a. capture artifacts and failure details
    b. update plan.md
    c. choose repair, retry, or clarification
    d. repeat from the earliest necessary step
12. If the slice succeeds:
    a. mark the slice complete in plan.md
    b. select the next pluggable feature if any remain
13. Stop only when all planned features are complete or a blocking clarification is required.
```

## Detailed Modular Algorithm

### Phase 1: Requirement Decomposition

1. parse the request into intent, board assumptions, peripherals, and expected behavior
2. classify each requested capability as either core or pluggable
3. detect unsupported or ambiguous requests
4. produce a structured requirements contract with explicit feature boundaries

### Phase 2: Planning

1. create `plan.md` if it does not exist for the request
2. add ordered tasks with status values such as `pending`, `in_progress`, `blocked`, and `done`
3. record expected validation checkpoints for each feature slice
4. record failure history and next-action decisions

### Phase 3: Deterministic Execution

1. prepare IOC inputs from the current feature slice
2. select the official ST board seed IOC when available
3. if no board seed exists, select the best supported fallback template path
4. map the CubeMX-style MCU identifier to the appropriate ST grouped MCU XML naming pattern
5. parse `mcu/*.xml` and `mcu/IP/*.xml` into a capability view for the current target
6. construct the canonical IOC model with board, mcu, required peripherals, required signals, reserved pins, labels, clock requirements, and interrupt requirements
7. construct or update the IOC deterministically from the seed plus the canonical model
8. preserve board-reserved defaults while applying only the required deltas
9. run local structural IOC validation
10. run headless CubeMX to verify IOC acceptance
11. regenerate project files through CubeMX
12. wait for generation completion using the configured completion rule
13. build the project through the build toolchain
14. flash the binary to the target
15. inspect runtime behavior through debug and hardware observation

### Phase 3A: IOC Builder Algorithm

1. receive the structured requirements contract from the planning layer
2. resolve the board and MCU identity for the current slice
3. choose a board seed IOC from ST data if available
4. build the canonical IOC model from the contract
5. resolve legal peripherals, pins, GPIO modes, and IP options from ST metadata
6. allocate only the required signals while preserving reserved board resources
7. update IOC properties such as `Mcu.IP*`, `Mcu.Pin*`, and related blocks deterministically
8. validate the generated IOC locally
9. validate the generated IOC with CubeMX headless acceptance
10. return the accepted IOC and change summary to the orchestrator

### Phase 4: Recovery And Iteration

1. if seed selection fails, repair board-to-seed resolution or narrow supported scope
2. if metadata resolution fails, repair MCU-to-XML mapping or capability parsing
3. if IOC structural validation fails, repair the model or mutation logic
4. if CubeMX rejects the IOC, repair the generated IOC state before downstream regeneration
5. if generation fails, repair generation inputs or IOC state
6. if build fails, inspect logs and apply focused fixes
7. if flash fails, inspect programmer and connection failures
8. if runtime validation fails, inspect live target state and diagnose the defect
9. after repair, rerun only the necessary downstream steps

## Interface Contract Between Major Modules

Requirement Decomposition Agent output:

- structured requirements contract
- ordered feature list
- updated `plan.md`

Orchestrator input:

- selected feature slice
- project metadata
- deterministic tool payloads

Tool-domain outputs:

- generated files
- build artifacts
- flash results
- runtime observations
- diagnostics for feedback into planning

## Testability Requirements

Each algorithm stage should be testable independently:

1. prompt-to-requirements tests
2. core-versus-pluggable classification tests
3. `plan.md` state transition tests
4. board-seed resolution tests
5. MCU metadata resolution tests
6. canonical IOC model tests
7. IOC contract-to-generation tests
8. build and flash workflow tests
9. runtime diagnosis loop tests

## Exit Conditions

The workflow should exit only under one of these conditions:

1. all core and pluggable features in the current plan are complete
2. a blocking clarification is required from the user
3. a hard external dependency failure prevents further progress
```