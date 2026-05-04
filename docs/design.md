# CubeMX Design Notes

## Purpose

This document records the planning discussion and design decisions made during the CubeMX planning context on 2026-04-16. It is intended to be the handoff reference before starting CubeMX agent implementation work.

## Why CubeMX Needs Separate Planning

CubeMX is expected to be the most complex part of the STM32 Agent Toolchain for these reasons:

- It is structurally different from programmer, build, and debug tooling.
- It is usually used through a graphical workflow, while this project needs reliable command-line use.
- The hardest problem is not only tool invocation, but also correctly understanding what the user wants to build.
- CubeMX workflows are naturally waterfall-oriented, while this agent must support iterative, incremental development.

## User Guidance Captured In This Context

The following user intent was established and accepted during this planning context:

1. CubeMX is likely the most complex area, so the work should be carefully staged.
2. CubeMX is mostly known as a graphics-driven tool, but the agent still needs to use command-line mode.
3. User prompts may be incomplete, vague, or expert-level, so the long-term design must eventually support both unclear and precise requirements.
4. The project should not follow CubeMX's natural waterfall workflow. Instead, the agent should use an Agile, iterative, incremental process.
5. The STM32CubeMX user manual was added to the workspace at the root as `stm32CubeMX_um1718_user_manual.pdf`, with the relevant reference being Section 3.3.2 on command-line mode.
6. The first request in this planning phase was to think and share a plan without implementing CubeMX yet.

## Core Process Model Agreed In This Context

The agreed process for future CubeMX-driven development is:

1. Convert user requirements into core features and pluggable features.
2. Implement the core features first.
3. Build after each increment.
4. Fix build bugs before proceeding.
5. Download to the device after successful build.
6. Check runtime behavior on hardware.
7. Fix runtime bugs before proceeding.
8. Add pluggable features one by one using the same cycle.
9. Keep a plan file that records progress and failures.
10. Ask the user to review the plan file if the agent gets stuck or repeated failures occur.

This means CubeMX integration is not treated as one large code-generation step. It is treated as an iterative engineering loop.

## Architecture Decisions

### 1. CubeMX Should Be Integrated Before Requirement Decomposition

This was the final sequencing decision reached in this context.

CubeMX integration should come before the requirement decomposition agent because:

- An existing `.ioc` file provides a deterministic starting point.
- It lets the project solve structural and regeneration issues first.
- It reduces architectural ambiguity before adding prompt interpretation complexity.
- It gives the future requirement decomposition agent a stable backend to target.

### 2. The Existing `.ioc` File Should Be The Starting Point

The first CubeMX work should use the prior available `.ioc` file rather than trying to generate a project from abstract requirements immediately.

Why:

- It provides a real project state.
- It exposes regeneration boundaries and file overwrite behavior early.
- It allows validation of command-line generation on a known project.
- It reduces risk before freeform requirement interpretation is introduced.

### 3. Requirement Decomposition Should Not Live In The Orchestration Agent

This was a later correction to the initial architecture proposal.

The orchestration agent should remain deterministic and tool-focused. It should only:

- read current state
- sequence workflows
- call MCP tools
- normalize results

Requirement decomposition, feature ordering, and recovery loops should eventually live in a separate requirement decomposition agent because:

- it may need backend LLM support
- it may later use GitHub search or other external tools
- it is optional and should be possible to disable independently
- it handles ambiguity rather than deterministic execution

### 4. Requirement Decomposition Agent Is Deferred Until Later

Although the separate requirement decomposition agent is the preferred long-term architecture, it should be developed after the first CubeMX backend work.

Reason:

- the CubeMX backend must first prove that it can inspect, regenerate, build, flash, and validate an IOC-driven project reliably

So the order is:

1. CubeMX backend on existing IOC
2. Stable regeneration/build/flash/debug loop
3. Requirement decomposition agent on top of that backend

### 5. Orchestration Agent Stays Narrow

The main orchestration agent should remain a tool-calling execution layer and should not become the planner.

It should:

- invoke programmer, build, debug, and CubeMX tools
- execute already decided steps
- report results and failures clearly

It should not:

- interpret ambiguous product requirements
- invent feature breakdowns
- run open-ended planning by itself

### 6. Host Tool Resolution Should Be Layered And Cross-Platform

The STM32 MCP servers should not assume VS Code, one operating system, or one
manual setup path.

The preferred host-tool resolution order is:

1. explicit request override when a workflow provides one
2. environment variable override for CI, containers, and non-VS Code clients
3. machine-local `stm32-tools.local.json`
4. OS-specific discovery through adapter modules and standard install paths
5. readiness or bootstrap guidance when no valid tool path is found

This keeps the servers portable across Windows, Linux, macOS, and different MCP
clients while preserving deterministic execution.

Normal MCP tool calls should use cheap path resolution and cached in-process
results when practical. Expensive version probes and full host diagnostics
should remain in readiness or capabilities flows rather than delaying every
agent invocation.

The adapter boundary should stay narrow:

- adapters own tool discovery, launch-path resolution, command construction,
  and raw subprocess execution
- server and workflow layers own retries, recovery policy, session management,
  structured result shaping, and orchestration decisions

The current refactor in this repository follows that split more strictly:

- STM32CubeProgrammer adapters own connect and operation command construction
    plus cached host-tool discovery
- ST-LINK GDB server and ARM GDB adapters own launch, list, batch, and version
    command construction plus cached host-tool discovery
- debug and programmer server modules keep stable wrapper functions so tests and
    callers can still patch server-level seams while execution policy remains in
    the server layer

This is why CubeIDE and CubeMX already fit naturally into adapters, and why the
same structure should be applied to STM32CubeProgrammer, ST-LINK GDB server,
and ARM GDB over time.

## CubeMX-First Development Strategy

The first CubeMX implementation phase should focus on deterministic backend capability, not prompt intelligence.

### CubeMX Part 1 Goals

1. Locate and validate the existing `.ioc` file.
2. Confirm STM32CubeMX command-line availability on the host.
3. Inspect the existing IOC-backed project state.
4. Regenerate the current project without semantic changes.
5. Confirm that regeneration preserves expected structure.
6. Build the regenerated project using the existing Build MCP.
7. Record outputs, failures, and affected files.

### What CubeMX Part 1 Should Not Try To Do

- full freeform requirement understanding
- broad requirement decomposition
- complex feature synthesis from natural language
- autonomous recovery planning beyond simple deterministic handling
- large multi-feature project creation from scratch

## Prompt Understanding Strategy For Later

Even though requirement decomposition is deferred, the discussion established that prompt understanding will eventually need to support three user categories:

- beginner users with vague requests
- intermediate users with partially specified requests
- expert users with precise hardware and peripheral requirements

The future prompt corpus should contain sample prompts across all three levels and should be reviewed before building the decomposition agent.

## Planned Future Requirement Decomposition Agent

The future requirement decomposition agent should:

- follow Agile iterative development rather than CubeMX's natural waterfall flow
- convert user intent into structured requirements
- split work into core and pluggable features
- detect ambiguity and request clarification when needed
- produce incremental execution plans
- optionally use backend LLMs, GitHub search, and other research tools
- start with the core feature set and then advance one pluggable feature at a time
- maintain a request-specific `plan.md` artifact with step status, failures, retries, and next actions
- support long-horizon execution rather than assuming a one-shot prompt-to-code flow
- keep the work extremely modular so prompt interpretation, planning, tool invocation, and validation can be tested independently
- allow the workflow to continue from regenerate/build/flash into debug launch, runtime inspection, and diagnosis on the attached target
- remain independently switchable on or off

The future requirement decomposition agent should not be required for users who already know exactly what they want.

### Additional Execution Constraints For The Future Requirement Decomposition Agent

The execution model for this agent should preserve the same engineering discipline already established elsewhere in this design:

1. every request should be normalized into a structured plan that distinguishes core scope from optional pluggable scope
2. the first execution loop should target only the core feature set needed to produce a valid working system
3. each additional pluggable feature should then be introduced one at a time using the same regenerate, build, flash, debug, and diagnose loop
4. the agent should update `plan.md` throughout execution so long-running work can be resumed, reviewed, or corrected without losing state
5. the planning layer should remain separate from deterministic tool-domain MCP execution so prompt-to-tool translation stays modular and testable
6. each module in the pipeline should expose narrow inputs and outputs so detailed automated tests can validate prompt parsing, requirements contracts, feature ordering, orchestration, and downstream tool calls independently

This means the future requirement decomposition agent is not just a parser for user prompts. It is the long-horizon planning layer that should decide execution order, maintain progress state, and hand small deterministic steps to the orchestration layer.

## Relationship Between The Major Components

### Tool-domain MCP servers

- STM32CubeProgrammer MCP handles connect, flash, reset, memory, and diagnostics.
- Build MCP handles CubeIDE builds.
- Debug MCP handles runtime debug and hardware inspection.
- CubeMX MCP will handle IOC inspection and regeneration.

### Orchestration agent

- Executes deterministic workflow steps.
- Calls tool-domain MCP servers.
- Does not own open-ended requirement planning.

### Future requirement decomposition agent

- Understands user intent.
- Produces feature breakdown and execution plans.
- Hands structured output to the orchestration layer.

## Immediate Recommendation For The Next Context

The next context should begin actual development of CubeMX agent Part 1 using the existing IOC file.

The recommended implementation order is:

1. inspect the current CubeMX scaffold in `src/stm32cubep_mcp/cubemx/server.py`
2. find and validate the current `.ioc` file from project metadata or workspace
3. discover the STM32CubeMX executable and command-line mode availability
4. implement IOC existence and metadata inspection more deeply than the current scaffold
5. implement deterministic project regeneration for the existing IOC
6. connect regeneration to the existing Build MCP for validation
7. document logs, file outputs, and failure points

## Constraints To Preserve

- keep the architecture modular by domain
- keep orchestration deterministic
- keep planning separate from tool execution
- prefer iterative, incremental feature addition over one-shot generation
- always record failures and progress in plan artifacts

## CubeMX Script-Driven Regeneration Update

This section records the revised deterministic CubeMX flow established on 2026-04-21.

### Required CubeMX Invocation

CubeMX regeneration must be launched with a script file path passed directly to the executable:

`STM32CubeMX.exe -q <script.txt>`

The agent must not rely on the older inline `generate code` command form as the primary workflow.

### Required Script Contents

The generated `script.txt` must contain these project-specific fields:

1. `config load "<ioc-file-path>"`
2. `project name "<project-name>"`
3. `project toolchain "<project-toolchain>"`
4. `project path "<project-path>"`
5. `project generate`
6. `exit_mx`

The `.ioc` file path is passed inside the script through `config load`. The script file path itself is what is passed to `STM32CubeMX.exe -q`.

### Project Metadata Contract

The orchestration layer must read the CubeMX project inputs from the project-specific JSON configuration and pass them explicitly to the CubeMX agent.

The first implementation step must therefore support this exact handoff:

1. orchestrator reads the project JSON
2. orchestrator extracts the IOC file path, project name, project toolchain, and project path
3. orchestrator calls the CubeMX agent with those resolved values
4. CubeMX agent writes `script.txt`
5. CubeMX agent launches `STM32CubeMX.exe -q <script.txt>`

This keeps orchestration deterministic while still making the CubeMX contract explicit.

### Completion Detection And Polling

`STM32CubeMX.exe -q <script.txt>` can return before generation is actually complete. The agent must therefore not treat process exit alone as regeneration completion.

The first completion rule is:

1. launch CubeMX with the script path
2. poll for creation of `STM32CubeIDE/.project` under the configured project path
3. keep waiting until the file appears or the overall timeout expires
4. only then continue to output review and optional build validation

Polling must use an overall timeout budget suitable for long-running generations. Small projects may take 4 to 5 minutes, and larger projects may take longer.

### Initial Implementation Scope

The immediate implementation scope for this revision is:

1. add project metadata fields needed for CubeMX script generation to the project schema and sample config
2. implement a helper that resolves the CubeMX script payload from project metadata
3. make the orchestrator pass that payload into the CubeMX MCP server
4. make the CubeMX MCP server write the script file and invoke CubeMX with `-q <script.txt>`
5. add polling for `STM32CubeIDE/.project` creation under the configured project path
6. keep existing build validation after successful polling-based completion detection

### Failure Handling Requirements

The revised CubeMX flow must report these failures clearly:

1. required project metadata is missing from the project JSON
2. script file creation failed
3. CubeMX process launch failed
4. CubeMX returned but the expected `STM32CubeIDE/.project` file did not appear before timeout
5. build validation failed after successful regeneration

Each failure should be logged together with the generated script contents and the expected project path so the user can inspect the exact regeneration contract that was used.

### Follow-Up Backlog After Real Host Validation

The real host validation on 2026-04-21 added two concrete follow-up requirements:

1. add a CubeIDE error-fix path so the agent can inspect headless build failures, locate the relevant generated CubeIDE or Eclipse logs, and apply targeted repair steps instead of stopping at a raw build failure
2. add live debugging support for the running image so the workflow can continue from regenerate/build/flash into debug launch, runtime inspection, and diagnosis on the attached target

These are follow-up capabilities and should be implemented on top of the now-validated regenerate/build/flash baseline.

## Final Decision Snapshot

The final state of the discussion in this context was:

- Yes to CubeMX command-line integration.
- Yes to Agile iterative development over CubeMX's waterfall-style workflow.
- Yes to using an existing IOC file first.
- Yes to solving structural and regeneration issues before prompt intelligence.
- Yes to a future separate requirement decomposition agent.
- No to embedding requirement decomposition inside the orchestration agent.
- No to building the requirement decomposition agent before the CubeMX backend is stable.

## Handoff Note

This file is the continuity anchor for starting a new development context focused on CubeMX agent Part 1.

## 2026-04-24 IOC Builder Construction Discussion

This section records the next design discussion for the IOC Builder Agent after the initial Phase 2 implementation.

### Current Direction Under Discussion

The IOC Builder Agent should evolve from a deterministic IOC patcher into a deterministic IOC construction engine.

The target behavior being discussed is:

1. accept a structured requirements contract from the Requirement Decomposition Agent
2. use a board-specific reference such as a known-good NUCLEO-L476RG IOC or seed template
3. construct or reconstruct a valid IOC file even when the working project IOC is missing
4. preserve deterministic behavior so the output remains testable and reproducible
5. hand the resulting IOC to the existing CubeMX regenerate/build/flash workflow

### Questions To Resolve

The next discussion should focus on these technical questions:

1. should the IOC Builder operate primarily as a seed-and-mutate system, a full IOC emitter, or a hybrid of both
2. what board-specific assets and metadata are required to support deterministic IOC construction
3. what canonical internal model should exist between the requirements contract and final IOC text
4. how should peripheral selection, pin assignment, and conflict resolution be represented and validated
5. how should the agent validate that a constructed IOC is acceptable to CubeMX before downstream build and flash steps
6. what minimum scope should be implemented first for NUCLEO-L476RG and UART-to-PC delivery

### Constraints To Preserve In This Discussion

- keep prompt understanding in the Requirement Decomposition Agent
- keep the IOC Builder deterministic and board-aware
- keep orchestration as a narrow execution layer
- prefer an implementation path that can be validated incrementally on real hardware
- avoid designs that depend on freeform LLM text generation of raw IOC contents