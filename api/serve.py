"""Run the FairLens audit service.

    .venv\\Scripts\\python -m api.serve

Environment overrides: FAIRLENS_SERVICE_HOST, FAIRLENS_SERVICE_PORT.
"""

from __future__ import annotations

import os

import uvicorn

from config_loader import load_config


def main() -> None:
    config = load_config()
    service = config.get("service", {})
    host = os.environ.get("FAIRLENS_SERVICE_HOST", str(service.get("host", "127.0.0.1")))
    port = int(os.environ.get("FAIRLENS_SERVICE_PORT", service.get("port", 8020)))
    uvicorn.run("api.app:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
