"""Picklable, module-level task functions shared by the test suite.

They must live at module top level so they can be pickled for the ``spawn`` start
method used on macOS/Windows.
"""
import os
import tempfile
import time

from parallelbar.wrappers import add_progress

RETRY_DIR = os.path.join(tempfile.gettempdir(), 'parallelbar_pytest_retry')


def square(x):
    return x * x


def add(a, b):
    return a + b


def add3(a, b, c):
    return a + b + c


def identity(x):
    return x


def boom_on_3(x):
    if x == 3:
        raise ValueError('boom on 3')
    return x


def boom_on_multiples_of_10(x):
    if x % 10 == 0:
        raise ValueError(f'bad value {x}')
    return x


def always_fail_2_5(x):
    if x in (2, 5):
        raise ValueError(f'always fail {x}')
    return x


def sleep_return(t):
    time.sleep(t)
    return t


_INIT_VALUE = 0


def worker_init(value):
    global _INIT_VALUE
    _INIT_VALUE = value


def read_init(x):
    return _INIT_VALUE + x


def flaky(x):
    """Fails the first time it sees x in {2, 5, 8}, succeeds on retry (file marker)."""
    if x in (2, 5, 8):
        marker = os.path.join(RETRY_DIR, str(x))
        if not os.path.exists(marker):
            open(marker, 'w').close()
            raise ValueError(f'transient error on {x}')
    return x


# --- add_progress decorated functions (used with used_add_progress_decorator=True) ---
@add_progress(error_handling='coerce', separate_bar=True, total=20, desc='inner')
def inner_coerce(n):
    if n == 4:
        raise ValueError('inner boom')
    return n * 2


def outer_pipeline(x):
    return [inner_coerce(i) for i in range(x)]


@add_progress()  # aggregate bar, error_handling='raise'
def inner_agg_raise(n):
    if n == 3:
        raise ValueError('agg raise')
    return n


def outer_agg_raise(x):
    return [inner_agg_raise(i) for i in range(x)]


@add_progress(error_handling='coerce')  # aggregate bar, returns exception on error
def inner_agg_coerce(n):
    if n == 3:
        raise ValueError('agg coerce')
    return n


def outer_agg_coerce(x):
    return [inner_agg_coerce(i) for i in range(x)]


@add_progress(error_handling='coerce', set_error_value=-1)
def inner_agg_setval(n):
    if n == 3:
        raise ValueError('agg setval')
    return n


def outer_agg_setval(x):
    return [inner_agg_setval(i) for i in range(x)]


@add_progress(timeout=1.0)
def inner_timeout(n):
    return n * 10


def outer_timeout(x):
    return [inner_timeout(i) for i in range(x)]
