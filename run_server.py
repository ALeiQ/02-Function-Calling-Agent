#!/usr/bin/env python3
"""Start the Function-Calling Agent web server.

TODO(milestone 4): activate once the API is implemented.
"""

import uvicorn

from src.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "src.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )