from __future__ import annotations

from .classifiers import SUPPORTED_PROMPT_FAMILIES
from .policy import derive_execution_policy
from ..project_model import IntentBundle


def plan_feature_split(
    prompt: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[str], list[str]]:
    lowered = prompt.strip().lower()
    core_features: list[dict[str, object]] = []
    pluggable_features: list[dict[str, object]] = []
    interface_intents: list[dict[str, object]] = []
    assumptions: list[str] = []
    open_questions: list[str] = []

    if any(token in lowered for token in ("blink", "led", "toggle")):
        core_features.append(
            {
                "id": "core-led-blink",
                "title": "Blink user LED",
                "kind": "core",
                "summary": "Drive the on-board LED through a GPIO output for visible runtime behavior.",
                "interface_intent_ids": ["iface-led-pa5"],
            }
        )
        interface_intents.append(
            {
                "id": "iface-led-pa5",
                "type": "gpio",
                "role": "led_output",
                "pin": "PA5",
                "label": "LD2 [green Led]",
                "signal": "GPIO_Output",
            }
        )
        assumptions.append("PA5 is the default user LED output pin on NUCLEO-L476RG.")

    if "pc" in lowered and any(token in lowered for token in ("send data", "send", "transmit", "printf", "uart", "serial")):
        core_features.append(
            {
                "id": "core-uart-device-to-pc",
                "title": "Send data to PC",
                "kind": "core",
                "summary": "Transmit device data to the host PC over the board's default serial path.",
                "interface_intent_ids": ["iface-uart-host-console"],
            }
        )
        interface_intents.append(
            {
                "id": "iface-uart-host-console",
                "type": "uart",
                "role": "device_to_pc_tx",
                "instance_preference": "USART2",
                "baud_rate": 115200,
                "reason": "Default host serial path for NUCLEO-L476RG prompts that ask for device-to-PC output.",
            }
        )
        assumptions.append("USART2 over the ST-LINK virtual COM path is the default device-to-PC transport for NUCLEO-L476RG.")

    if any(token in lowered for token in ("button", "pushbutton", "blue button", "user button")):
        pluggable_features.append(
            {
                "id": "pluggable-user-button-event",
                "title": "User button event",
                "kind": "pluggable",
                "summary": "Capture the on-board button input so firmware can react to a human-triggered event.",
                "interface_intent_ids": ["iface-button-pc13"],
            }
        )
        interface_intents.append(
            {
                "id": "iface-button-pc13",
                "type": "gpio_exti",
                "role": "user_button",
                "pin": "PC13",
                "label": "B1 [Blue PushButton]",
                "signal": "GPXTI13",
            }
        )
        assumptions.append("PC13 is the default user button input pin on NUCLEO-L476RG.")

    if not core_features and not interface_intents:
        open_questions.append(
            "The initial Phase 2 scaffold only recognizes the first supported device-to-PC serial prompt family."
        )

    if any(token in lowered for token in ("test", "run and test", "verify", "validate")):
        pluggable_features.append(
            {
                "id": "pluggable-runtime-check",
                "title": "Runtime verification",
                "kind": "pluggable",
                "summary": "Run flash-time and post-flash verification after the core serial output feature succeeds.",
                "interface_intent_ids": [],
                "delivery_mode": "policy_only",
            }
        )

    return core_features, pluggable_features, interface_intents, assumptions, open_questions


def build_intent_bundle(prompt: str) -> IntentBundle:
    core_features, pluggable_features, interface_intents, assumptions, open_questions = plan_feature_split(prompt)
    has_supported_delivery = bool(core_features or interface_intents)
    return IntentBundle(
        intent_kind="feature_delivery" if has_supported_delivery else "unsupported_feature_request",
        confidence=0.95 if has_supported_delivery else 0.35,
        core_requirements=core_features,
        optional_requirements=pluggable_features,
        interface_intents=interface_intents,
        runtime_expectations=derive_execution_policy(prompt),
        assumptions=assumptions,
        open_questions=open_questions,
        extra={"supported_prompt_families": list(SUPPORTED_PROMPT_FAMILIES)},
    )
