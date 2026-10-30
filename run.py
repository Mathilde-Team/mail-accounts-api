# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Exclusion de couverture justifiée (SOCLE §4) : garde de script, le
# lancement réel démarre uvicorn et ne revient pas.
if __name__ == "__main__":  # pragma: no cover
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    uvicorn.run(
        "api:create_app",
        factory=True,
        host=os.environ.get("MAIL_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("MAIL_API_PORT", "9941")),
        access_log=False,
        proxy_headers=False,
    )
