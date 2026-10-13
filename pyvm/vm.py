from __future__ annotations

import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import Any, Dict, List, Optional, Set, Tuple, Union

class Opcode(IntEnum):
    NOP = 0
    LOAD_CONST = 1
    LOAD_FAST = 2
    STORE_FAST = 3
    ADD = 4
    SUB = 5
    MUL = 6
    DIV = 7
    COMPARE_EQ = 8
    COMPARE_LT = 9
    JUMP = 10
    JUMP_IF_FALSE = 11
    CALL = 12
    RETURN = 13
    ALLOC = 14
    HALT = 15

@dataclass(frozen=True, slots=True)
class Instruction:
    opcode: Opcode
    rd: int
    op1: int
    op2: int

    def encode(self) -> int:
        return (
            (int(self.opcode) & 0xFF) << 56
            | (self.rd & 0xFF) << 48
            | (self.op1 & 0xFFFF) << 32
            | (self.op2 & 0xFFFF)
        )

    @classmethod
    def decode(cls, word: int) -> Instruction:
        opcode_val = (word >> 56) & 0xFF
        rd = (word >> 48) & 0xFF
        op1 = (word >> 32) & 0xFFFF
        op2 = word & 0xFFFF
        return cls(Opcode(opcode_val), rd, op1, op2)

class GCColor(IntEnum):
    WHITE = 0
    GREY = 1
    BLACK = 2

class VMObject(ABC):
    __slots__ = ('_gc_color', '_gc_next', '_gc_prev')

    def __init__(self) -> None:
        self._gc_color: GCColor = GCColor.WHITE
        self._gc_next: Optional[VMObject] = None
        self._gc_prev: Optional[VMObject] = None

    @abstractmethod
    def get_references(self) -> List[VMObject]:
        pass

class VMHeapObject(VMObject):
    __slots__ = ('fields',)

    def __init__(self, initial_fields: Optional[Dict[str, VMObject]] = None) -> None:
        super().__init__()
        self.fields: Dict[str, VMObject] = initial_fields if initial_fields is not None else {}

    def get_references(self) -> List[VMObject]:
        return list(self.fields.values())

class GarbageCollector:
    __slots__ = ('threshold', 'bytes_allocated', 'head', 'allocation_count')

    def __init__(self, threshold: int = 1024) -> None:
        self.threshold: int = threshold
        self.bytes_allocated: int = 0
        self.head: Optional[VMObject] = None
        self.allocation_count: int = 0

    def register_allocation(self, obj: VMObject) -> None:
        obj._gc_color = GCColor.WHITE
        obj._gc_next = self.head
        obj._gc_prev = None
        if self.head is not None:
            self.head._gc_prev = obj
        self.head = obj
        self.allocation_count += 1
        self.bytes_allocated += 1
        if self.allocation_count >= self.threshold:
            self.collect(set())

    def collect(self, roots: Set[VMObject]) -> int:
        grey_set: List[VMObject] = []

        for root in roots:
            if root is not None and root._gc_color == GCColor.WHITE:
                root._gc_color = GCColor.GREY
                grey_set.append(root)

        while len(grey_set) > 0:
            obj = grey_set.pop()
            obj._gc_color = GCColor.BLACK
            for ref in obj.get_references():
                if ref is not None and ref._gc_color == GCColor.WHITE:
                    ref._gc_color = GCColor.GREY
                    grey_set.append(ref)

        current = self.head
        collected_count = 0
        while current is not None:
            next_node = current._gc_next
            if current._gc_color == GCColor.BLACK:
                current._gc_color = GCColor.WHITE
            else:
                if current._gc_prev is not None:
                    current._gc_prev._gc_next = current._gc_next
                else:
                    self.head = current._gc_next
                if current._gc_next is not None:
                    current._gc_next._gc_prev = current._gc_prev
                current._gc_next = None
                current._gc_prev = None
                collected_count += 1
                self.bytes_allocated -= 1
            current = next_node

        self.allocation_count = 0
        return collected_count

class CallFrame:
    __slots__ = ('code', 'ip', 'registers', 'stack', 'base_pointer', 'stack_pointer', 'globals_table')

    def __init__(self, code: List[Instruction], register_count: int, globals_table: Dict[str, Any]) -> None:
        if register_count <= 0 or register_count > 256:
            raise ValueError(f"Invalid register count: {register_count}")
        self.code: List[Instruction] = code
        self.ip: int = 0
        self.registers: List[Any] = [None] * register_count
        self.stack: List[Any] = []
        self.base_pointer: int = 0
        self.stack_pointer: int = 0
        self.globals_table: Dict[str, Any] = globals_table

    def push(self, value: Any) -> None:
        self.stack.append(value)
        self.stack_pointer += 1

    def pop(self) -> Any:
        if self.stack_pointer <= self.base_pointer:
            raise IndexError("Stack underflow in CallFrame")
        self.stack_pointer -= 1
        return self.stack.pop()

    def get_register(self, idx: int) -> Any:
        if idx < 0 or idx >= len(self.registers):
            raise IndexError(f"Register index out of bounds: {idx}")
        return self.registers[idx]

    def set_register(self, idx: int, value: Any) -> int:
        if idx < 0 or idx >= len(self.registers):
            raise IndexError(f"Register index out of bounds: {idx}")
        self.registers[idx] = value
        return idx

class VMError(Exception):
    pass

class TypeError(VMError):
    pass

class StackOverflowError(VMError):
    pass

class VM:
    __slots__ = ('constants', 'globals_table', 'call_stack', 'heap', 'max_call_stack_depth', 'running')

    def __init__(self, constants: List[Any], globals_table: Optional[Dict[str, Any]] = None, max_call_stack_depth: int = 1024) -> None:
        self.constants: List[Any] = constants
        self.globals_table: Dict[str, Any] = globals_table if globals_table is not None else {}
        self.call_stack: List[CallFrame] = []
        self.heap: GarbageCollector = GarbageCollector()
        self.max_call_stack_depth: int = max_call_stack_depth
        self.running: bool = False

    def collect_roots(self) -> Set[VMObject]:
        roots: Set[VMObject] = set()
        for frame in self.call_stack:
            for reg in frame.registers:
                if isinstance(reg, VMObject):
                    roots.add(reg)
            for stk in frame.stack:
                if isinstance(stk, VMObject):
                    roots.add(stk)
        for val in self.globals_table.values():
            if isinstance(val, VMObject):
                roots.add(val)
        return roots

    def execute(self, code: List[Instruction], register_count: int = 16) -> Any:
        initial_frame = CallFrame(code, register_count, self.globals_table)
        self.call_stack.append(initial_frame)
        self.running = True
        return_value: Any = None

        try:
            while self.running and len(self.call_stack) > 0:
                frame = self.call_stack[-1]
                if frame.ip < 0 or frame.ip >= len(frame.code):
                    raise VMError(f"Instruction pointer out of bounds: {frame.ip}")

                instr = frame.code[frame.ip]
                frame.ip += 1

                opcode = instr.opcode
                rd = instr.rd
                op1 = instr.op1
                op2 = instr.op2

                if opcode == Opcode.NOP:
                    pass

                elif opcode == Opcode.LOAD_CONST:
                    if op1 < 0 or op1 >= len(self.constants):
                        raise VMError(f"Constant index out of bounds: {op1}")
                    val = self.constants[op1]
                    frame.set_register(rd, val)

                elif opcode == Opcode.LOAD_FAST:
                    val = frame.get_register(op1)
                    frame.set_register(rd, val)

                elif opcode == Opcode.STORE_FAST:
                    val = frame.get_register(rd)
                    frame.set_register(op1, val)

                elif opcode == Opcode.ADD:
                    left = frame.get_register(op1)
                    right = frame.get_register(op2)
                    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                        raise TypeError(f"Type error in ADD: {type(left)} and {type(right)}")
                    res = left + right
                    frame.set_register(rd, res)

                elif opcode == Opcode.SUB:
                    left = frame.get_register(op1)
                    right = frame.get_register(op2)
                    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                        raise TypeError(f"Type error in SUB: {type(left)} and {type(right)}")
                    res = left - right
                    frame.set_register(rd, res)

                elif opcode == Opcode.MUL:
                    left = frame.get_register(op1)
                    right = frame.get_register(op2)
                    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                        raise TypeError(f"Type error in MUL: {type(left)} and {type(right)}")
                    res = left * right
                    frame.set_register(rd, res)

                elif opcode == Opcode.DIV:
                    left = frame.get_register(op1)
                    right = frame.get_register(op2)
                    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                        raise TypeError(f"Type error in DIV: {type(left)} and {type(right)}")
                    if right == 0:
                        raise ZeroDivisionError("Division by zero")
                    res = left / right
                    frame.set_register(rd, res)

                elif opcode == Opcode.COMPARE_EQ:
                    left = frame.get_register(op1)
                    right = frame.get_register(op2)
                    res = 1 if left == right else 0
                    frame.set_register(rd, res)

                elif opcode == Opcode.COMPARE_LT:
                    left = frame.get_register(op1)
                    right = frame.get_register(op2)
                    res = 1 if left < right else 0
                    frame.set_register(rd, res)

                elif opcode == Opcode.JUMP:
                    target = (op1 << 16) | op2
                    if target < 0 or target >= len(frame.code):
                        raise VMError(f"Jump target out of bounds: {target}")
                    frame.ip = target

                elif opcode == Opcode.JUMP_IF_FALSE:
                    cond = frame.get_register(rd)
                    target = (op1 << 16) | op2
                    if not cond:
                        if target < 0 or target >= len(frame.code):
                            raise VMError(f"Jump target out of bounds: {target}")
                        frame.ip = target

                elif opcode == Opcode.ALLOC:
                    obj = VMHeapObject()
                    self.heap.register_allocation(obj)
                    frame.set_register(rd, obj)
                    if self.heap.allocation_count >= self.heap.threshold:
                        roots = self.collect_roots()
                        self.heap.collect(roots)

                elif opcode == Opcode.CALL:
                    if len(self.call_stack) >= self.max_call_stack_depth:
                        raise StackOverflowError("Maximum call stack depth exceeded")
                    callee_code = self.constants[op1]
                    if not isinstance(callee_code, list):
                        raise TypeError("Callee code must be a list of Instructions")
                    new_frame = CallFrame(callee_code, op2, self.globals_table)
                    for i in range(min(op2, len(frame.registers))):
                        new_frame.set_register(i, frame.get_register(i))
                    self.call_stack.append(new_frame)

                elif opcode == Opcode.RETURN:
                    return_value = frame.get_register(rd)
                    self.call_stack.pop()
                    if len(self.call_stack) == 0:
                        self.running = False

                elif opcode == Opcode.HALT:
                    self.running = False
                    return_value = frame.get_register(rd)

                else:
                    raise VMError(f"Unknown opcode: {opcode}")

        except Exception as e:
            self.call_stack.clear()
            self.running = False
            raise e

        return return_value