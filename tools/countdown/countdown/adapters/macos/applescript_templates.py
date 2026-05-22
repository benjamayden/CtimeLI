"""AppleScript templates for block-end actions — pure string builders.

No PyObjC imports. Targets apps by bundle identifier only — display names
never appear in generated scripts, closing the AppleScript injection vector
documented in docs/edge-cases.md.

Bundle IDs are validated before reaching these functions; callers must filter
IDs through domain.apps.is_valid_bundle_id first. Generated scripts return
an integer count of apps successfully acted on.
"""

from __future__ import annotations

from countdown.domain.apps import is_valid_bundle_id


def hide_script(bundle_ids: list[str]) -> str | None:
    """AppleScript that hides each app in `bundle_ids` and returns a count.

    Returns None if no valid IDs remain after filtering.
    """
    safe = [bid for bid in bundle_ids if is_valid_bundle_id(bid)]
    if not safe:
        return None

    lines = ["set hideCount to 0", 'tell application "System Events"']
    for bid in safe:
        lines += [
            "    try",
            f'        tell (first process whose bundle identifier is "{bid}")',
            "            set visible to false",
            "            set hideCount to hideCount + 1",
            "        end tell",
            "    end try",
        ]
    lines += ["end tell", "return hideCount"]
    return "\n".join(lines)


def minimize_script(bundle_ids: list[str]) -> str | None:
    """AppleScript that minimizes all windows of each app in `bundle_ids`.

    Returns None if no valid IDs remain after filtering.
    """
    safe = [bid for bid in bundle_ids if is_valid_bundle_id(bid)]
    if not safe:
        return None

    lines = ["set minCount to 0", 'tell application "System Events"']
    for bid in safe:
        lines += [
            "    try",
            f'        tell (first process whose bundle identifier is "{bid}")',
            "            set windowCount to count of windows",
            "            repeat with i from windowCount to 1 by -1",
            "                try",
            '                    set value of attribute "AXMinimized" of window i to true',
            "                    set minCount to minCount + 1",
            "                end try",
            "            end repeat",
            "        end tell",
            "    end try",
        ]
    lines += ["end tell", "return minCount"]
    return "\n".join(lines)
