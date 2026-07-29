"""Ensure the repository root is importable when pytest is invoked directly."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
