import tasks
from parallelbar import progress_map


def test_traceback_attached_on_coerce():
    res = progress_map(tasks.boom_on_3, range(5), n_cpu=2, error_behavior='coerce', disable=True)
    err = res[3]
    assert isinstance(err, ValueError)
    assert hasattr(err, 'traceback')
    assert 'ValueError' in err.traceback
    assert 'boom on 3' in err.traceback


def test_traceback_points_to_user_code():
    res = progress_map(tasks.boom_on_3, [3], n_cpu=1, error_behavior='coerce', disable=True)
    assert 'boom_on_3' in res[0].traceback


def test_coerce_default_error_value_is_exception():
    res = progress_map(tasks.boom_on_3, [3], n_cpu=1, error_behavior='coerce', disable=True)
    assert isinstance(res[0], ValueError)


def test_all_success_no_exceptions():
    res = progress_map(tasks.square, range(20), n_cpu=2, error_behavior='coerce', disable=True)
    assert not any(isinstance(r, Exception) for r in res)
