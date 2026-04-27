from __future__ import annotations

import re
from typing import Literal

WorkflowRoute = Literal["develop_agent", "cube_programmer", "build", "build_flash", "debug", "cubemx", "requirements", "unknown"]
PromptMode = Literal["auto", "develop-agent", "firmware-delivery", "test-only", "inspect-only"]

BUILD_PROMPT_TOKENS = ("build", "compile", "cubeide", "cmake", "make", "headlessbuild")
FLASH_PROMPT_TOKENS = ("flash", "program", "download", "erase", "reset", "connect", "st-link", "verify")
DEBUG_PROMPT_TOKENS = ("breakpoint", "gdb", "register", "snapshot", "debug", "attach", "uart", "usart", "baud", "peripheral", "gpio", "timer", "spi", "i2c", "adc", "rcc")
FEATURE_PROMPT_TOKENS = ("write a project", "create project", "generate project", "send data", "transmit", "blink", "button")
DEVELOP_AGENT_TOKENS = (
    "add feature",
    "add a feature",
    "extend the server",
    "extend server",
    "mcp tool",
    "mcp server",
    "orchestrator",
    "routing policy",
    "develop-agent",
    "agent development",
    "server feature",
)
INSPECT_ONLY_TOKENS = ("inspect-only", "status", "capabilities", "readiness", "what is configured", "report host")
FEATURE_SPEC_TOKENS = (
    "objective is to configure",
    "the following configuration values are used in this project",
    "this project has to be tested with",
    "pulse width modulation",
    "duty cycle",
    "systemcoreclock is set to",
)
PROMPT_MODE_PREFIX_PATTERN = re.compile(r"^\s*(develop-agent|firmware-delivery|test-only|inspect-only)\s*:\s*", re.IGNORECASE)


def normalize_prompt_mode(mode: str | None) -> PromptMode:
    if not isinstance(mode, str) or not mode.strip():
        return "auto"
    normalized = mode.strip().lower().replace("_", "-")
    if normalized in {"auto", "develop-agent", "firmware-delivery", "test-only", "inspect-only"}:
        return normalized  # type: ignore[return-value]
    return "auto"


def split_prompt_mode_prefix(prompt: str) -> tuple[PromptMode | None, str]:
    match = PROMPT_MODE_PREFIX_PATTERN.match(prompt)
    if match is None:
        return None, prompt
    return normalize_prompt_mode(match.group(1)), prompt[match.end() :]


def prompt_without_mode_prefix(prompt: str) -> str:
    return split_prompt_mode_prefix(prompt)[1]


def resolve_prompt_mode(prompt: str, requested_mode: str | None = "auto") -> PromptMode:
    normalized_mode = normalize_prompt_mode(requested_mode)
    if normalized_mode != "auto":
        return normalized_mode

    prefixed_mode, unprefixed_prompt = split_prompt_mode_prefix(prompt)
    if prefixed_mode is not None:
        return prefixed_mode

    lowered = unprefixed_prompt.strip().lower()
    if any(token in lowered for token in DEVELOP_AGENT_TOKENS):
        return "develop-agent"
    if any(token in lowered for token in INSPECT_ONLY_TOKENS):
        return "inspect-only"
    if classify_prompt(unprefixed_prompt) == "requirements":
        return "firmware-delivery"
    if classify_prompt(unprefixed_prompt) in {"build", "build_flash", "cube_programmer", "debug", "cubemx"}:
        return "test-only"
    return "develop-agent"


def classify_prompt(prompt: str) -> WorkflowRoute:
    prompt = prompt_without_mode_prefix(prompt)
    lowered = prompt.strip().lower()
    if any(token in lowered for token in DEVELOP_AGENT_TOKENS):
        return "develop_agent"
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
