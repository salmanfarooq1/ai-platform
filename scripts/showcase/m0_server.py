"""Owned Gateway-only API for the M0 journey."""

import os


def main() -> None:
    import uvicorn

    from api.main import create_app

    uvicorn.run(
        create_app(),
        fd=int(os.environ["SHOWCASE_API_FD"]), access_log=False, log_level="error",
    )


if __name__ == "__main__":
    main()
