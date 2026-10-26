"""Process entry point for the sandbox API.

Keeping the ASGI target in the sandbox package means the black-box components
never need to know the scoring module's import path. The auditor launches this
script as a separate process and talks to it only over HTTP.
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the FairLens sandbox API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--log-level", default="warning")
    args = parser.parse_args()
    uvicorn.run(
        "sandbox.api:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
