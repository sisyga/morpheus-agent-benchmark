from __future__ import annotations

import unittest
from unittest.mock import patch

import server


class ServerWrapperTests(unittest.TestCase):
    def test_main_runs_mcp_over_stdio(self) -> None:
        with patch.object(server.mcp, "run") as run:
            server.main()

        run.assert_called_once_with(transport="stdio")


if __name__ == "__main__":
    unittest.main()
