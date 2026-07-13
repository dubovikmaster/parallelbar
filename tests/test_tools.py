import pytest

from parallelbar.tools import (
    func_args_unpack,
    get_len,
    cpu_bench,
    fibonacci,
    iterate_by_pack,
    get_packs_count,
)


def _add(a, b):
    return a + b


def _add_with_queue(a, b, worker_queue=None):
    return (a, b, worker_queue)


def test_func_args_unpack_basic():
    assert func_args_unpack(_add, (2, 3)) == 5


def test_func_args_unpack_with_queue():
    assert func_args_unpack(_add_with_queue, (1, 2), worker_queue='Q') == (1, 2, 'Q')


def test_get_len_with_total():
    assert get_len(range(100), 7) == 7


def test_get_len_from_len():
    assert get_len([1, 2, 3, 4], None) == 4


def test_get_len_range():
    assert get_len(range(10), None) == 10


def test_get_len_generator_no_total_is_none():
    assert get_len((x for x in range(5)), None) is None


def test_cpu_bench_returns_input():
    assert cpu_bench(50) == 50
    assert cpu_bench(0) == 0


@pytest.mark.parametrize('n,expected', [(0, 0), (1, 1), (2, 1), (7, 13), (10, 55)])
def test_fibonacci(n, expected):
    assert fibonacci(n) == expected


def test_iterate_by_pack_even():
    assert list(iterate_by_pack([1, 2, 3, 4], 2)) == [[1, 2], [3, 4]]


def test_iterate_by_pack_remainder():
    assert list(iterate_by_pack([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_iterate_by_pack_default_size():
    assert list(iterate_by_pack([1, 2, 3])) == [[1], [2], [3]]


def test_iterate_by_pack_empty():
    assert list(iterate_by_pack([], 3)) == []


def test_iterate_by_pack_invalid_size():
    with pytest.raises(ValueError):
        list(iterate_by_pack([1, 2, 3], 0))


def test_get_packs_count_exact():
    assert get_packs_count([1, 2, 3, 4], 2) == 2


def test_get_packs_count_remainder():
    assert get_packs_count([1, 2, 3, 4, 5], 2) == 3
