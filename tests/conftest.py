import os
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# repo root so `import parallelbar` works, and this dir so `import tasks` works
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

import pytest

import tasks


@pytest.fixture
def clean_retry_dir():
    shutil.rmtree(tasks.RETRY_DIR, ignore_errors=True)
    os.makedirs(tasks.RETRY_DIR, exist_ok=True)
    yield tasks.RETRY_DIR
    shutil.rmtree(tasks.RETRY_DIR, ignore_errors=True)
