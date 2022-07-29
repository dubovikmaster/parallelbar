
# Parallelbar

**Parallelbar** displays the progress of tasks in the process pool for methods such as **map**, **imap** and **imap_unordered**. Parallelbar is based on the [tqdm](https://github.com/tqdm/tqdm) module and the standard python [multiprocessing](https://docs.python.org/3/library/multiprocessing.html) library. 
Starting from version 0.2.0, the **ProcessPoll** class of the [pebble](https://github.com/noxdafox/pebble) library is used to implement the **map** method. Thanks to this, it became possible to handle exceptions that occur within a separate process and also set a timeout for the execution of a task by a process.

## Installation

    pip install parallelbar
    or
    pip install --user git+https://github.com/dubovikmaster/parallelbar.git



## Usage


```python
from parallelbar import progress_imap, progress_map, progress_imapu
from parallelbar.tools import cpu_bench, fibonacci
```

Let's create a list of 100 numbers and test **progress_map** with default parameters on a toy function **cpu_bench**:


```python
tasks = [1_000_000 + i for i in range(100)]
```
```python
%%time
list(map(cpu_bench, tasks))
```
```python
Wall time: 52.6 s
```

Ok, by default this works on one core of my i7-9700F and it took 52 seconds. Let's parallelize the calculations for all 8 cores and look at the progress. This can be easily done by replacing standart function  **map** with **progress_map**.

```python
if __name__=='__main__':
    progress_map(cpu_bench, tasks)
```

![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/first_bar_.gif)

Core progress:

![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/core_progress.gif)

Great! We got an acceleration of 6 times! We were also able to observe the process
What about the progress on the cores of your cpu?



```python
if __name__=='__main__':
    tasks = [5_000_00 + i for i in range(100)]
    progress_map(cpu_bench, tasks, n_cpu=4, chunk_size=1, core_progress=True)
```

![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/multiple_bar_4.gif)

You can also easily use **progress_imap** and **progress_imapu** analogs of the *imap* and *imap_unordered* methods of the **Pool()** class


```python
%%time
if __name__=='__main__':
    tasks = [20 + i for i in range(15)]
    result = progress_imap(fibonacci, tasks, chunk_size=1, core_progress=False)
```

![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/one_bar_imap.gif)

## New in version 0.2.0
Thanks to the [pebble](https://github.com/noxdafox/pebble), it is now possible to handle exceptions and set timeouts for the execution of tasks by the process in the **progress_map** function.   
Consider the following toy example:

```python
def foo(n):
    if n==5 or n==17:
        1/0
    elif n==10:
        time.sleep(2)
    else:
        time.sleep(1)
    return n
if __name__=='__main__':
	res = progress_map(foo, range(20), process_timeout=5, n_cpu=8)
```
![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/error_bar_2.gif)

As you can see, under the main progress bar, another progress bar has appeared that displays the number of tasks that ended unsuccessfully. At the same time, the main bar turned orange, as if signaling something went wrong
```python
print(res)
	[0, 1, 2, 3, 4, ZeroDivisionError('division by zero'), 6, 7, 8, 9, 10, 11, 12,
     13, 14, 15, 16, ZeroDivisionError('division by zero'), 18, 19]
```
 In the resulting array, we have exceptions in the corresponding places. Also, we can see the exception traceback:
```python
print(res[5].traceback)
Traceback (most recent call last):
  File "/home/padu/anaconda3/envs/work/lib/python3.9/site-packages/pebble/common.py", line 174, in process_execute
    return function(*args, **kwargs)
  File "/home/padu/anaconda3/envs/work/lib/python3.9/site-packages/parallelbar/parallelbar.py", line 48, in _process
    result = func(task)
  File "/tmp/ipykernel_70395/285585760.py", line 3, in foo
    1/0
ZeroDivisionError: division by zero
```
From which concept at what place in the code the exception occurred. 
Let's add a timeout of 1.5 seconds for each process. If the process execution time exceeds 1.5 seconds, an appropriate exception will be raised and handled. In this case, the process will restart and continue to work (thanks to **pebble**)
```python
if __name__=='__main__':
	res = progress_map(foo, range(20), process_timeout=1.5, n_cpu=8)
```
![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/error_bar_1.gif)
```python
print(res)
	[0, 1, 2, 3, 4, ZeroDivisionError('division by zero'), 6, 7, 8, 9, 'function foo took longer than 1.5 s.', 
	11, 12, 13, 14, 15, 16, ZeroDivisionError('division by zero'), 18, 19]
```

Exception handling has also been added to methods **progress_imap** and **progress_imapu**. 

## New in version 0.2.10

1. The `process_timeout` keyword argument has been added to the **progress_imap** and **progress_imapu** methods (**can be used only if `chunk_size=1`!**) 
2. The **stopit_after_timeout** decorator has been added to the **tools** module. 
3. Fixed a bug that caused the **progrees_imap** and **progress_imapu** methods to hang if `chunk_size > 1`

Example of using a decorator

```python
from parallelbar.tools import stopit_after_timeout
import time

# abort function execution after timeout in seconds
@stopit_after_timeout(1, raise_exception=False)
def foo():
    for _ in range(5):
        time.sleep(2)
        
if __name__ == '__main__':
    start = time.time()
    print(foo())
    print(f'time took {time.time()-start} s.')
```
```
time took  1.010124 s.
'function foo took longer than 1 s.'
```
As you can see, instead of 5 seconds of execution, the function was interrupted after 1 second of timeout. 
If `raise_exception=True`, a **TimeoutError** exception will be raised.

## New in version 0.3.0
1. The `error_behavior` keyword argument has been added to the **progress_map**, **progress_imap** and **progress_imapu** methods. 
Must be one of the values: "raise", "ignore", "coerce". 
     - "raise" - raise an exception thrown in the process pool.
     - "ignore" - ignore the exceptions that occur. Do not add anything to the result
     - "coerce" - handle the exception. The result will include the value set by the parameter `set_error_value` (by default None - the traceback of the raised exception will be added to the result)
2. The `set_error_value` keyword argument has been added to the **progress_map**, **progress_imap** and **progress_imapu** methods.

Example of usage

```python
import time
import resource as rs
from parallelbar import progress_imap


def memory_limit(limit):
    soft, hard = rs.getrlimit(rs.RLIMIT_AS)
    rs.setrlimit(rs.RLIMIT_AS, (limit, hard))


def my_awesome_foo(n):
    if n == 0:
        s = 'a' * 10000000
    elif n == 20:
        time.sleep(100)
    else:
        time.sleep(1)
    return n


if __name__ == '__main__':
    tasks = range(30)
    start = time.monotonic()
    result = progress_imap(my_awesome_foo, tasks, 
                           process_timeout=1.5, 
                           initializer=memory_limit, 
                           initargs=(100,),
                           n_cpu=4,
                           error_behavior='coerce',
                           set_error_value=None,
                           )
    print(f'time took: {time.monotonic() - start:.1f}')
    print(result)
```
![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/test-new.gif)
```
time took: 8.2
[MemoryError(), 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 
16, 17, 18, 19, TimeoutError('function "my_awesome_foo" took longer than 1.5 s.'), 21, 22, 23, 24, 25, 26, 27, 28, 29]
```
Set NaN instead of tracebacks to the result of the pool operation:
```python
if __name__ == '__main__':
    tasks = range(30)
    start = time.monotonic()
    result = progress_imap(my_awesome_foo, tasks, 
                           process_timeout=1.5, 
                           initializer=memory_limit, 
                           initargs=(100,),
                           n_cpu=4,
                           error_behavior='coerce',
                           set_error_value=float('nan'),
                           )
    print(f'time took: {time.monotonic() - start:.1f}')
    print(result)
```
![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/test-new.gif)
```
time took: 8.0
[nan, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 
16, 17, 18, 19, nan, 21, 22, 23, 24, 25, 26, 27, 28, 29]
```
Let's ignore exception:
```python
if __name__ == '__main__':
    tasks = range(30)
    start = time.monotonic()
    result = progress_imap(my_awesome_foo, tasks, 
                           process_timeout=1.5, 
                           initializer=memory_limit, 
                           initargs=(100,),
                           n_cpu=4,
                           error_behavior='ignore',
                           set_error_value=None,
                           )
    print(f'time took: {time.monotonic() - start:.1f}')
    print(result)
```
![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/test-new.gif)
```
time took: 8.0
[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 
16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 27, 28, 29]
```




## Problems of the naive approach
Why can't I do something simpler? Let's take the standard **imap** method and run through it in a loop with **tqdm** and take the results from the processes:
```python
from multiprocessing import Pool
from tqdm.auto import tqdm
```


```python
if __name__=='__main__':
    with Pool() as p:
        tasks = [20 + i for i in range(15)]
        pool = p.imap(fibonacci, tasks)
        result = []
        for i in tqdm(pool, total=len(tasks)):
            result.append(i)
```

![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/imap_naive_1.gif)

It looks good, doesn't it? But let's do the following, make the first task very difficult for the core. To do this, I will insert the number 38 at the beginning of the tasks list. Let's see what happens

```python
if __name__=='__main__':
    with Pool() as p:
        tasks = [20 + i for i in range(15)]
        tasks.insert(0, 39)
        pool = p.imap_unordered(fibonacci, tasks)
        result = []
        for i in tqdm(pool, total=len(tasks)):
            result.append(i)
```

![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/imap_naive_2.gif)

This is a fiasco. Our progress hung on the completion of the first task and then at the end showed 100% progress.
Let's try to do the same experiment only for the progress_imap function:

```python
if __name__=='__main__':
    tasks = [20 + i for i in range(15)]
    tasks.insert(0, 39)
    result = progress_imap(fibonacci, tasks)
```

![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/imap_naive_3.gif)

The progress_imap function takes care of collecting the result and closing the process pool for you.
In fact, the naive approach described above will work for the standard imap_unordered method. But it does not guarantee the order of the returned result. This is often critically important.

## License

MIT license
