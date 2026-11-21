"""Cola FIFO implementada sobre LinkedList propia."""

from typing import Generic, Iterator, TypeVar
from .linked_list import LinkedList

T = TypeVar("T")


class Queue(Generic[T]):
    """Cola FIFO O(1) para recorridos BFS y procesamiento de eventos."""

    __slots__ = ("_items",)

    def __init__(self) -> None:
        self._items: LinkedList[T] = LinkedList()

    def enqueue(self, item: T) -> None:
        self._items.append(item)

    def dequeue(self) -> T:
        if self._items.is_empty():
            raise IndexError("dequeue desde una Queue vacía")
        return self._items.pop_front()

    def peek(self) -> T:
        if self._items.is_empty():
            raise IndexError("peek desde una Queue vacía")
        return self._items.peek_front()

    def is_empty(self) -> bool: return self._items.is_empty()
    def clear(self) -> None: self._items.clear()
    def __len__(self) -> int: return len(self._items)
    def __iter__(self) -> Iterator[T]: return iter(self._items)
    def __repr__(self) -> str: return f"Queue({self._items.to_list()!r})"
