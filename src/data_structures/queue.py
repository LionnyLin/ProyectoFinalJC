"""Cola FIFO implementada sobre LinkedList propia."""

from typing import Generic, Iterator, TypeVar
from .linked_list import LinkedList

T = TypeVar("T")


class Queue(Generic[T]):
    """Cola FIFO para recorridos BFS y procesamiento secuencial de eventos."""

    def __init__(self) -> None:
        self._items: LinkedList[T] = LinkedList()

    def enqueue(self, item: T) -> None:
        """Inserta un elemento al final de la cola en O(1)."""
        self._items.append(item)

    def dequeue(self) -> T:
        """Extrae y retorna el elemento al frente de la cola en O(1)."""
        if self._items.is_empty():
            raise IndexError("dequeue desde una Queue vacía")
        return self._items.pop_front()

    def peek(self) -> T:
        """Retorna el elemento al frente sin extraerlo."""
        if self._items.is_empty():
            raise IndexError("peek desde una Queue vacía")
        return self._items.peek_front()

    def is_empty(self) -> bool:
        return self._items.is_empty()

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)

    def __repr__(self) -> str:
        return f"Queue({self._items.to_list()!r})"
