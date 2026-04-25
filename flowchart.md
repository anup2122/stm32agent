# STM32 Agent Workflow Flowchart

## Purpose

This document captures the execution flow for the future long-horizon STM32 workflow before implementation begins.

## End-To-End Flow

```mermaid
flowchart TD
    A[Receive User Request] --> B[Load Project Context and Existing plan.md]
    B --> C[Requirement Decomposition]
    C --> D{Ambiguity Present?}
    D -- Yes --> E[Ask Clarifying Questions]
    E --> C
    D -- No --> F[Split into Core and Pluggable Features]
    F --> G[Create or Update plan.md]
    G --> H[Select Current Execution Slice]
    H --> I{Core Feature Done?}
    I -- No --> J[Pick Next Core Feature Step]
    I -- Yes --> K[Pick Next Pluggable Feature]
    J --> L[Build Structured Requirements Contract]
    K --> L
    L --> M[Select ST Board Seed or Fallback Template]
    M --> N[Build Canonical IOC Model]
    N --> O[Resolve ST MCU and IP Metadata]
    O --> P[Apply Deterministic IOC Mutation]
    P --> Q[Run Python Structural IOC Validation]
    Q --> R{IOC Structurally Valid?}
    R -- No --> S[Capture IOC Failure and Update plan.md]
    S --> T[Repair Contract, Seed Choice, or Mutation Rules]
    T --> L
    R -- Yes --> U[Run Headless CubeMX IOC Acceptance Check]
    U --> V{CubeMX Accepts IOC?}
    V -- No --> W[Capture CubeMX IOC Rejection]
    W --> T
    V -- Yes --> X[Run CubeMX Regeneration]
    X --> Y{Generation Succeeded?}
    Y -- No --> Z[Capture Generation Failure and Update plan.md]
    Z --> T
    Y -- Yes --> AA[Build Project]
    AA --> AB{Build Succeeded?}
    AB -- No --> AC[Analyze Build Errors]
    AC --> AD[Apply Focused Repair]
    AD --> G
    AB -- Yes --> AE[Flash Target]
    AE --> AF{Flash Succeeded?}
    AF -- No --> AG[Capture Flash Failure]
    AG --> G
    AF -- Yes --> AH[Launch Debug and Runtime Inspection]
    AH --> AI{Runtime Behavior Correct?}
    AI -- No --> AJ[Diagnose Runtime Defect]
    AJ --> AK[Update plan.md and Repair Path]
    AK --> G
    AI -- Yes --> AL[Mark Slice Complete in plan.md]
    AL --> AM{More Pluggable Features Remaining?}
    AM -- Yes --> K
    AM -- No --> AN[Finalize Plan and Report Results]
```

## Flow Rules

1. never jump directly from prompt to full implementation in one step
2. always create or update `plan.md` before major execution begins
3. always implement core capability before optional pluggable features
4. only add one pluggable feature per loop
5. each loop must include seed selection, IOC modeling, deterministic mutation, IOC validation, generation, build, flash, and runtime validation when applicable
6. failures must feed back into the plan instead of being treated as terminal by default

## Decision Points

The key decision points are:

- whether the request is ambiguous
- whether the current slice is still core scope or has moved into pluggable scope
- whether IOC structural checks, CubeMX IOC acceptance, generation, build, flash, and runtime checks succeeded
- whether the next action is repair, clarification, or feature advancement

## IOC Builder Subflow

The IOC Builder portion of the flow is intentionally decomposed into these stages:

1. select a trusted ST board seed IOC when available
2. convert the requirements contract into a canonical IOC model
3. resolve legal MCU and IP capabilities from ST metadata
4. apply deterministic seed-preserving mutations
5. validate locally before using CubeMX as the final IOC accept or reject oracle

This keeps the critical IOC path deterministic and reviewable before downstream generation begins.
