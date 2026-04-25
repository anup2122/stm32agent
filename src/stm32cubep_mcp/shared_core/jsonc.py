from __future__ import annotations

import json


def cloned_json_object(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    return json.loads(json.dumps(payload))


def strip_jsonc_comments(document_text: str) -> str:
    result: list[str] = []
    in_string = False
    string_delimiter = '"'
    in_line_comment = False
    in_block_comment = False
    escaping = False
    index = 0

    while index < len(document_text):
        char = document_text[index]
        next_char = document_text[index + 1] if index + 1 < len(document_text) else ""

        if in_line_comment:
            if char in "\r\n":
                in_line_comment = False
                result.append(char)
            else:
                result.append(" ")
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                result.extend((" ", " "))
                in_block_comment = False
                index += 2
                continue
            result.append(char if char in "\r\n" else " ")
            index += 1
            continue

        if in_string:
            result.append(char)
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == string_delimiter:
                in_string = False
            index += 1
            continue

        if char in {'"', "'"}:
            in_string = True
            string_delimiter = char
            result.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            result.extend((" ", " "))
            in_line_comment = True
            index += 2
            continue

        if char == "/" and next_char == "*":
            result.extend((" ", " "))
            in_block_comment = True
            index += 2
            continue

        result.append(char)
        index += 1

    return "".join(result)


def parse_jsonc_document(document_text: str) -> object:
    return json.loads(strip_jsonc_comments(document_text))
