import io
import json
import sys
import unittest
from unittest.mock import patch

import morpheus_tools_cli as cli


class MorpheusToolsCliTests(unittest.TestCase):
    def test_invalid_command_returns_usage_json(self) -> None:
        with patch.object(sys, "argv", ["morpheus_tools_cli.py", "missing"]), patch("sys.stdout", new=io.StringIO()) as out:
            status = cli.main()

        payload = json.loads(out.getvalue())
        self.assertEqual(status, 1)
        self.assertFalse(payload["ok"])
        self.assertIn("Available:", payload["error"])

    def test_valid_command_receives_json_kwargs(self) -> None:
        calls = []

        def command(**kwargs):
            calls.append(kwargs)
            return {"ok": True, "value": kwargs["value"]}

        with (
            patch.object(sys, "argv", ["morpheus_tools_cli.py", "fake"]),
            patch.object(cli, "COMMANDS", {"fake": command}),
            patch("sys.stdin", new=io.StringIO('{"value": 3}')),
            patch("sys.stdout", new=io.StringIO()) as out,
        ):
            status = cli.main()

        self.assertEqual(status, 0)
        self.assertEqual(calls, [{"value": 3}])
        self.assertEqual(json.loads(out.getvalue()), {"ok": True, "value": 3})

    def test_command_exception_returns_failed_json(self) -> None:
        def command() -> dict:
            raise RuntimeError("boom")

        with (
            patch.object(sys, "argv", ["morpheus_tools_cli.py", "fake"]),
            patch.object(cli, "COMMANDS", {"fake": command}),
            patch("sys.stdin", new=io.StringIO("")),
            patch("sys.stdout", new=io.StringIO()) as out,
        ):
            status = cli.main()

        self.assertEqual(status, 1)
        self.assertEqual(json.loads(out.getvalue()), {"ok": False, "error": "boom"})

    def test_success_without_ok_field_exits_zero(self) -> None:
        with (
            patch.object(sys, "argv", ["morpheus_tools_cli.py", "fake"]),
            patch.object(cli, "COMMANDS", {"fake": lambda: {"value": 1}}),
            patch("sys.stdin", new=io.StringIO("")),
            patch("sys.stdout", new=io.StringIO()) as out,
        ):
            status = cli.main()

        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out.getvalue()), {"value": 1})


if __name__ == "__main__":
    unittest.main()
