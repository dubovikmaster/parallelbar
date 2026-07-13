import pytest

import tasks
from parallelbar import progress_map, progress_starmap, progress_imap, Parallel


def test_map_retries_recover(clean_retry_dir):
    assert progress_map(tasks.flaky, range(10), n_cpu=2, retries=2, disable=True) == list(range(10))


def test_map_retries_not_enough(clean_retry_dir):
    # flaky needs 1 retry to recover; with retries=0 it should still have failures (raise)
    with pytest.raises(ValueError):
        progress_map(tasks.flaky, range(10), n_cpu=2, retries=0, disable=True)


def test_map_retries_exhausted_raise():
    with pytest.raises(ValueError):
        progress_map(tasks.always_fail_2_5, range(10), n_cpu=2, retries=1, disable=True)


def test_map_retries_exhausted_coerce():
    res = progress_map(tasks.always_fail_2_5, range(10), n_cpu=2, retries=1,
                       error_behavior='coerce', disable=True)
    assert isinstance(res[2], ValueError)
    assert isinstance(res[5], ValueError)
    assert res[0] == 0 and res[9] == 9


def test_map_retries_exhausted_set_error_value():
    res = progress_map(tasks.always_fail_2_5, range(10), n_cpu=2, retries=1,
                       error_behavior='coerce', set_error_value=-1, disable=True)
    assert res[2] == -1 and res[5] == -1


def test_map_retries_return_failed_tasks():
    res, failed = progress_map(tasks.always_fail_2_5, range(10), n_cpu=2, retries=1,
                               error_behavior='coerce', return_failed_tasks=True, disable=True)
    assert sorted(failed) == [2, 5]


def test_map_retries_incompatible_with_add_progress():
    with pytest.raises(ValueError):
        progress_map(tasks.identity, range(5), retries=2, used_add_progress_decorator=True, disable=True)


def test_starmap_retries_incompatible_with_add_progress():
    with pytest.raises(ValueError):
        progress_starmap(tasks.add, [(1, 2)], retries=2, used_add_progress_decorator=True, disable=True)


def test_imap_retries_incompatible_with_add_progress():
    with pytest.raises(ValueError):
        progress_imap(tasks.identity, range(5), retries=2, used_add_progress_decorator=True, disable=True)


def test_starmap_retries_exhausted_coerce():
    res = progress_starmap(tasks.add, [(1, 2), ('a', 1)], n_cpu=2, retries=1,
                           error_behavior='coerce', disable=True)
    assert res[0] == 3
    assert isinstance(res[1], TypeError)


def test_imap_retries_recover(clean_retry_dir):
    assert progress_imap(tasks.flaky, range(10), n_cpu=2, retries=2, disable=True) == list(range(10))


def test_parallel_map_retries(clean_retry_dir):
    with Parallel(n_cpu=2) as par:
        assert par.map(tasks.flaky, range(10), retries=2, disable=True) == list(range(10))


def test_parallel_imapu_retries_rejected():
    with pytest.raises(ValueError):
        with Parallel(n_cpu=2) as par:
            par.imapu(tasks.identity, range(5), retries=2, disable=True)
