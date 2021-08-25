from parallelbar.tools import cpu_bench
from parallelbar import progress_imap




if __name__ == '__main__':
    tasks = (5_000_000 + i for i in range(30))
    result = progress_imap(cpu_bench, tasks, core_progress=True)