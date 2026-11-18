"""Pila LIFO implementada sobre LinkedList propia."""

from typing import Generic, Iterator, TypeVar
from .linked_list import LinkedList

T = TypeVar("T")


class Stack(Generic[T]):
    """Pila LIFO para recorrido DFS iterativo y reconstrucción de caminos."""

    def __init__(self) -> None:
        self._items: LinkedList[T] = LinkedList()

    def push(self, item: T) -> None:
        """Apila un elemento en el tope en O(1)."""
        self._items.append(item)

    def pop(self) -> T:
        """Desapila y retorna el elemento del tope en O(1)."""
        if self._items.is_empty():
            raise IndexError("pop desde una Stack vacía")
        return self._items.pop_back()

    def peek(self) -> T:
        """Retorna el elemento del tope sin desapilarlo."""
        if self._items.is_empty():
            raise IndexError("peek desde una Stack vacía")
        return self._items.peek_back()

    def is_empty(self) -> bool:
        return self._items.is_empty()

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T]:
        return self._items.iter_backward()

    def __repr__(self) -> str:
        return f"Stack({self._items.to_list()!r})"
