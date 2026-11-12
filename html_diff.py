"""Textual diff of old and new cleaned HTML. No job-specific selectors."""
import difflib


def stable_lines(html):
    return [
        line.rstrip()
        for line in html.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip()
    ]


def create_html_diff(old_html, new_html, context_lines=3):
    """Return additions and removals together. AI interprets their meaning."""
    old_lines = stable_lines(old_html)
    new_lines = stable_lines(new_html)

    if old_lines == new_lines:
        return {
            "changed": False,
            "first_run": False,
            "added_content": "",
            "removed_content": "",
            "diff_text": "",
            "added_lines": 0,
            "removed_lines": 0,
        }

    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    added, removed = [], []

    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in {"delete", "replace"}:
            removed.extend(old_lines[old_start:old_end])
        if tag in {"insert", "replace"}:
            added.extend(new_lines[new_start:new_end])

    unified = difflib.unified_diff(
        old_lines, new_lines,
        fromfile="OLD_HTML", tofile="NEW_HTML",
        lineterm="", n=context_lines,
    )
    return {
        "changed": True,
        "first_run": False,
        "added_content": "\n".join(added),
        "removed_content": "\n".join(removed),
        "diff_text": "\n".join(unified),
        "added_lines": len(added),
        "removed_lines": len(removed),
    }
