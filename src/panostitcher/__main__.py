"""Allow ``python -m panostitcher``."""

import sys

from .cli import main

sys.exit(main())
