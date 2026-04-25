import asyncio
import json

from stm32cubep_mcp.orchestrator import server as orchestrator_server


def main() -> None:
    prompt = "I have attached STM32L476Rg Nucleo device. write a project that will send data from the device to pc and run and test it"
    result = asyncio.run(
        orchestrator_server.stm32_orchestrate_feature_prompt(
            prompt=prompt,
            build_timeout_seconds=900,
            flash_timeout_seconds=300,
            cubemx_timeout_seconds=1200,
        )
    )
    cubemx_result = result.get("cubemx_result") or {}
    detail = {
        "stage": result.get("stage"),
        "message": result.get("message"),
        "cubemx_success": cubemx_result.get("success"),
        "cubemx_result_message": cubemx_result.get("message"),
        "cubemx_workflow": cubemx_result.get("workflow"),
        "cubemx_request": cubemx_result.get("cubemx_request"),
        "cubemx_inner_success": ((cubemx_result.get("result") or {}).get("success") if isinstance(cubemx_result.get("result"), dict) else None),
        "cubemx_inner_failure_reason": ((cubemx_result.get("result") or {}).get("regeneration_result", {}).get("failure_reason") if isinstance((cubemx_result.get("result") or {}).get("regeneration_result"), dict) else None),
        "cubemx_completion_wait": ((cubemx_result.get("result") or {}).get("completion_wait") if isinstance(cubemx_result.get("result"), dict) else None),
        "cubemx_log_file": ((cubemx_result.get("result") or {}).get("log_file") if isinstance(cubemx_result.get("result"), dict) else None),
    }
    print(json.dumps(detail, indent=2, default=str))


if __name__ == "__main__":
    main()