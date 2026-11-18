"""Cola de prioridad propia (Min-Heap binario) para eventos temporales y ranking."""

from typing import Any, Generic, List, Tuple, TypeVar

T = TypeVar("T")


class PriorityQueue(Generic[T]):
    """Min-Heap binario implementado desde cero con desempate determinista por inserción."""

    def __init__(self) -> None:
        self._heap: List[Tuple[Any, int, T]] = []
        self._seq: int = 0

    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def push(self, priority: Any, item: T) -> None:
        """Inserta `item` con prioridad numérica `priority` en O(log n)."""
        self._heap.append((priority, self._seq, item))
        self._seq += 1
        self._sift_up(len(self._heap) - 1)

    def pop(self) -> Tuple[Any, T]:
        """Extrae y retorna `(priority, item)` de menor prioridad en O(log n)."""
        if not self._heap:
            raise IndexError("pop desde una PriorityQueue vacía")
        top_prio, _, top_item = self._heap[0]
        last = self._heap.pop()
        if self._heap:
            self._heap[0] = last
            self._sift_down(0)
        return top_prio, top_item

    def peek(self) -> Tuple[Any, T]:
        """Retorna `(priority, item)` de menor prioridad sin extraerlo."""
        if not self._heap:
            raise IndexError("peek desde una PriorityQueue vacía")
        prio, _, item = self._heap[0]
        return prio, item

    def clear(self) -> None:
        self._heap.clear()
        self._seq = 0

    def _sift_up(self, idx: int) -> None:
        while idx > 0:
            parent = (idx - 1) // 2
            if self._heap[idx] < self._heap[parent]:
                self._heap[idx], self._heap[parent] = self._heap[parent], self._heap[idx]
                idx = parent
            else:
                break

    def _sift_down(self, idx: int) -> None:
        n = len(self._heap)
        while True:
            smallest = idx
            left = 2 * idx + 1
            right = 2 * idx + 2
            if left < n and self._heap[left] < self._heap[smallest]:
                smallest = left
            if right < n and self._heap[right] < self._heap[smallest]:
                smallest = right
            if smallest != idx:
                self._heap[idx], self._heap[smallest] = self._heap[smallest], self._heap[idx]
                idx = smallest
            else:
                break

    def __len__(self) -> int:
        return len(self._heap)

    def __repr__(self) -> str:
        return f"PriorityQueue(size={len(self._heap)})"
