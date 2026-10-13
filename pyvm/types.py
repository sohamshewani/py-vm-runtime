"""
pyvm/types.py

Production-ready type definitions, AST nodes, bytecode word packing,
memory layout structures, and garbage collection primitives for 'py-vm-runtime'.
"""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


class Opcode(IntEnum):
    """8-bit Opcode enumeration for fixed-width 64-bit bytecode instructions."""
    NOP = 0x00
    LOAD_CONST = 0x01
    LOAD_FAST = 0x02
    STORE_FAST = 0x03
    ADD = 0x04
    SUB = 0x05
    MUL = 0x06
    DIV = 0x07
    MOD = 0x08
    EQ = 0x09
    NE = 0x0A
    LT = 0x0B
    LE = 0x0C
    GT = 0x0D
    GE = 0x0E
    JUMP = 0x0F
    JUMP_IF_TRUE = 0x10
    JUMP_IF_FALSE = 0x11
    CALL = 0x12
    RETURN = 0x13
    ALLOC = 0x14
    LOAD_FIELD = 0x15
    STORE_FIELD = 0x16
    HALT = 0xFF


class Color(IntEnum):
    """Tricolor mark-and-sweep GC colors."""
    WHITE = 0
    GREY = 1
    BLACK = 2


@dataclass(frozen=True, slots=True)
class BytecodeInstruction:
    """
    Fixed-width 64-bit instruction word packed into a structured dataclass.
    Layout:
      - 8-bit Opcode (bits 56-63)
      - 8-bit Register Destination (bits 48-55)
      - 16-bit Operand 1 (bits 32-47)
      - 16-bit Operand 2 (bits 0-31)
    """
    opcode: int
    rd: int
    op1: int
    op2: int

    def __post_init__(self) -> None:
        if not (0 <= self.opcode <= 0xFF):
            raise ValueError(f"Opcode out of 8-bit range: {self.opcode}")
        if not (0 <= self.rd <= 0xFF):
            raise ValueError(f"Register destination out of 8-bit range: {self.rd}")
        if not (0 <= self.op1 <= 0xFFFF):
            raise ValueError(f"Operand 1 out of 16-bit range: {self.op1}")
        if not (0 <= self.op2 <= 0xFFFF):
            raise ValueError(f"Operand 2 out of 32-bit range / 16-bit range: {self.op2}")

    def pack(self) -> int:
        """Packs the instruction fields into a single 64-bit integer word."""
        return (
            (self.opcode << 56)
            | (self.rd << 48)
            | (self.op1 << 32)
            | self.op2
        )

    @classmethod
    def unpack(cls, word: int) -> BytecodeInstruction:
        """Unpacks a 64-bit integer word into a BytecodeInstruction instance."""
        if not (0 <= word <= 0xFFFFFFFFFFFFFFFF):
            raise ValueError(f"Word exceeds 64-bit unsigned bounds: {word}")
        opcode = (word >> 56) & 0xFF
        rd = (word >> 48) & 0xFF
        op1 = (word >> 32) & 0xFFFF
        op2 = word & 0xFFFFFFFF
        return cls(opcode=opcode, rd=rd, op1=op1, op2=op2)


class ASTNode(ABC):
    """Base class for all AST nodes utilizing __slots__ for cache locality."""
    __slots__ = ()


@dataclass(frozen=True, slots=True)
class LiteralNode(ASTNode):
    value: Any


@dataclass(frozen=True, slots=True)
class IdentifierNode(ASTNode):
    name: str


@dataclass(frozen=True, slots=True)
class BinaryOpNode(ASTNode):
    operator: str
    left: ASTNode
    right: ASTNode


@dataclass(frozen=True, slots=True)
class AssignNode(ASTNode):
    target: str
    value: ASTNode


@dataclass(frozen=True, slots=True)
class FunctionDefNode(ASTNode):
    name: str
    params: Tuple[str, ...]
    body: Tuple[ASTNode, ...]


@dataclass(frozen=True, slots=True)
class CallNode(ASTNode):
    callee: ASTNode
    args: Tuple[ASTNode, ...]


@dataclass(frozen=True, slots=True)
class IfNode(ASTNode):
    condition: ASTNode
    then_body: Tuple[ASTNode, ...]
    else_body: Tuple[ASTNode, ...]


class GCObject(ABC):
    """Base class for all heap-allocated objects tracked by the Garbage Collector."""
    __slots__ = ('_gc_color', '_gc_next', '_gc_prev')

    def __init__(self) -> None:
        self._gc_color: Color = Color.WHITE
        self._gc_next: Optional[GCObject] = None
        self._gc_prev: Optional[GCObject] = None

    @property
    def gc_color(self) -> Color:
        return self._gc_color

    @gc_color.setter
    def gc_color(self, color: Color) -> None:
        self._gc_color = color

    @abstractmethod
    def get_references(self) -> List[GCObject]:
        """Returns all child GCObject references for tricolor traversal."""
        pass


@dataclass(slots=True)
class HeapObject(GCObject):
    """Standard heap-allocated object holding arbitrary attributes and values."""
    fields: Dict[str, Any] = field(default_factory=dict)

    def get_references(self) -> List[GCObject]:
        refs: List[GCObject] = []
        for val in self.fields.values():
            if isinstance(val, GCObject):
                refs.append(val)
        return refs


@dataclass(slots=True)
class HeapFunction(GCObject):
    """First-class function object allocated on the heap."""
    name: str
    code: Tuple[BytecodeInstruction, ...]
    free_vars: List[GCObject] = field(default_factory=list)

    def get_references(self) -> List[GCObject]:
        return list(self.free_vars)


class Heap:
    """Manages heap allocation and tricolor mark-and-sweep garbage collection."""
    __slots__ = ('_head', '_allocated_count', '_threshold')

    def __init__(self, threshold: int = 1024) -> None:
        self._head: Optional[GCObject] = None
        self._allocated_count: int = 0
        self._threshold: int = threshold

    def allocate(self, obj: GCObject, roots: List[GCObject]) -> GCObject:
        """Allocates an object, inserting it into the heap list, triggering GC on threshold crossing."""
        if self._allocated_count >= self._threshold:
            self.collect(roots)
        
        obj._gc_color = Color.WHITE
        obj._gc_next = self._head
        obj._gc_prev = None
        if self._head is not None:
            self._head._gc_prev = obj
        self._head = obj
        self._allocated_count += 1
        return obj

    def collect(self, roots: List[GCObject]) -> int:
        """
        Executes a precise tricolor mark-and-sweep garbage collection cycle.
        Returns the number of reclaimed objects.
        """
        grey_stack: List[GCObject] = []

        # Mark roots Grey
        for root in roots:
            if root is not None and root.gc_color == Color.WHITE:
                root.gc_color = Color.GREY
                grey_stack.append(root)

        # Process grey stack (marking phase)
        while grey_stack:
            obj = grey_stack.pop()
            obj.gc_color = Color.BLACK
            for child in obj.get_references():
                if child is not None and child.gc_color == Color.WHITE:
                    child.gc_color = Color.GREY
                    grey_stack.append(child)

        # Sweep phase
        current = self._head
        reclaimed_count = 0
        while current is not None:
            nxt = current._gc_next
            if current.gc_color == Color.BLACK:
                # Reset to White for the next cycle
                current.gc_color = Color.WHITE
                current = nxt
            elif current.gc_color == Color.WHITE:
                # Unreachable object: unlink and reclaim
                if current._gc_prev is not None:
                    current._gc_prev._gc_next = current._gc_next
                else:
                    self._head = current._gc_next
                
                if current._gc_next is not None:
                    current._gc_next._gc_prev = current._gc_prev
                
                current._gc_next = None
                current._gc_prev = None
                reclaimed_count += 1
                self._allocated_count -= 1
                current = nxt
            else:
                # Fallback safety reset
                current.gc_color = Color.WHITE
                current = nxt

        # Adjust threshold dynamically based on live objects
        self._threshold = max(1024, self._allocated_count * 2)
        return reclaimed_count


@dataclass(slots=True)
class CallFrame:
    """
    Isolates execution state, local registers, and instruction pointer.
    Enforces base-pointer and stack-pointer boundaries.
    """
    code: Tuple[BytecodeInstruction, ...]
    ip: int = 0
    registers: List[Any] = field(default_factory=lambda: [None] * 256)
    stack_base: int = 0
    stack_pointer: int = 0
    max_stack_size: int = 1024

    def __post_init__(self) -> None:
        if len(self.registers) != 256:
            raise ValueError("CallFrame requires a fixed-size register window of exactly 256 entries.")
        if self.max_stack_size <= 0:
            raise ValueError("CallFrame max_stack_size must be strictly positive.")

    def verify_register_bounds(self, reg_idx: int) -> None:
        """Validates that a register index falls within the active window [0, 255]."""
        if not (0 <= reg_idx < len(self.registers)):
            raise IndexError(f"Register index {reg_idx} out of bounds for frame window [0, 255].")

    def push_stack(self, value: Any, evaluation_stack: List[Any]) -> None:
        """Pushes a value onto the evaluation stack with strict boundary enforcement."""
        if (self.stack_pointer - self.stack_base) >= self.max_stack_size:
            raise OverflowError("CallFrame evaluation stack overflow detected.")
        evaluation_stack.append(value)
        self.stack_pointer += 1

    def pop_stack(self, evaluation_stack: List[Any]) -> Any:
        """Pops a value from the evaluation stack with strict boundary enforcement."""
        if self.stack_pointer <= 0 or len(evaluation_stack) <= self.stack_base:
            raise IndexError("CallFrame evaluation stack underflow detected.")
        self.stack_pointer -= 1
        return evaluation_stack.pop()


@dataclass(slots=True)
class VMThreadState:
    """Thread execution state containing evaluation stack, call stack, and global scope."""
    evaluation_stack: List[Any] = field(default_factory=list)
    call_stack: List[CallFrame] = field(default_factory=list)
    globals_table: Dict[str, Any] = field(default_factory=dict)
    heap: Heap = field(default_factory=Heap)

    def get_gc_roots(self) -> List[GCObject]:
        """Gathers all active GC roots across thread stacks, register windows, and globals."""
        roots: List[GCObject] = []

        # Evaluation stack roots
        for item in self.evaluation_stack:
            if isinstance(item, GCObject):
                roots.append(item)

        # Call frame register windows and frames
        for frame in self.call_stack:
            for reg in frame.registers:
                if isinstance(reg, GCObject):
                    roots.append(reg)

        # Global symbol table roots
        for val in self.globals_table.values():
            if isinstance(val, GCObject):
                roots.append(val)

        return roots

    def unwind_stack(self) -> None:
        """Systematically unwinds call stack frames, releasing pinned resources during panic recovery."""
        while self.call_stack:
            frame = self.call_stack.pop()
            # Clear register references to release pinned GC roots
            for i in range(len(frame.registers)):
                frame.registers[i] = None
        self.evaluation_stack.clear()