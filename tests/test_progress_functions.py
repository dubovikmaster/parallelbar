import multiprocessing as mp

import pytest

import tasks
from parallelbar import progress_map, progress_starmap, progress_imap, progress_imapu


# --------------------------- progress_map ---------------------------

def test_map_basic():
    assert progress_map(tasks.square, range(10), n_cpu=2, disable=True) == [x * x for x in range(10)]


def test_map_empty():
    assert progress_map(tasks.square, [], n_cpu=2, disable=True) == []


def test_map_with_bar_enabled():
    assert progress_map(tasks.square, range(5), n_cpu=2, disable=False) == [x * x for x in range(5)]


def test_map_coerce_with_bar_enabled():
    # disable=False exercises the status thread including the error bar
    res = progress_map(tasks.boom_on_multiples_of_10, range(30), n_cpu=2,
                       error_behavior='coerce', disable=False)
    assert isinstance(res[0], ValueError)
    assert isinstance(res[10], ValueError)
    assert res[1] == 1


def test_map_n_cpu_one():
    assert progress_map(tasks.square, range(6), n_cpu=1, disable=True) == [x * x for x in range(6)]


def test_map_chunk_size():
    assert progress_map(tasks.square, range(20), n_cpu=2, chunk_size=5, disable=True) == [x * x for x in range(20)]


def test_map_total_explicit():
    assert progress_map(tasks.square, range(8), n_cpu=2, total=8, disable=True) == [x * x for x in range(8)]


def test_map_iterator_with_total():
    gen = (x for x in range(8))
    assert progress_map(tasks.identity, gen, n_cpu=2, total=8, disable=True) == list(range(8))


def test_map_threads_executor():
    assert progress_map(tasks.square, range(10), n_cpu=2, executor='threads', disable=True) == \
        [x * x for x in range(10)]


@pytest.mark.parametrize('context', ['spawn', 'fork', 'forkserver'])
def test_map_context(context):
    if context not in mp.get_all_start_methods():
        pytest.skip(f'{context} not available on this platform')
    assert progress_map(tasks.square, range(6), n_cpu=2, context=context, disable=True) == \
        [x * x for x in range(6)]


def test_map_maxtasksperchild():
    assert progress_map(tasks.square, range(30), n_cpu=2, maxtasksperchild=3, disable=True) == \
        [x * x for x in range(30)]


def test_map_coerce_returns_exceptions():
    res = progress_map(tasks.boom_on_3, range(5), n_cpu=2, error_behavior='coerce', disable=True)
    assert res[:3] == [0, 1, 2]
    assert isinstance(res[3], ValueError)
    assert res[4] == 4


def test_map_coerce_set_error_value():
    res = progress_map(tasks.boom_on_3, range(5), n_cpu=2, error_behavior='coerce',
                       set_error_value=-1, disable=True)
    assert res == [0, 1, 2, -1, 4]


def test_map_raise_propagates():
    with pytest.raises(ValueError):
        progress_map(tasks.boom_on_3, range(5), n_cpu=2, error_behavior='raise', disable=True)


def test_map_raise_propagates_with_bar_enabled():
    with pytest.raises(ValueError):
        progress_map(tasks.boom_on_3, range(5), n_cpu=2, error_behavior='raise', disable=False)


def test_map_initializer_and_initargs():
    res = progress_map(tasks.read_init, range(5), n_cpu=2,
                       initializer=tasks.worker_init, initargs=(100,), disable=True)
    assert res == [100 + x for x in range(5)]


def test_map_return_failed_tasks():
    res, failed = progress_map(tasks.boom_on_3, range(6), n_cpu=2, error_behavior='coerce',
                               return_failed_tasks=True)
    assert sorted(failed) == [3]
    assert isinstance(res[3], ValueError)


def test_map_timeout_param_raises():
    with pytest.raises(mp.TimeoutError):
        progress_map(tasks.sleep_return, [1.0, 1.0, 1.0, 1.0], n_cpu=2, timeout=0.2, disable=True)


def test_map_process_timeout_soft():
    res = progress_map(tasks.sleep_return, [0.02, 0.02, 1.5, 0.02], n_cpu=2,
                       process_timeout=0.4, error_behavior='coerce', disable=True)
    assert res[0] == 0.02
    assert isinstance(res[2], Exception)


def test_map_need_serialize_lambda():
    res = progress_map(lambda x: x + 100, range(5), n_cpu=2, need_serialize=True, disable=True)
    assert res == [x + 100 for x in range(5)]


# --------------------------- progress_starmap ---------------------------

def test_starmap_basic():
    assert progress_starmap(tasks.add, [(1, 2), (3, 4), (5, 6)], n_cpu=2, disable=True) == [3, 7, 11]


def test_starmap_three_args():
    assert progress_starmap(tasks.add3, [(1, 2, 3), (4, 5, 6)], n_cpu=2, disable=True) == [6, 15]


def test_starmap_coerce():
    res = progress_starmap(tasks.add, [(1, 2), ('a', 3)], n_cpu=2, error_behavior='coerce', disable=True)
    assert res[0] == 3
    assert isinstance(res[1], TypeError)


# --------------------------- progress_imap ---------------------------

def test_imap_basic_order_preserved():
    assert progress_imap(tasks.square, range(15), n_cpu=2, disable=True) == [x * x for x in range(15)]


def test_imap_coerce():
    res = progress_imap(tasks.boom_on_3, range(5), n_cpu=2, error_behavior='coerce', disable=True)
    assert isinstance(res[3], ValueError)


def test_imap_return_failed_tasks():
    res, failed = progress_imap(tasks.boom_on_3, range(6), n_cpu=2, error_behavior='coerce',
                                return_failed_tasks=True)
    assert sorted(failed) == [3]


# --------------------------- progress_imapu ---------------------------

def test_imapu_basic_unordered():
    res = progress_imapu(tasks.square, range(15), n_cpu=2, disable=True)
    assert sorted(res) == sorted(x * x for x in range(15))


def test_imapu_coerce():
    res = progress_imapu(tasks.boom_on_3, range(5), n_cpu=2, error_behavior='coerce', disable=True)
    assert any(isinstance(r, ValueError) for r in res)


# --------------------------- validation ---------------------------

def test_invalid_error_behavior():
    with pytest.raises(ValueError):
        progress_map(tasks.square, range(3), error_behavior='wrong', disable=True)


def test_invalid_executor():
    with pytest.raises(ValueError):
        progress_map(tasks.square, range(3), executor='gpu', disable=True)


def test_iterator_without_total_raises():
    with pytest.raises(ValueError):
        progress_map(tasks.square, (x for x in range(5)), disable=True)
