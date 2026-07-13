import time

import pytest

import tasks
from parallelbar import progress_map
from parallelbar.wrappers import stopit_after_timeout, add_progress, _make_args


# --------------------------- add_progress ---------------------------

def test_add_progress_separate_bar_coerce():
    # outer_pipeline calls inner_coerce 5 times per task; inner_coerce(4) -> ValueError (coerced)
    res = progress_map(tasks.outer_pipeline, [5, 5, 5, 5], n_cpu=2, total=20,
                       used_add_progress_decorator=True, disable=True)
    for sublist in res:
        assert sublist[0] == 0
        assert sublist[1] == 2
        assert isinstance(sublist[4], ValueError)


def test_add_progress_separate_bar_with_display():
    # disable=False exercises the status thread's sub-bar creation/finalization path
    res = progress_map(tasks.outer_pipeline, [5, 5, 5], n_cpu=2, total=15,
                       used_add_progress_decorator=True, disable=False)
    assert len(res) == 3
    assert all(isinstance(sub[4], ValueError) for sub in res)


def test_add_progress_aggregate_success():
    res = progress_map(tasks.outer_timeout, [4, 4], n_cpu=2, total=8,
                       used_add_progress_decorator=True, disable=True)
    assert res == [[0, 10, 20, 30], [0, 10, 20, 30]]


def test_add_progress_aggregate_raise_propagates():
    # With used_add_progress_decorator=True the map does not wrap func, so a decorator
    # configured with error_handling='raise' lets the exception propagate out of progress_map.
    with pytest.raises(ValueError):
        progress_map(tasks.outer_agg_raise, [5, 5], n_cpu=2, total=10,
                     used_add_progress_decorator=True, disable=True)


def test_add_progress_aggregate_coerce_returns_exception():
    res = progress_map(tasks.outer_agg_coerce, [5], n_cpu=1, total=5,
                       used_add_progress_decorator=True, disable=True)
    sublist = res[0]
    assert sublist[:3] == [0, 1, 2]
    assert isinstance(sublist[3], ValueError)


def test_add_progress_aggregate_set_error_value():
    res = progress_map(tasks.outer_agg_setval, [5], n_cpu=1, total=5,
                       used_add_progress_decorator=True, disable=True)
    assert res[0] == [0, 1, 2, -1, 4]


def test_add_progress_default_kwargs():
    @add_progress()
    def f(x):
        return x
    assert callable(f)


# --------------------------- _make_args ---------------------------

def test_make_args_single():
    assert _make_args(5) == 5


def test_make_args_multiple():
    assert _make_args(1, 2, 3) == (1, 2, 3)


def test_make_args_with_kwargs():
    assert _make_args(1, 2, a=3) == (1, 2, {'a': 3})


# --------------------------- stopit_after_timeout ---------------------------

def test_stopit_returns_result_when_fast():
    @stopit_after_timeout(0.5, raise_exception=True)
    def fast(t):
        time.sleep(t)
        return 'done'
    assert fast(0.01) == 'done'


def test_stopit_raises_on_timeout():
    @stopit_after_timeout(0.2, raise_exception=True)
    def slow(t):
        time.sleep(t)
        return 'done'
    with pytest.raises(TimeoutError):
        slow(1.0)


def test_stopit_returns_message_when_not_raising():
    @stopit_after_timeout(0.2, raise_exception=False)
    def slow(t):
        time.sleep(t)
        return 'done'
    result = slow(1.0)
    assert isinstance(result, str)
    assert '0.2' in result
