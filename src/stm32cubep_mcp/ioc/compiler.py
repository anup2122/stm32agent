from __future__ import annotations

from ..ioc_builder.ioc_model import build_ioc_model
from ..ioc.db_index import local_cubemx_db_index
from ..knowledge.cubemx_db import cubemx_xml_references_for_ip
from ..requirements_ioc_contract import validate_contract
from .board_catalog import get_board_profile
from .mcu_catalog import resolve_mcu_metadata
from .operation_ir import IocOperation
from .validator import validate_ioc_model

SUPPORTED_INTENT_ROLES: set[tuple[str | None, str | None]] = {
    ("clock", "system_clock"),
    ("clock", "rcc_clockconfig_baseline"),
    ("clock", "runtime_pll_source_switch"),
    ("watchdog", "window_watchdog"),
    ("rtc", "alarm_a"),
    ("timer_pwm", "pwm_output"),
    ("timer_pwm", "complementary_pwm_output"),
    ("dma_binding", "memory_to_timer_compare"),
    ("uart", "device_to_pc_tx"),
    ("uart", "debug_console"),
    ("gpio", "led_output"),
    ("gpio_exti", "user_button"),
    ("power", "low_power_run"),
    ("analog", "opamp_pga_signal_chain"),
    ("lptim", "external_counter_low_power_pwm"),
}


def _unique_preserving_order(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _unsupported_interface_intent_errors(contract: dict[str, object]) -> list[str]:
    errors: list[str] = []
    interface_intents = contract.get("interface_intents")
    if not isinstance(interface_intents, list):
        return errors

    for intent in interface_intents:
        if not isinstance(intent, dict):
            continue
        intent_type = intent.get("type")
        intent_role = intent.get("role")
        if (intent_type, intent_role) in SUPPORTED_INTENT_ROLES:
            continue
        intent_id = intent.get("id") if isinstance(intent.get("id"), str) else f"{intent_type}:{intent_role}"
        errors.append(
            f"Interface intent '{intent_id}' with type '{intent_type}' and role '{intent_role}' is not compiled by the IOC Builder yet."
        )
    return errors


def _xml_references_for_model(model) -> list[dict[str, object]]:
    references: list[dict[str, object]] = []
    try:
        index = local_cubemx_db_index()
    except (FileNotFoundError, OSError):
        return references

    for peripheral in _unique_preserving_order(list(model.required_peripherals)):
        for reference in cubemx_xml_references_for_ip(index, model.grouped_mcu_name, peripheral):
            if reference not in references:
                references.append(reference)
    return references


def compile_model_to_ioc_operations(model, *, source_requirement_ids: list[str]) -> list[IocOperation]:
    operations: list[IocOperation] = [
        IocOperation(
            op_id="set-mcu-name",
            kind="set_property",
            target={"key": "Mcu.Name"},
            value=model.target_mcu,
            reason="Align the managed IOC with the requested target MCU.",
            source_requirement_ids=source_requirement_ids,
        ),
        IocOperation(
            op_id="set-toolchain",
            kind="set_property",
            target={"key": "ProjectManager.ToolChain"},
            value=model.toolchain,
            reason="Keep the IOC toolchain aligned with the project defaults.",
            source_requirement_ids=source_requirement_ids,
        ),
        IocOperation(
            op_id="set-target-toolchain",
            kind="set_property",
            target={"key": "ProjectManager.TargetToolchain"},
            value=model.toolchain,
            reason="Keep the target toolchain aligned with the project defaults.",
            source_requirement_ids=source_requirement_ids,
        ),
        IocOperation(
            op_id="set-main-location",
            kind="set_property",
            target={"key": "ProjectManager.MainLocation"},
            value="Src",
            reason="Preserve the expected CubeMX main source layout.",
            source_requirement_ids=source_requirement_ids,
        ),
        IocOperation(
            op_id="set-project-structure",
            kind="set_property",
            target={"key": "ProjectManager.ProjectStructure"},
            value="",
            reason="Preserve the existing project structure layout for generated code.",
            source_requirement_ids=source_requirement_ids,
        ),
        IocOperation(
            op_id="set-under-root",
            kind="set_property",
            target={"key": "ProjectManager.UnderRoot"},
            value="false",
            reason="Preserve board baseline layout without forcing nested project-manager roots.",
            source_requirement_ids=source_requirement_ids,
        ),
    ]

    for peripheral in _unique_preserving_order(list(model.required_peripherals)):
        operations.append(
            IocOperation(
                op_id=f"ensure-peripheral-{peripheral.lower()}",
                kind="ensure_peripheral_enabled",
                target={"peripheral": peripheral},
                value=peripheral,
                reason=f"Enable the {peripheral} peripheral needed by the compiled intent.",
                source_requirement_ids=source_requirement_ids,
            )
        )

    for pin_name in _unique_preserving_order(list(model.used_pins)):
        operations.append(
            IocOperation(
                op_id=f"ensure-pin-{pin_name.lower().replace('-', '_').replace('(', '').replace(')', '').replace(' ', '_')}",
                kind="ensure_pin_used",
                target={"pin": pin_name},
                value=pin_name,
                reason=f"Reserve pin {pin_name} for the compiled IOC intent.",
                source_requirement_ids=source_requirement_ids,
            )
        )

    property_index = 0
    for binding in model.bindings:
        labels = binding.get("labels", {})
        signals = binding.get("signals", {})
        modes = binding.get("modes", {})
        if isinstance(signals, dict):
            for pin_name, signal in signals.items():
                if pin_name in labels:
                    operations.append(
                        IocOperation(
                            op_id=f"set-gpio-parameters-{property_index}",
                            kind="set_property",
                            target={"key": f"{pin_name}.GPIOParameters"},
                            value="GPIO_Label",
                            reason=f"Enable label metadata for pin {pin_name}.",
                            source_requirement_ids=source_requirement_ids,
                        )
                    )
                    property_index += 1
                    operations.append(
                        IocOperation(
                            op_id=f"set-gpio-label-{property_index}",
                            kind="set_property",
                            target={"key": f"{pin_name}.GPIO_Label"},
                            value=labels[pin_name],
                            reason=f"Apply the generated label for pin {pin_name}.",
                            source_requirement_ids=source_requirement_ids,
                        )
                    )
                    property_index += 1
                operations.append(
                    IocOperation(
                        op_id=f"set-signal-{property_index}",
                        kind="set_property",
                        target={"key": f"{pin_name}.Signal"},
                        value=signal,
                        reason=f"Assign signal {signal} to pin {pin_name}.",
                        source_requirement_ids=source_requirement_ids,
                    )
                )
                property_index += 1
                if pin_name in modes:
                    operations.append(
                        IocOperation(
                            op_id=f"set-mode-{property_index}",
                            kind="set_property",
                            target={"key": f"{pin_name}.Mode"},
                            value=modes[pin_name],
                            reason=f"Set the CubeMX mode for pin {pin_name}.",
                            source_requirement_ids=source_requirement_ids,
                        )
                    )
                    property_index += 1

        instance = binding.get("instance")
        peripheral_properties = binding.get("peripheral_properties", {})
        if isinstance(instance, str) and isinstance(peripheral_properties, dict):
            for property_name, property_value in peripheral_properties.items():
                operations.append(
                    IocOperation(
                        op_id=f"set-peripheral-property-{property_index}",
                        kind="set_property",
                        target={"key": f"{instance}.{property_name}"},
                        value=property_value,
                        reason=f"Set {instance}.{property_name} to the compiled value.",
                        source_requirement_ids=source_requirement_ids,
                    )
                )
                property_index += 1

        shared_properties = binding.get("shared_properties", {})
        if isinstance(shared_properties, dict):
            for property_name, property_value in shared_properties.items():
                operations.append(
                    IocOperation(
                        op_id=f"set-shared-property-{property_index}",
                        kind="set_property",
                        target={"key": property_name},
                        value=property_value,
                        reason=f"Set shared IOC property {property_name}.",
                        source_requirement_ids=source_requirement_ids,
                    )
                )
                property_index += 1

    return operations


def compile_contract_to_ioc_plan(contract: dict[str, object]) -> dict[str, object]:
    validation_errors = validate_contract(contract)
    if validation_errors:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": "The requirements-to-IOC contract is invalid.",
            "validation_errors": validation_errors,
        }

    unsupported_intent_errors = _unsupported_interface_intent_errors(contract)
    if unsupported_intent_errors:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": "The requirements contract contains feature intents that the IOC Builder cannot compile yet.",
            "validation_errors": unsupported_intent_errors,
        }

    target = contract["target"]
    board_id = str(target["board_id"])
    board_profile = get_board_profile(board_id)
    if board_profile is None:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": f"Board profile '{board_id}' is not supported by the IOC Synthesis Agent yet.",
            "validation_errors": [],
        }

    mcu_metadata = resolve_mcu_metadata(board_id, str(target["mcu"]))
    if mcu_metadata is None:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": f"MCU metadata for board '{board_id}' is not supported by the IOC Builder yet.",
            "validation_errors": [],
        }

    model = build_ioc_model(contract, board_profile, mcu_metadata)
    model_errors = validate_ioc_model(model, mcu_metadata)
    if model_errors:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": "The canonical IOC model is invalid for the selected board and MCU metadata.",
            "validation_errors": model_errors,
        }

    current_increment = contract.get("current_increment") if isinstance(contract.get("current_increment"), dict) else {}
    source_requirement_ids = [
        feature_id
        for feature_id in current_increment.get("feature_ids", [])
        if isinstance(feature_id, str) and feature_id.strip()
    ]
    operations = compile_model_to_ioc_operations(model, source_requirement_ids=source_requirement_ids)
    xml_references = _xml_references_for_model(model)
    enabled_peripherals = [
        str(operation.value)
        for operation in operations
        if operation.kind == "ensure_peripheral_enabled" and isinstance(operation.value, str)
    ]
    used_pins = [
        str(operation.value)
        for operation in operations
        if operation.kind == "ensure_pin_used" and isinstance(operation.value, str)
    ]
    ioc_properties = [
        {"key": str(operation.target.get("key")), "value": operation.value}
        for operation in operations
        if operation.kind == "set_property" and isinstance(operation.target.get("key"), str)
    ]

    return {
        "server": "ioc_builder",
        "success": True,
        "builder_strategy": "seed_plus_mutate",
        "operation_strategy": "operation_ir_plus_mutate",
        "board_profile": board_id,
        "seed_selection": {
            "board_id": board_id,
            "source": "embedded_official_board_seed",
        },
        "mcu_metadata": {
            "requested_mcu": mcu_metadata.get("requested_mcu"),
            "grouped_mcu_name": mcu_metadata.get("grouped_mcu_name"),
            "grouped_xml_filename": mcu_metadata.get("grouped_xml_filename"),
        },
        "ioc_model": model.to_summary(),
        "current_increment": contract["current_increment"],
        "operations": [operation.to_dict() for operation in operations],
        "enabled_peripherals": enabled_peripherals,
        "used_pins": used_pins,
        "ioc_properties": ioc_properties,
        "cubemx_xml_references": xml_references,
        "codegen_hints": list(model.codegen_hints),
        "message": "The IOC operation plan was compiled deterministically from the requirements contract.",
    }
