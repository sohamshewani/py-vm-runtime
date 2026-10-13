from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from enum import IntEnum, auto

class Opcode(IntEnum):
    LOAD_CONST = 0x01
    LOAD_VAR = 0x02
    STORE_VAR = 0x03
    ADD = 0x04
    SUB = 0x05
    MUL = 0x06
    DIV = 0x07
    JUMP = 0x08
    JUMP_IF_FALSE = 0x09
    CALL = 0x0A
    RET = 0x0B
    ALLOC = 0x0C
    MOVE = 0x0D
    PRINT = 0x0E
    HALT = 0x0F

@dataclass(frozen=True, slots=True)
class ASTNode:
    pass

@dataclass(frozen=True, slots=True)
class LiteralNode(ASTNode):
    value: Any

@dataclass(frozen=True, slots=True)
class IdentifierNode(ASTNode):
    name: str

@dataclass(frozen=True, slots=True)
class BinaryOpNode(ASTNode):
    op: str
    left: ASTNode
    right: ASTNode

@dataclass(frozen=True, slots=True)
class AssignNode(ASTNode):
    name: str
    value: ASTNode

@dataclass(frozen=True, slots=True)
class IfNode(ASTNode):
    condition: ASTNode
    body: List[ASTNode]
    else_body: List[ASTNode]

@dataclass(frozen=True, slots=True)
class WhileNode(ASTNode):
    condition: ASTNode
    body: List[ASTNode]

@dataclass(frozen=True, slots=True)
class FunctionDefNode(ASTNode):
    name: str
    params: List[str]
    body: List[ASTNode]

@dataclass(frozen=True, slots=True)
class CallNode(ASTNode):
    callee: str
    args: List[ASTNode]

@dataclass(frozen=True, slots=True)
class ReturnNode(ASTNode):
    value: Optional[ASTNode]

@dataclass(frozen=True, slots=True)
class ProgramNode(ASTNode):
    body: List[ASTNode]

class CompilationError(Exception):
    def __init__(self, message: str, node: Optional[ASTNode] = None):
        super().__init__(message)
        self.node = node

class InstructionEncoder:
    @staticmethod
    def encode(opcode: Opcode, reg_dest: int, op1: int, op2: int) -> int:
        if not (0 <= opcode <= 0xFF):
            raise ValueError(f"Opcode out of bounds: {opcode}")
        if not (0 <= reg_dest <= 0xFF):
            raise ValueError(f"Register destination out of bounds: {reg_dest}")
        if not (0 <= op1 <= 0xFFFF):
            raise ValueError(f"Operand 1 out of bounds: {op1}")
        if not (0 <= op2 <= 0xFFFF):
            raise ValueError(f"Operand 2 out of bounds: {op2}")
        
        return (opcode << 56) | (reg_dest << 48) | (op1 << 32) | op2

    @staticmethod
    def decode(word: int) -> Tuple[int, int, int, int]:
        opcode = (word >> 56) & 0xFF
        reg_dest = (word >> 48) & 0xFF
        op1 = (word >> 32) & 0xFFFF
        op2 = word & 0xFFFF
        return opcode, reg_dest, op1, op2

class SymbolTable:
    def __init__(self, parent: Optional['SymbolTable'] = None):
        self.symbols: Dict[str, int] = {}
        self.parent: Optional['SymbolTable'] = parent
        self.next_index: int = 0

    def define(self, name: str) -> int:
        if name in self.symbols:
            return self.symbols[name]
        idx = self.next_index
        self.symbols[name] = idx
        self.next_index += 1
        return idx

    def resolve(self, name: str) -> Optional[int]:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent is not None:
            return self.parent.resolve(name)
        return None

class Compiler:
    def __init__(self):
        self.constants: List[Any] = []
        self.constants_map: Dict[Any, int] = {}
        self.instructions: List[int] = []
        self.current_scope: SymbolTable = SymbolTable()
        self.register_counter: int = 0
        self.max_registers: int = 256

    def _allocate_register(self) -> int:
        if self.register_counter >= self.max_registers:
            raise CompilationError("Register window overflow: exceeded 256 registers.")
        reg = self.register_counter
        self.register_counter += 1
        return reg

    def _free_register(self, count: int = 1) -> None:
        self.register_counter = max(0, self.register_counter - count)

    def _add_constant(self, value: Any) -> int:
        if value in self.constants_map:
            return self.constants_map[value]
        idx = len(self.constants)
        if idx > 0xFFFF:
            raise CompilationError("Constant pool overflow: exceeded 65535 constants.")
        self.constants.append(value)
        self.constants_map[value] = idx
        return idx

    def emit(self, opcode: Opcode, reg_dest: int, op1: int, op2: int) -> int:
        word = InstructionEncoder.encode(opcode, reg_dest, op1, op2)
        self.instructions.append(word)
        return len(self.instructions) - 1

    def patch(self, address: int, opcode: Opcode, reg_dest: int, op1: int, op2: int) -> None:
        word = InstructionEncoder.encode(opcode, reg_dest, op1, op2)
        if address < 0 or address >= len(self.instructions):
            raise CompilationError(f"Invalid bytecode address for patching: {address}")
        self.instructions[address] = word

    def compile(self, node: ASTNode) -> Dict[str, Any]:
        self.compile_node(node)
        self.emit(Opcode.HALT, 0, 0, 0)
        return {
            "constants": self.constants,
            "instructions": self.instructions,
            "max_registers": self.max_registers
        }

    def compile_node(self, node: ASTNode) -> int:
        if isinstance(node, ProgramNode):
            for stmt in node.body:
                self.compile_node(stmt)
            return 0
        elif isinstance(node, LiteralNode):
            const_idx = self._add_constant(node.value)
            dest_reg = self._allocate_register()
            self.emit(Opcode.LOAD_CONST, dest_reg, const_idx, 0)
            return dest_reg
        elif isinstance(node, IdentifierNode):
            var_idx = self.current_scope.resolve(node.name)
            if var_idx is None:
                raise CompilationError(f"Undefined variable '{node.name}'", node)
            dest_reg = self._allocate_register()
            self.emit(Opcode.LOAD_VAR, dest_reg, var_idx, 0)
            return dest_reg
        elif isinstance(node, BinaryOpNode):
            left_reg = self.compile_node(node.left)
            right_reg = self.compile_node(node.right)
            dest_reg = self._allocate_register()
            
            op_map = {
                "+": Opcode.ADD,
                "-": Opcode.SUB,
                "*": Opcode.MUL,
                "/": Opcode.DIV
            }
            if node.op not in op_map:
                raise CompilationError(f"Unknown binary operator '{node.op}'", node)
            
            self.emit(op_map[node.op], dest_reg, left_reg, right_reg)
            self._free_register(2)
            return dest_reg
        elif isinstance(node, AssignNode):
            val_reg = self.compile_node(node.value)
            var_idx = self.current_scope.define(node.name)
            self.emit(Opcode.STORE_VAR, val_reg, var_idx, 0)
            self._free_register(1)
            return val_reg
        elif isinstance(node, IfNode):
            cond_reg = self.compile_node(node.condition)
            jump_false_addr = self.emit(Opcode.JUMP_IF_FALSE, cond_reg, 0, 0)
            self._free_register(1)
            
            for stmt in node.body:
                self.compile_node(stmt)
                
            jump_end_addr = self.emit(Opcode.JUMP, 0, 0, 0)
            else_addr = len(self.instructions)
            
            self.patch(jump_false_addr, Opcode.JUMP_IF_FALSE, cond_reg, else_addr, 0)
            
            for stmt in node.else_body:
                self.compile_node(stmt)
                
            end_addr = len(self.instructions)
            self.patch(jump_end_addr, Opcode.JUMP, 0, end_addr, 0)
            return 0
        elif isinstance(node, WhileNode):
            loop_start = len(self.instructions)
            cond_reg = self.compile_node(node.condition)
            jump_false_addr = self.emit(Opcode.JUMP_IF_FALSE, cond_reg, 0, 0)
            self._free_register(1)
            
            for stmt in node.body:
                self.compile_node(stmt)
                
            self.emit(Opcode.JUMP, 0, loop_start, 0)
            loop_end = len(self.instructions)
            self.patch(jump_false_addr, Opcode.JUMP_IF_FALSE, cond_reg, loop_end, 0)
            return 0
        elif isinstance(node, FunctionDefNode):
            func_const_idx = self._add_constant(node.name)
            dest_reg = self._allocate_register()
            self.emit(Opcode.ALLOC, dest_reg, func_const_idx, 0)
            return dest_reg
        elif isinstance(node, CallNode):
            callee_const = self._add_constant(node.callee)
            callee_reg = self._allocate_register()
            self.emit(Opcode.LOAD_CONST, callee_reg, callee_const, 0)
            
            arg_regs = []
            for arg in node.args:
                r = self.compile_node(arg)
                arg_regs.append(r)
                
            dest_reg = self._allocate_register()
            self.emit(Opcode.CALL, dest_reg, callee_reg, len(arg_regs))
            self._free_register(len(arg_regs) + 1)
            return dest_reg
        elif isinstance(node, ReturnNode):
            if node.value is not None:
                val_reg = self.compile_node(node.value)
                self.emit(Opcode.RET, val_reg, 0, 0)
                self._free_register(1)
            else:
                self.emit(Opcode.RET, 0, 0, 0)
            return 0
        else:
            raise CompilationError(f"Unsupported AST node type: {type(node).__name__}", node)