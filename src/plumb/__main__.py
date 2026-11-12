"""``python -m plumb`` — the same command surface as the ``plumb`` script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
