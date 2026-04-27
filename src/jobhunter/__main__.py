import sys

import structlog

from jobhunter import __version__
from jobhunter.config import Settings

logger = structlog.get_logger()


def main() -> None:
    """Main entry point for the application."""
    print(f"Job Hunter EU v{__version__}")

    try:
        settings = Settings()  # type: ignore[call-arg]
        logger.info("Configuration loaded successfully", **settings.safe_dict())
    except Exception as e:
        logger.error("Failed to load configuration", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
