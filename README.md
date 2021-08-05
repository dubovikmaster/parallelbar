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
if __name__=='__main__':
    progress_map(cpu_bench, tasks)
```


      0%|          | 0/100 [00:00<?, ?it/s]


You can display the progress on each core:


```python
if __name__=='__main__':
    progress_map(cpu_bench, tasks, core_progress=True)
```


    Core 1:   0%|          | 0/16 [00:00<?, ?it/s]



    Core 2:   0%|          | 0/16 [00:00<?, ?it/s]



    Core 3:   0%|          | 0/16 [00:00<?, ?it/s]



    Core 4:   0%|          | 0/16 [00:00<?, ?it/s]



    Core 5:   0%|          | 0/16 [00:00<?, ?it/s]



    Core 6:   0%|          | 0/16 [00:00<?, ?it/s]



    Core 7:   0%|          | 0/16 [00:00<?, ?it/s]



    Core 8:   0%|          | 0/16 [00:00<?, ?it/s]


Ofcourse you can specify the number of cores and chunk_size:


```python
if __name__=='__main__':
    tasks = [5_000_00 + i for i in range(100)]
    progress_map(cpu_bench, tasks, n_cpu=4, chunk_size=1, core_progress=True)
```


    Core 1:   0%|          | 0/25 [00:00<?, ?it/s]



    Core 2:   0%|          | 0/25 [00:00<?, ?it/s]



    Core 3:   0%|          | 0/25 [00:00<?, ?it/s]



    Core 4:   0%|          | 0/25 [00:00<?, ?it/s]


You can also easily use **progress_imap** and **progress_imapu** analogs of the *imap* and *imap_unordered* methods of the **Pool()** class


```python
%%time
if __name__=='__main__':
    tasks = [20 + i for i in range(15)]
    result = progress_imap(fibonacci, tasks, chunk_size=1, core_progress=False)
```


      0%|          | 0/15 [00:00<?, ?it/s]


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




```python

```
