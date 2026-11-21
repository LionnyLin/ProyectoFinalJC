"""Tabla hash propia con encadenamiento separado y capacidad potencia de 2."""

from typing import Any, Generic, Iterator, List, Tuple, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class _Entry(Generic[K, V]):
    __slots__ = ("key", "value")

    def __init__(self, key: K, value: V) -> None:
        self.key = key
        self.value = value


def _next_power_of_two(n: int) -> int:
    cap = 16
    while cap < n:
        cap <<= 1
    return cap


class HashTable(Generic[K, V]):
    """Tabla hash desde cero (capacidad 2^k, máscara de bits) O(1) promedio."""

    DEFAULT_CAPACITY = 16
    LOAD_FACTOR_THRESHOLD = 0.75
    __slots__ = ("_buckets", "_mask", "_size")

    def __init__(self, initial_capacity: int = DEFAULT_CAPACITY) -> None:
        capacity = _next_power_of_two(initial_capacity)
        self._buckets: List[List[_Entry[K, V]]] = [[] for _ in range(capacity)]
        self._mask: int = capacity - 1
        self._size: int = 0

    def _rehash(self, new_capacity: int) -> None:
        new_mask = new_capacity - 1
        new_buckets: List[List[_Entry[K, V]]] = [[] for _ in range(new_capacity)]
        for bucket in self._buckets:
            for entry in bucket:
                new_buckets[hash(entry.key) & new_mask].append(entry)
        self._buckets = new_buckets
        self._mask = new_mask

    def _append_new(self, bucket: List[_Entry[K, V]], key: K, value: V) -> None:
        if (self._size + 1) > len(self._buckets) * self.LOAD_FACTOR_THRESHOLD:
            self._rehash(len(self._buckets) << 1)
            bucket = self._buckets[hash(key) & self._mask]
        bucket.append(_Entry(key, value))
        self._size += 1

    def put(self, key: K, value: V) -> None:
        bucket = self._buckets[hash(key) & self._mask]
        for entry in bucket:
            if entry.key == key:
                entry.value = value
                return
        self._append_new(bucket, key, value)

    def add(self, key: K, delta: float) -> float:
        """Incrementa un acumulador numérico (o lo crea) en una sola búsqueda de bucket."""
        bucket = self._buckets[hash(key) & self._mask]
        for entry in bucket:
            if entry.key == key:
                new_val = entry.value + delta  # type: ignore[operator]
                entry.value = new_val
                return new_val
        self._append_new(bucket, key, delta)  # type: ignore[arg-type]
        return delta

    def get(self, key: K, default: Any = None) -> Any:
        for entry in self._buckets[hash(key) & self._mask]:
            if entry.key == key:
                return entry.value
        return default

    def contains(self, key: K) -> bool:
        for entry in self._buckets[hash(key) & self._mask]:
            if entry.key == key:
                return True
        return False

    def remove(self, key: K) -> V:
        bucket = self._buckets[hash(key) & self._mask]
        for i, entry in enumerate(bucket):
            if entry.key == key:
                bucket.pop(i)
                self._size -= 1
                return entry.value
        raise KeyError(key)

    def setdefault(self, key: K, default: V) -> V:
        bucket = self._buckets[hash(key) & self._mask]
        for entry in bucket:
            if entry.key == key:
                return entry.value
        self._append_new(bucket, key, default)
        return default

    def clear(self) -> None:
        self._buckets = [[] for _ in range(self.DEFAULT_CAPACITY)]
        self._mask = self.DEFAULT_CAPACITY - 1
        self._size = 0

    def keys(self) -> List[K]: return [e.key for b in self._buckets for e in b]
    def values(self) -> List[V]: return [e.value for b in self._buckets for e in b]
    def items(self) -> List[Tuple[K, V]]: return [(e.key, e.value) for b in self._buckets for e in b]
    def __len__(self) -> int: return self._size
    def __contains__(self, key: object) -> bool: return self.contains(key)  # type: ignore[arg-type]

    def __getitem__(self, key: K) -> V:
        for entry in self._buckets[hash(key) & self._mask]:
            if entry.key == key:
                return entry.value
        raise KeyError(key)

    def __setitem__(self, key: K, value: V) -> None: self.put(key, value)
    def __delitem__(self, key: K) -> None: self.remove(key)

    def __iter__(self) -> Iterator[K]:
        for bucket in self._buckets:
            for entry in bucket:
                yield entry.key

    def __repr__(self) -> str:
        pairs = ", ".join(f"{k!r}: {v!r}" for k, v in self.items())
        return f"HashTable({{{pairs}}})"
