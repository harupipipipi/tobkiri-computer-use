"""Opt-in production MCP check; schemas/skills only, with no desktop input."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from tobkiri_computer_use.runtime import driver_command
from tobkiri_computer_use.transport import McpTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver", help="Trusted configured Cua executable")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    native_command = driver_command(driver=args.driver)
    with McpTransport(native_command) as native:
        original = {tool["name"]: tool for tool in native.list_tools()}

    command = [sys.executable, "-m", "tobkiri_computer_use.reloadable",
               "--surface", "all", "--approval", "deny"]
    if args.driver:
        command.extend(("--driver", args.driver))
    with McpTransport(command) as computer:
        tools = {tool["name"]: tool for tool in computer.list_tools()}
        assert "tobkiri_observe" in tools and "tobkiri_act" in tools
        # Cua itself has original browser_* tools. Preserve those while refusing
        # imported extension aliases or a combined broker surface.
        assert not any(name.startswith("tobkiri_tabs_")
                       or name == "tobkiri_integration_status"
                       or (name.startswith("browser_") and name not in original)
                       for name in tools)
        for name, schema in original.items():
            assert tools[name] == schema, f"Original Cua schema changed: {name}"
        uri = "skill://tobkiri-computer-use/SKILL.md"
        resources = computer.request("resources/list")["resources"]
        assert any(resource["uri"] == uri for resource in resources)
        skill = computer.request("resources/read", {"uri": uri})
        assert "tobkiri" in skill["contents"][0]["text"]
        report = {"passed": True, "computer_tools": len(tools),
                  "original_cua_tools": len(original),
                  "original_schemas_preserved": True, "skill_read": True,
                  "browser_backend": False, "desktop_input": False,
                  "server": computer.server_info}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
