"""Lista doblemente enlazada propia para listas de adyacencia e historial temporal."""

from typing import Callable, Generic, Iterator, Optional, TypeVar

T = TypeVar("T")


class DoublyLinkedNode(Generic[T]):
    """Nodo de una lista doblemente enlazada."""

    __slots__ = ("data", "prev", "next")

    def __init__(self, data: T) -> None:
        self.data: T = data
        self.prev: Optional["DoublyLinkedNode[T]"] = None
        self.next: Optional["DoublyLinkedNode[T]"] = None


class LinkedList(Generic[T]):
    """Lista doblemente enlazada implementada desde cero."""

    def __init__(self) -> None:
        self._head: Optional[DoublyLinkedNode[T]] = None
        self._tail: Optional[DoublyLinkedNode[T]] = None
        self._size: int = 0

    @property
    def head(self) -> Optional[DoublyLinkedNode[T]]:
        return self._head

    @property
    def tail(self) -> Optional[DoublyLinkedNode[T]]:
        return self._tail

    def is_empty(self) -> bool:
        return self._size == 0

    def append(self, value: T) -> DoublyLinkedNode[T]:
        """Agrega un elemento al final en O(1)."""
        node = DoublyLinkedNode(value)
        if self._tail is None:
            self._head = node
            self._tail = node
        else:
            node.prev = self._tail
            self._tail.next = node
            self._tail = node
        self._size += 1
        return node

    def prepend(self, value: T) -> DoublyLinkedNode[T]:
        """Agrega un elemento al inicio en O(1)."""
        node = DoublyLinkedNode(value)
        if self._head is None:
            self._head = node
            self._tail = node
        else:
            node.next = self._head
            self._head.prev = node
            self._head = node
        self._size += 1
        return node

    def pop_front(self) -> T:
        """Elimina y retorna el primer elemento en O(1)."""
        if self._head is None:
            raise IndexError("pop_front desde una LinkedList vacía")
        value = self._head.data
        self._head = self._head.next
        if self._head is None:
            self._tail = None
        else:
            self._head.prev = None
        self._size -= 1
        return value

    def pop_back(self) -> T:
        """Elimina y retorna el último elemento en O(1)."""
        if self._tail is None:
            raise IndexError("pop_back desde una LinkedList vacía")
        value = self._tail.data
        self._tail = self._tail.prev
        if self._tail is None:
            self._head = None
        else:
            self._tail.next = None
        self._size -= 1
        return value

    def peek_front(self) -> T:
        """Retorna el primer elemento sin eliminarlo."""
        if self._head is None:
            raise IndexError("peek_front desde una LinkedList vacía")
        return self._head.data

    def peek_back(self) -> T:
        """Retorna el último elemento sin eliminarlo."""
        if self._tail is None:
            raise IndexError("peek_back desde una LinkedList vacía")
        return self._tail.data

    def get_at(self, index: int) -> T:
        """Obtiene el elemento en la posición `index` (soporta índices negativos)."""
        if index < 0:
            index += self._size
        if index < 0 or index >= self._size:
            raise IndexError(f"Índice fuera de rango: {index}")

        if index <= self._size // 2:
            curr = self._head
            for _ in range(index):
                assert curr is not None
                curr = curr.next
        else:
            curr = self._tail
            for _ in range(self._size - 1 - index):
                assert curr is not None
                curr = curr.prev
        assert curr is not None
        return curr.data

    def remove_if(self, predicate: Callable[[T], bool]) -> Optional[T]:
        """Elimina y retorna el primer elemento que cumple `predicate`."""
        curr = self._head
        while curr is not None:
            if predicate(curr.data):
                if curr.prev is not None:
                    curr.prev.next = curr.next
                else:
                    self._head = curr.next
                if curr.next is not None:
                    curr.next.prev = curr.prev
                else:
                    self._tail = curr.prev
                self._size -= 1
                return curr.data
            curr = curr.next
        return None

    def clear(self) -> None:
        """Elimina todos los elementos de la lista."""
        self._head = None
        self._tail = None
        self._size = 0

    def iter_forward(self) -> Iterator[T]:
        """Itera desde el inicio hasta el final."""
        curr = self._head
        while curr is not None:
            yield curr.data
            curr = curr.next

    def iter_backward(self) -> Iterator[T]:
        """Itera desde el final hasta el inicio."""
        curr = self._tail
        while curr is not None:
            yield curr.data
            curr = curr.prev

    def to_list(self) -> list[T]:
        """Convierte a lista estándar de Python para visualización o exportación."""
        return list(self.iter_forward())

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[T]:
        return self.iter_forward()

    def __getitem__(self, index: int) -> T:
        return self.get_at(index)

    def __repr__(self) -> str:
        return f"LinkedList({self.to_list()!r})"
