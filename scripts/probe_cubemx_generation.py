import json

from stm32cubep_mcp.cubemx import server as cubemx_server


def main() -> None:
    result = cubemx_server.stm32_cubemx_regenerate_project(
        ioc_path=r"C:\agent_dev_v1\mcp-server-stm32cubep\NUCLEO-L476RG-UART2-printf\NUCLEO-L476RG-UART2-printf.ioc",
        project_name="NUCLEO-L476RG-UART2-printf",
        project_toolchain="STM32CubeIDE",
        project_path=r"C:\agent_dev_v1\mcp-server-stm32cubep\generated\cubemx-probe",
        output_root=r"C:\agent_dev_v1\mcp-server-stm32cubep\generated\cubemx-probe",
        script_path=r"C:\agent_dev_v1\mcp-server-stm32cubep\generated\cubemx-probe\script.txt",
        validate_build=False,
        timeout_seconds=900,
        build_timeout_seconds=900,
    )
    summary = {
        "success": result.get("success"),
        "message": result.get("message"),
        "output_root": result.get("output_root"),
        "project_path": result.get("project_path"),
        "completion_wait": result.get("completion_wait"),
        "affected_files": result.get("affected_files"),
        "log_file": result.get("log_file"),
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()