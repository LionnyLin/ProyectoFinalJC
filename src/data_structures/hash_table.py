"""Tabla hash propia con encadenamiento separado y redimensionamiento dinámico."""

from typing import Any, Generic, Iterator, List, Optional, Tuple, TypeVar

K = TypeVar("K")
V = TypeVar("V")

_SENTINEL = object()


class _Entry(Generic[K, V]):
    """Par clave-valor almacenado en un bucket de la tabla hash."""

    __slots__ = ("key", "value")

    def __init__(self, key: K, value: V) -> None:
        self.key = key
        self.value = value


class HashTable(Generic[K, V]):
    """Tabla hash implementada desde cero para consulta O(1) promedio por identificador."""

    DEFAULT_CAPACITY = 16
    LOAD_FACTOR_THRESHOLD = 0.75

    def __init__(self, initial_capacity: int = DEFAULT_CAPACITY) -> None:
        capacity = max(8, initial_capacity)
        self._buckets: List[List[_Entry[K, V]]] = [[] for _ in range(capacity)]
        self._size = 0

    def _bucket_index(self, key: K, capacity: Optional[int] = None) -> int:
        cap = capacity if capacity is not None else len(self._buckets)
        return (hash(key) & 0x7FFFFFFF) % cap

    def _rehash(self, new_capacity: int) -> None:
        new_buckets: List[List[_Entry[K, V]]] = [[] for _ in range(new_capacity)]
        for bucket in self._buckets:
            for entry in bucket:
                idx = self._bucket_index(entry.key, new_capacity)
                new_buckets[idx].append(entry)
        self._buckets = new_buckets

    def put(self, key: K, value: V) -> None:
        """Inserta o actualiza el valor asociado a `key`."""
        if (self._size + 1) / len(self._buckets) > self.LOAD_FACTOR_THRESHOLD:
            self._rehash(len(self._buckets) * 2)

        idx = self._bucket_index(key)
        bucket = self._buckets[idx]
        for entry in bucket:
            if entry.key == key:
                entry.value = value
                return
        bucket.append(_Entry(key, value))
        self._size += 1

    def get(self, key: K, default: Any = None) -> Any:
        """Retorna el valor asociado a `key` o `default` si no existe."""
        idx = self._bucket_index(key)
        for entry in self._buckets[idx]:
            if entry.key == key:
                return entry.value
        return default

    def contains(self, key: K) -> bool:
        """Indica si `key` está presente en la tabla."""
        idx = self._bucket_index(key)
        return any(entry.key == key for entry in self._buckets[idx])

    def remove(self, key: K) -> V:
        """Elimina `key` y retorna su valor; lanza KeyError si no existe."""
        idx = self._bucket_index(key)
        bucket = self._buckets[idx]
        for i, entry in enumerate(bucket):
            if entry.key == key:
                bucket.pop(i)
                self._size -= 1
                return entry.value
        raise KeyError(key)

    def clear(self) -> None:
        """Vacía la tabla hash conservando una capacidad base."""
        self._buckets = [[] for _ in range(self.DEFAULT_CAPACITY)]
        self._size = 0

    def keys(self) -> List[K]:
        """Retorna todas las claves almacenadas."""
        return [entry.key for bucket in self._buckets for entry in bucket]

    def values(self) -> List[V]:
        """Retorna todos los valores almacenados."""
        return [entry.value for bucket in self._buckets for entry in bucket]

    def items(self) -> List[Tuple[K, V]]:
        """Retorna pares (clave, valor)."""
        return [(entry.key, entry.value) for bucket in self._buckets for entry in bucket]

    def setdefault(self, key: K, default: V) -> V:
        """Retorna el valor de `key` si existe; en caso contrario inserta y retorna `default`."""
        existing = self.get(key, _SENTINEL)
        if existing is not _SENTINEL:
            return existing
        self.put(key, default)
        return default

    def __getitem__(self, key: K) -> V:
        val = self.get(key, _SENTINEL)
        if val is _SENTINEL:
            raise KeyError(key)
        return val

    def __setitem__(self, key: K, value: V) -> None:
        self.put(key, value)

    def __delitem__(self, key: K) -> None:
        self.remove(key)

    def __contains__(self, key: object) -> bool:
        return self.contains(key)  # type: ignore[arg-type]

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[K]:
        for bucket in self._buckets:
            for entry in bucket:
                yield entry.key

    def __repr__(self) -> str:
        pairs = ", ".join(f"{k!r}: {v!r}" for k, v in self.items())
        return f"HashTable({{{pairs}}})"
