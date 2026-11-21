"""Cola de prioridad propia (Min-Heap binario) para eventos temporales y ranking."""

from typing import Any, Generic, List, Tuple, TypeVar

T = TypeVar("T")


class PriorityQueue(Generic[T]):
    """Min-Heap binario desde cero con tuplas (priority, seq, item) deterministas."""

    __slots__ = ("_heap", "_seq")

    def __init__(self) -> None:
        self._heap: List[Tuple[Any, int, T]] = []
        self._seq: int = 0

    def _sift_up(self, idx: int) -> None:
        heap = self._heap
        while idx > 0:
            parent = (idx - 1) >> 1
            if heap[idx] < heap[parent]:
                heap[idx], heap[parent] = heap[parent], heap[idx]
                idx = parent
            else:
                break

    def _sift_down(self, idx: int) -> None:
        heap = self._heap
        n = len(heap)
        while True:
            left = (idx << 1) + 1
            if left >= n:
                break
            right = left + 1
            smallest = right if right < n and heap[right] < heap[left] else left
            if heap[smallest] < heap[idx]:
                heap[idx], heap[smallest] = heap[smallest], heap[idx]
                idx = smallest
            else:
                break

    def push(self, priority: Any, item: T) -> None:
        self._heap.append((priority, self._seq, item))
        self._seq += 1
        self._sift_up(len(self._heap) - 1)

    def pop(self) -> Tuple[Any, T]:
        heap = self._heap
        if not heap:
            raise IndexError("pop desde una PriorityQueue vacía")
        top_prio, _, top_item = heap[0]
        last = heap.pop()
        if heap:
            heap[0] = last
            self._sift_down(0)
        return top_prio, top_item

    def peek(self) -> Tuple[Any, T]:
        if not self._heap:
            raise IndexError("peek desde una PriorityQueue vacía")
        prio, _, item = self._heap[0]
        return prio, item

    def clear(self) -> None:
        self._heap.clear()
        self._seq = 0

    def is_empty(self) -> bool: return not self._heap
    def __len__(self) -> int: return len(self._heap)
    def __bool__(self) -> bool: return bool(self._heap)
    def __repr__(self) -> str: return f"PriorityQueue(size={len(self._heap)})"
