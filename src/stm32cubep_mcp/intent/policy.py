from __future__ import annotations

STRICT_VALIDATION_TOKENS = ("run and test", "test it", "verify", "validate", "production")
SKIP_FLASH_TOKENS = ("build only", "compile only", "do not flash", "skip flash", "generate only")


def should_require_cubemx_validation(prompt: str) -> bool:
    lowered = prompt.strip().lower()
    return any(token in lowered for token in STRICT_VALIDATION_TOKENS)


def should_skip_flash(prompt: str) -> bool:
    lowered = prompt.strip().lower()
    return any(token in lowered for token in SKIP_FLASH_TOKENS)


def derive_execution_policy(prompt: str) -> dict[str, object]:
    policy: dict[str, object] = {}
    if should_require_cubemx_validation(prompt):
        policy["ioc_cubemx_validation"] = "required"
    if should_skip_flash(prompt):
        policy["flash_after_successful_build"] = False
        policy["runtime_check_after_flash"] = False
    return policy
