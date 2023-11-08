import platform
import multiprocessing as mp

if platform.system() in ['Windows', 'Darwin']:
    _WORKER_QUEUE = None
else:
    _WORKER_QUEUE = mp.Manager().Queue()
