from __future__ import annotations

from typing import Awaitable, Callable


async def orchestrate_debug_question(
    *,
    prompt: str,
    session_name: str,
    timeout_seconds: int,
    debug_status: Callable[..., dict[str, object]],
    orchestrate_debug_session_fn: Callable[..., Awaitable[dict[str, object]]],
    answer_question: Callable[..., dict[str, object]],
) -> dict[str, object]:
    status_result = debug_status(session_name=session_name)
    launch_result: dict[str, object] | None = None
    if not status_result.get("success"):
        launch_result = await orchestrate_debug_session_fn(
            session_name=session_name,
            reset_before_launch=False,
            timeout_seconds=timeout_seconds,
        )
        if not launch_result.get("success"):
            return {
                "server": "orchestrator",
                "workflow": "debug_question",
                "success": False,
                "prompt": prompt,
                "session_name": session_name,
                "launch_result": launch_result,
                "message": "The debug session could not be prepared for live target inspection.",
            }

    answer_result = answer_question(
        question=prompt,
        session_name=session_name,
        timeout_seconds=timeout_seconds,
    )
    return {
        "server": "orchestrator",
        "workflow": "debug_question",
        "success": bool(answer_result.get("success")),
        "prompt": prompt,
        "session_name": session_name,
        "launch_result": launch_result,
        "answer_result": answer_result,
        "message": str(answer_result.get("answer") or answer_result.get("message") or "Live target inspection finished."),
    }
