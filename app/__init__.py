from __future__ import annotations

from .server import main, mcp, server


def demo_main() -> None:
    from .demo_runner import main as _main

    _main()


__all__ = ["main", "mcp", "server", "demo_main"]
