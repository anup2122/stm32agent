from __future__ import annotations

import re

SUPPORTED_PROMPT_FAMILIES = [
    "NUCLEO-L476RG device-to-PC serial transmit",
    "NUCLEO-L476RG LED blink",
    "NUCLEO-L476RG button event to PC",
]

EXISTING_PROJECT_TOKENS = (
    "existing project",
    "current project",
    "running project",
    "old project",
    "reuse project",
    "modify project",
    "update project",
    "existing ioc",
    "existing codebase",
)

NEW_PROJECT_TOKENS = (
    "new project",
    "create a project",
    "create project",
    "write a project",
    "generate project",
    "start a project",
    "fresh project",
)

NEW_DEVICE_TOKENS = (
    "new device",
    "new board",
    "fresh board",
    "fresh device",
    "attached device",
)

ENGINEERING_SPEC_TOKENS = (
    "objective is to configure",
    "the following configuration values are used in this project",
    "this project has to be tested with",
    "pulse width modulation",
    "duty cycle",
    "systemcoreclock is set to",
)


def looks_like_engineering_feature_spec(prompt: str) -> bool:
    lowered = prompt.strip().lower()
    has_target = any(token in lowered for token in ("nucleo", "stm32", "board", "device"))
    if not has_target:
        return False
    if any(token in lowered for token in ENGINEERING_SPEC_TOKENS):
        return True
    return bool(re.search(r"\bconfigure\b.*\b(project|tim|timer|dma|pwm)\b", lowered))
