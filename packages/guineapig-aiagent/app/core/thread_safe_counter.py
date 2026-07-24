import threading


# 线程安全的计数器类
class ThreadSafeCounter:
    def __init__(self, initial_value=0):
        self._value = initial_value
        self._lock = threading.Lock()

    def increment(self, delta=1):
        with self._lock:
            self._value += delta
            return self._value

    def decrement(self, delta=1):
        """减少计数器值"""
        with self._lock:
            self._value -= delta
            return self._value

    def get(self):
        with self._lock:
            return self._value
