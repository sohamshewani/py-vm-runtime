"""
pyvm/gc.py - Precise Tricolor Mark-and-Sweep Garbage Collector for py-vm-runtime.

Implements a deterministic memory manager with allocation pressure monitoring,
safepoint yields, root tracking, and object lifecycle hooks.
"""

from __future__annotations__

import sys
import threading
from typing import Any, Dict, List, Optional, Set, Tuple, final


class GCHeader:
    """Memory overhead header for heap-allocated py-vm objects."""

    __slots__ = ("color", "marked", "size", "forwarded")

    def __init__(self, size: int = 1) -> None:
        self.color: int = 0  # 0: White, 1: Grey, 2: Black
        self.marked: bool = False
        self.size: int = size
        self.forwarded: Optional[HeapObject] = None


class HeapObject:
    """Base class for all heap-allocated entities within the py-vm runtime."""

    __slots__ = ("gc_header", "attributes")

    def __init__(self, size: int = 1) -> None:
        self.gc_header = GCHeader(size=size)
        self.attributes: Dict[str, Any] = {}

    def get_references(self) -> List[HeapObject]:
        """Extract all outgoing heap references for tricolor traversal."""
        refs: List[HeapObject] = []
        for value in self.attributes.values():
            if isinstance(value, HeapObject):
                refs.append(value)
            elif isinstance(value, (list, tuple, set)):
                for item in value:
                    if isinstance(item, HeapObject):
                        refs.append(item)
            elif isinstance(value, dict):
                for k, v in value.items():
                    if isinstance(k, HeapObject):
                        refs.append(k)
                    if isinstance(v, HeapObject):
                        refs.append(v)
        return refs


@final
class GarbageCollector:
    """Precise Tricolor Mark-and-Sweep Garbage Collector."""

    WHITE = 0
    GREY = 1
    BLACK = 2

    def __init__(self, allocation_threshold: int = 1024) -> None:
        self.heap: Set[HeapObject] = set()
        self.roots: Set[HeapObject] = set()
        self.allocation_count: int = 0
        self.allocation_threshold: int = allocation_threshold
        self._lock = threading.Lock()
        self._collecting = False

    def register_root(self, obj: HeapObject) -> None:
        """Register an object root with the garbage collector."""
        with self._lock:
            if isinstance(obj, HeapObject):
                self.roots.add(obj)

    def unregister_root(self, obj: HeapObject) -> None:
        """Unregister an object root from the garbage collector."""
        with self._lock:
            if obj in self.roots:
                self.roots.remove(obj)

    def allocate(self, obj_type: type, size: int = 1, *args: Any, **kwargs: Any) -> HeapObject:
        """Allocate a new heap object, checking safepoints and trigger collection if needed."""
        with self._lock:
            self.allocation_count += size
            if self.allocation_count >= self.allocation_threshold and not self._collecting:
                self._safepoint_collect()

            instance = obj_type(*args, **kwargs)
            if not isinstance(instance, HeapObject):
                raise TypeError(f"Managed allocation requires HeapObject subclass, got {obj_type}")
            
            instance.gc_header.size = size
            instance.gc_header.color = self.WHITE
            self.heap.add(instance)
            return instance

    def _safepoint_collect(self) -> None:
        """Execute a full mark-and-sweep garbage collection cycle internally."""
        if self._collecting:
            return
        self._collecting = True
        try:
            self.collect()
        finally:
            self._collecting = False
            self.allocation_count = 0

    def collect(self) -> int:
        """Run the precise tricolor mark-and-sweep algorithm.

        Returns:
            The number of reclaimed heap objects.
        """
        with self._lock:
            grey_stack: List[HeapObject] = []

            # Phase 1: Mark Roots (White -> Grey)
            for root in self.roots:
                if root in self.heap:
                    root.gc_header.color = self.GREY
                    grey_stack.append(root)

            # Phase 2: Propagation / Traversal (Grey -> Black)
            while grey_stack:
                obj = grey_stack.pop()
                obj.gc_header.color = self.BLACK
                for child in obj.get_references():
                    if child in self.heap and child.gc_header.color == self.WHITE:
                        child.gc_header.color = self.GREY
                        grey_stack.append(child)

            # Phase 3: Sweep (White collection)
            surviving_heap: Set[HeapObject] = set()
            reclaimed_count = 0

            for obj in self.heap:
                if obj.gc_header.color == self.BLACK:
                    obj.gc_header.color = self.WHITE
                    surviving_heap.add(obj)
                else:
                    reclaimed_count += 1
                    # Clear references to break circular dependencies explicitly
                    obj.attributes.clear()

            self.heap = surviving_heap
            return reclaimed_count

    def force_collection(self) -> int:
        """Public entrypoint to force an immediate GC cycle."""
        with self._lock:
            self._collecting = True
            try:
                reclaimed = self.collect()
                self.allocation_count = 0
                return reclaimed
            finally:
                self._collecting = False

    def get_heap_stats(self) -> Dict[str, int]:
        """Retrieve telemetry data for the garbage collector heap state."""
        with self._lock:
            return {
                "heap_size": len(self.heap),
                "root_count": len(self.roots),
                "allocation_count": self.allocation_count,
                "allocation_threshold": self.allocation_threshold,
            }