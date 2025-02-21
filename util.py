import socket
from contextlib import closing
import heapq
import threading

def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


class ThreadSafeUniquePriorityQueue:
    def __init__(self):
        self.heap = []  # Min-heap for priority order
        self.set = set()  # Track unique elements
        self.lock = threading.Lock()

    def enqueue(self, item, priority):
        """Thread-safe enqueue operation with priority."""
        with self.lock:
            if item not in self.set:
                heapq.heappush(self.heap, (priority, item))
                self.set.add(item)

    def dequeue(self):
        """Thread-safe dequeue operation (removes highest priority item)."""
        with self.lock:
            if self.heap:
                priority, item = heapq.heappop(self.heap)
                self.set.remove(item)
                return item
            raise IndexError("dequeue from an empty queue")

    def size(self) -> int:
        """Thread-safe size check."""
        with self.lock:
            return len(self.heap)

    def __contains__(self, item):
        """Thread-safe membership check."""
        with self.lock:
            return item in self.set

    def __len__(self):
        """Thread-safe length check."""
        with self.lock:
            return len(self.heap)

    def peek(self):
        """Thread-safe peek at the highest-priority element without removing it."""
        with self.lock:
            return self.heap[0][1] if self.heap else None

    def is_empty(self):
        """Thread-safe check for emptiness."""
        with self.lock:
            return len(self.heap) == 0

    def __repr__(self):
        with self.lock:
            return f"ThreadSafeUniquePriorityQueue({[item for _, item in self.heap]})"
