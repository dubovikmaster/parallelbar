import multiprocessing as mp

import pytest

import tasks
from parallelbar import Parallel


def test_parallel_map():
    with Parallel(n_cpu=2) as par:
        assert par.map(tasks.square, range(10), disable=True) == [x * x for x in range(10)]


def test_parallel_starmap():
    with Parallel(n_cpu=2) as par:
        assert par.starmap(tasks.add, [(1, 2), (3, 4)], disable=True) == [3, 7]


def test_parallel_imap_order_preserved():
    with Parallel(n_cpu=2) as par:
        assert par.imap(tasks.square, range(10), disable=True) == [x * x for x in range(10)]


def test_parallel_imapu_unordered():
    with Parallel(n_cpu=2) as par:
        res = par.imapu(tasks.square, range(10), disable=True)
    assert sorted(res) == sorted(x * x for x in range(10))


def test_parallel_reused_across_calls():
    with Parallel(n_cpu=2) as par:
        a = par.map(tasks.square, range(5), disable=True)
        b = par.map(tasks.identity, range(5), disable=True)
        c = par.starmap(tasks.add, [(1, 1), (2, 2)], disable=True)
    assert a == [x * x for x in range(5)]
    assert b == list(range(5))
    assert c == [2, 4]


def test_parallel_coerce_and_failed_tasks():
    with Parallel(n_cpu=2) as par:
        res, failed = par.map(tasks.boom_on_3, range(6), error_behavior='coerce', return_failed_tasks=True)
    assert sorted(failed) == [3]
    assert isinstance(res[3], ValueError)


def test_parallel_set_error_value():
    with Parallel(n_cpu=2) as par:
        res = par.map(tasks.boom_on_3, range(5), error_behavior='coerce', set_error_value=None, disable=True)
    assert isinstance(res[3], ValueError)


def test_parallel_need_serialize():
    with Parallel(n_cpu=2) as par:
        res = par.map(lambda x: x * 3, range(5), need_serialize=True, disable=True)
    assert res == [x * 3 for x in range(5)]


def test_parallel_process_timeout():
    with Parallel(n_cpu=2) as par:
        res = par.map(tasks.sleep_return, [0.02, 1.5, 0.02], process_timeout=0.4,
                      error_behavior='coerce', disable=True)
    assert isinstance(res[1], Exception)


def test_parallel_timeout_param():
    with pytest.raises(mp.TimeoutError):
        with Parallel(n_cpu=2) as par:
            par.map(tasks.sleep_return, [1.0, 1.0], timeout=0.2, disable=True)


def test_parallel_close_then_use_raises():
    par = Parallel(n_cpu=2)
    par.close()
    with pytest.raises(RuntimeError):
        par.map(tasks.square, range(3), disable=True)


def test_parallel_terminate():
    par = Parallel(n_cpu=2)
    par.map(tasks.square, range(3), disable=True)
    par.terminate()
    with pytest.raises(RuntimeError):
        par.map(tasks.square, range(3), disable=True)


def test_parallel_double_close_is_safe():
    par = Parallel(n_cpu=2)
    par.close()
    par.close()  # must not raise


def test_parallel_terminate_after_close_is_safe():
    par = Parallel(n_cpu=2)
    par.close()
    par.terminate()  # already closed -> early return, must not raise


def test_parallel_manual_lifecycle():
    par = Parallel(n_cpu=2)
    try:
        res = par.map(tasks.square, range(4), disable=True)
    finally:
        par.close()
    assert res == [x * x for x in range(4)]
