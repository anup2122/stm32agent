from __future__ import annotations


def validate_string_list(value: object, field_name: str, errors: list[str]) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{field_name} must be an array of non-empty strings.")


def validate_tools_local_schema(payload: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Document must be a JSON object."]

    version = payload.get("version")
    if not isinstance(version, int):
        errors.append("version must be an integer.")

    tools = payload.get("tools")
    if not isinstance(tools, dict):
        errors.append("tools must be an object.")
        return errors

    supported_tools = ("cube_programmer", "cubeide", "cubemx", "stlink_gdb_server", "arm_gdb")
    for tool_name in supported_tools:
        tool_entry = tools.get(tool_name)
        if tool_entry is None:
            continue
        if not isinstance(tool_entry, dict):
            errors.append(f"tools.{tool_name} must be an object when provided.")
            continue

        env_var = tool_entry.get("env_var")
        if env_var is not None and not isinstance(env_var, str):
            errors.append(f"tools.{tool_name}.env_var must be a string when provided.")

        executable_name = tool_entry.get("executable_name")
        if executable_name is not None and not isinstance(executable_name, str):
            errors.append(f"tools.{tool_name}.executable_name must be a string when provided.")

        candidates = tool_entry.get("candidates")
        if candidates is not None and not isinstance(candidates, dict):
            errors.append(f"tools.{tool_name}.candidates must be an object when provided.")
        elif isinstance(candidates, dict):
            for platform_name, platform_candidates in candidates.items():
                validate_string_list(platform_candidates, f"tools.{tool_name}.candidates.{platform_name}", errors)

    return errors


def validate_project_metadata_schema(payload: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Document must be a JSON object."]

    version = payload.get("version")
    if not isinstance(version, int):
        errors.append("version must be an integer.")

    project_name = payload.get("project_name")
    if project_name is not None and not isinstance(project_name, str):
        errors.append("project_name must be a string when provided.")

    for field_name in ("_comment", "generated_root", "project_toolchain", "build_system", "default_configuration"):
        value = payload.get(field_name)
        if value is not None and not isinstance(value, str):
            errors.append(f"{field_name} must be a string when provided.")

    board = payload.get("board")
    if board is not None and not isinstance(board, dict):
        errors.append("board must be an object when provided.")
    elif isinstance(board, dict):
        comment = board.get("_comment")
        if comment is not None and not isinstance(comment, str):
            errors.append("board._comment must be a string when provided.")
        for field_name in ("name", "mcu", "interface"):
            if field_name in board and not isinstance(board[field_name], str):
                errors.append(f"board.{field_name} must be a string when provided.")

    for section_name in ("firmware", "build", "debug"):
        section = payload.get(section_name)
        if section is not None and not isinstance(section, dict):
            errors.append(f"{section_name} must be an object when provided.")
        elif isinstance(section, dict):
            comment = section.get("_comment")
            if comment is not None and not isinstance(comment, str):
                errors.append(f"{section_name}._comment must be a string when provided.")

    cubemx = payload.get("cubemx")
    if cubemx is not None and not isinstance(cubemx, dict):
        errors.append("cubemx must be an object when provided.")
    elif isinstance(cubemx, dict):
        comment = cubemx.get("_comment")
        if comment is not None and not isinstance(comment, str):
            errors.append("cubemx._comment must be a string when provided.")

    connect_defaults = board.get("connect_defaults") if isinstance(board, dict) else None
    if connect_defaults is not None and not isinstance(connect_defaults, dict):
        errors.append("board.connect_defaults must be an object when provided.")

    return errors
