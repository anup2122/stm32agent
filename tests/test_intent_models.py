from __future__ import annotations

import unittest

from stm32cubep_mcp.intent import build_intent_bundle
from stm32cubep_mcp.project_model import (
    AgentTask,
    IntentBundle,
    agent_task_from_legacy_contract,
    legacy_requirements_dict_from_intent_bundle,
    validate_agent_task,
    validate_intent_bundle,
)
from stm32cubep_mcp.requirements import server as requirements_server


class IntentModelTests(unittest.TestCase):
    def test_build_intent_bundle_preserves_prompt_analysis_fields(self) -> None:
        bundle = build_intent_bundle(
            "Create a NUCLEO-L476RG project that blinks the LED, sends data to PC, and run and test it"
        )
        legacy = legacy_requirements_dict_from_intent_bundle(bundle)

        self.assertIsInstance(bundle, IntentBundle)
        self.assertEqual(bundle.intent_kind, "feature_delivery")
        self.assertEqual(legacy["core_features"][0]["id"], "core-led-blink")
        self.assertEqual(legacy["core_features"][1]["id"], "core-uart-device-to-pc")
        self.assertEqual(legacy["execution_policy"]["ioc_cubemx_validation"], "required")

    def test_agent_task_adapter_extracts_requested_actions_from_contract(self) -> None:
        contract = requirements_server.build_requirements_contract(
            "Create a NUCLEO-L476RG project that sends data to PC but build only and do not flash"
        )

        task = agent_task_from_legacy_contract(contract)

        self.assertIsInstance(task, AgentTask)
        self.assertEqual(task.task_kind, "feature_delivery")
        self.assertEqual(task.board_id, "NUCLEO-L476RG")
        self.assertEqual(task.requested_actions, ["build"])

    def test_validators_report_missing_required_fields(self) -> None:
        agent_errors = validate_agent_task(AgentTask())
        intent_errors = validate_intent_bundle(IntentBundle(confidence=1.5))

        self.assertIn("task_kind is required.", agent_errors)
        self.assertIn("source_prompt is required.", agent_errors)
        self.assertIn("intent_kind is required.", intent_errors)
        self.assertIn("confidence must be between 0.0 and 1.0 when provided.", intent_errors)


if __name__ == "__main__":
    unittest.main()
