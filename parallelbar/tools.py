from math import sin, cos, radians


def func_args_unpack(func, args):
    return func(*args)


def get_len(iterable, total):
    try:
        length = iterable.__len__()
    except AttributeError:
        length = total
    return length


def cpu_bench(number):
    product = 1.0
    for elem in range(number):
        angle = radians(elem)
        product *= sin(angle)**2 + cos(angle)**2
    return product


def fibonacci(number):
    if number <= 1:
        return number
    else:
        return fibonacci(number-2) + fibonacci(number-1)


def iterate_by_pack(iterable, pack_size: int = 1):
    if pack_size < 1:
        raise ValueError("pack_size must be greater than 0")
    iterator = iter(iterable)
    sentinel = object()
    item = None
    while item is not sentinel:
        pack = []
        for _ in range(pack_size):
            item = next(iterator, sentinel)
            if item is sentinel:
                break
            pack.append(item)
        if pack:
            yield pack


def get_packs_count(array, pack_size):
    total, extra = divmod(len(array), pack_size)
    if extra:
        total += 1
    return total

