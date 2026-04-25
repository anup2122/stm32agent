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
    summary = {
        "success": result.get("success"),
        "stage": result.get("stage"),
        "message": result.get("message"),
        "workflow": result.get("workflow"),
        "execution_policy_summary": result.get("execution_policy_summary"),
        "ioc_validation_summary": result.get("ioc_validation_summary"),
        "artifact_source": result.get("artifact_source"),
        "artifact_path": result.get("artifact_path"),
        "flash_skipped": result.get("flash_skipped"),
        "cubemx_success": ((result.get("cubemx_result") or {}).get("success") if isinstance(result.get("cubemx_result"), dict) else None),
        "cubemx_message": ((result.get("cubemx_result") or {}).get("message") if isinstance(result.get("cubemx_result"), dict) else None),
        "build_message": ((result.get("build_result") or {}).get("message") if isinstance(result.get("build_result"), dict) else None),
        "build_success": ((result.get("build_result") or {}).get("success") if isinstance(result.get("build_result"), dict) else None),
        "build_project_path": ((result.get("build_result") or {}).get("project_path") if isinstance(result.get("build_result"), dict) else None),
        "log_file": ((result.get("build_result") or {}).get("log_file") if isinstance(result.get("build_result"), dict) else None),
        "flash_success": ((result.get("flash_result") or {}).get("success") if isinstance(result.get("flash_result"), dict) else None),
        "flash_message": ((result.get("flash_result") or {}).get("message") if isinstance(result.get("flash_result"), dict) else None),
        "runtime_validation_success": ((result.get("runtime_validation_result") or {}).get("success") if isinstance(result.get("runtime_validation_result"), dict) else None),
        "runtime_validation_message": ((result.get("runtime_validation_result") or {}).get("message") if isinstance(result.get("runtime_validation_result"), dict) else None),
        "plan_path": ((result.get("plan_artifact") or {}).get("plan_path") if isinstance(result.get("plan_artifact"), dict) else None),
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()