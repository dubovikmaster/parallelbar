## Parallelbar

**Parallelbar** displays the progress of tasks in the process pool for methods such as **map**, **imap** and **imap_unordered**. Parallelbar is based on the [tqdm](https://github.com/tqdm/tqdm) module and the standard python [multiprocessing](https://docs.python.org/3/library/multiprocessing.html) library.

## Installation

    pip install --user git+https://github.com/dubovikmaster/parallelbar.git


## Example


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

![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/first_bar.gif)

Great! We got an acceleration of 6 times! We were also able to observe the process
What about the progress on the cores of your cpu?


```python
if __name__=='__main__':
    progress_map(cpu_bench, tasks, core_progress=True)
```
![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/multiple_bar_8.gif)

Ofcourse you can specify the number of cores and chunk_size:


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

    Wall time: 2.08 s
    


```python
result
```

    [6765,
     10946,
     17711,
     28657,
     46368,
     75025,
     121393,
     196418,
     317811,
     514229,
     832040,
     1346269,
     2178309,
     3524578,
     5702887]

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
        tasks.insert(1, 38)
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
    with Pool() as p:
        tasks = [20 + i for i in range(15)]
        tasks.insert(1, 38)
        result = progress_imap(fibonacci, tasks)
```

![](https://raw.githubusercontent.com/dubovikmaster/parallelbar/main/gifs/imap_naive_3.gif)

The progress_imap function takes care of collecting the result and closing the process pool for you.
In fact, the naive approach described above will work for the standard imap_unordered method. But it does not guarantee the order of the returned result. This is often critically important.

## License

MIT license
