from __future__ import annotations

import re
from typing import Literal

WorkflowRoute = Literal["cube_programmer", "build", "build_flash", "debug", "cubemx", "requirements", "unknown"]

BUILD_PROMPT_TOKENS = ("build", "compile", "cubeide", "cmake", "make", "headlessbuild")
FLASH_PROMPT_TOKENS = ("flash", "program", "download", "erase", "reset", "connect", "st-link", "verify")
DEBUG_PROMPT_TOKENS = ("breakpoint", "gdb", "register", "snapshot", "debug", "attach", "uart", "usart", "baud", "peripheral", "gpio", "timer", "spi", "i2c", "adc", "rcc")
FEATURE_PROMPT_TOKENS = ("write a project", "create project", "generate project", "send data", "transmit", "blink", "button")
FEATURE_SPEC_TOKENS = (
    "objective is to configure",
    "the following configuration values are used in this project",
    "this project has to be tested with",
    "pulse width modulation",
    "duty cycle",
    "systemcoreclock is set to",
)


def classify_prompt(prompt: str) -> WorkflowRoute:
    lowered = prompt.strip().lower()
    has_feature_target = any(token in lowered for token in ("nucleo", "stm32", "device", "board", "pc"))
    has_feature_creation_hint = any(token in lowered for token in FEATURE_PROMPT_TOKENS) or bool(
        re.search(r"\b(create|write|generate|implement|develop|configure|update|modify|extend)\b.*\bproject\b", lowered)
    )
    has_feature_spec_hint = any(token in lowered for token in FEATURE_SPEC_TOKENS)
    if has_feature_target and (has_feature_creation_hint or has_feature_spec_hint):
        return "requirements"
    if any(token in lowered for token in ("cube mx", "cubemx", ".ioc", "regenerate project", "parse ioc")):
        return "cubemx"
    if any(token in lowered for token in DEBUG_PROMPT_TOKENS):
        return "debug"
    if any(token in lowered for token in BUILD_PROMPT_TOKENS) and any(token in lowered for token in FLASH_PROMPT_TOKENS):
        return "build_flash"
    if any(token in lowered for token in BUILD_PROMPT_TOKENS):
        return "build"
    if any(token in lowered for token in FLASH_PROMPT_TOKENS):
        return "cube_programmer"
    return "unknown"


def extract_file_path(prompt: str) -> str | None:
    match = re.search(r"file_path\s*=\s*([\S]+)", prompt)
    if match is None:
        return None
    return match.group(1).strip('"\'')


def is_debug_question(prompt: str) -> bool:
    lowered = prompt.strip().lower()
    return any(token in lowered for token in ("what", "which", "show", "read", "inspect", "tell me"))
