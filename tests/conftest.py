# conftest.py — CER harness pytest integration
# Adds project root + pipecat stubs to path so ported tests can import tools/db/persona/processors.

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PIPECAT_STUBS = os.path.join(_PROJECT_ROOT, "pipecat_stubs")

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _PIPECAT_STUBS not in sys.path:
    sys.path.insert(0, _PIPECAT_STUBS)
