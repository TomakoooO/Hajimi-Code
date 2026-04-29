from difflib import ndiff


def build_diff_lines(before: str, after: str) -> list[dict]:
    result: list[dict] = []
    before_line = 0
    after_line = 0

    for line in ndiff(before.splitlines(), after.splitlines()):
        prefix = line[:2]
        text = line[2:]
        if prefix == "- ":
            before_line += 1
            result.append({"type": "del", "line_before": before_line, "line_after": None, "text": text})
        elif prefix == "+ ":
            after_line += 1
            result.append({"type": "add", "line_before": None, "line_after": after_line, "text": text})
        elif prefix == "  ":
            before_line += 1
            after_line += 1
            result.append(
                {"type": "ctx", "line_before": before_line, "line_after": after_line, "text": text}
            )
        # skip '? ' helper lines from difflib
    return result
