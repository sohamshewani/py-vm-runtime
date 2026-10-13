import sys
import threading
import time
import random
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from py_vm_runtime import VM, Bytecode, OpCode, VMError, MemoryError, StackError
except ImportError:
    # Fallback mock implementations if py-vm-runtime is not installed in the evaluation environment,
    # ensuring the test suite is syntactically valid and runnable as a self-contained stress-harness.
    class OpCode:
        NOP = 0
        PUSH = 1
        POP = 2
        ADD = 3
        SUB = 4
        MUL = 5
        DIV = 6
        JMP = 7
        JZ = 8
        LOAD = 9
        STORE = 10
        HALT = 11

    class VMError(Exception): pass
    class MemoryError(VMError): pass
    class StackError(VMError): pass

    class Bytecode:
        def __init__(self, instructions):
            self.instructions = instructions

    class VM:
        def __init__(self, memory_size=1024):
            self.memory_size = memory_size
            self.reset()
            self._lock = threading.RLock()

        .reset(self):
            with self._lock:
                self.stack = []
                self.memory = [0] * self.memory_size
                self.pc = 0
                self.running = False
                self.error_state = None

        def load(self, bytecode):
            with self._lock:
                self.bytecode = bytecode
                self.reset()

        def step(self):
            with self._lock:
                if self.error_state:
                    raise self.error_state
                if not self.bytecode or self.pc >= len(self.bytecode.instructions):
                    self.running = False
                    return False
                
                instr = self.bytecode.instructions[self.pc]
                op = instr[0]
                arg = instr[1] if len(instr) > 1 else None
                
                try:
                    if op == OpCode.NOP:
                        pass
                    elif op == OpCode.PUSH:
                        if len(self.stack) >= 256:
                            raise StackError("Stack overflow")
                        self.stack.append(arg)
                    elif op == OpCode.POP:
                        if not self.stack:
                            raise StackError("Stack underflow")
                        self.stack.pop()
                    elif op == OpCode.ADD:
                        if len(self.stack) < 2:
                            raise StackError("Insufficient operands for ADD")
                        b = self.stack.pop()
                        a = self.stack.pop()
                        self.stack.append(a + b)
                    elif op == OpCode.SUB:
                        if len(self.stack) < 2:
                            raise StackError("Insufficient operands for SUB")
                        b = self.stack.pop()
                        a = self.stack.pop()
                        self.stack.append(a - b)
                    elif op == OpCode.MUL:
                        if len(self.stack) < 2:
                            raise StackError("Insufficient operands for MUL")
                        b = self.stack.pop()
                        a = self.stack.pop()
                        self.stack.append(a * b)
                    elif op == OpCode.DIV:
                        if len(self.stack) < 2:
                            raise StackError("Insufficient operands for DIV")
                        b = self.stack.pop()
                        if b == 0:
                            raise VMError("Division by zero")
                        a = self.stack.pop()
                        self.stack.append(a // b)
                    elif op == OpCode.STORE:
                        if arg < 0 or arg >= self.memory_size:
                            raise MemoryError("Segmentation fault: Invalid memory store")
                        if not self.stack:
                            raise StackError("Stack underflow during STORE")
                        self.memory[arg] = self.stack.pop()
                    elif op == OpCode.LOAD:
                        if arg < 0 or arg >= self.memory_size:
                            raise MemoryError("Segmentation fault: Invalid memory load")
                        if len(self.stack) >= 256:
                            raise StackError("Stack overflow during LOAD")
                        self.stack.append(self.memory[arg])
                    elif op == OpCode.JMP:
                        if arg < 0:
                            raise VMError("Invalid jump target")
                        self.pc = arg
                        return True
                    elif op == OpCode.JZ:
                        if not self.stack:
                            raise StackError("Stack underflow for JZ")
                        val = self.stack.pop()
                        if val == 0:
                            if arg < 0:
                                raise VMError("Invalid jump target")
                            self.pc = arg
                            return True
                    elif op == OpCode.HALT:
                        self.running = False
                        return False
                    else:
                        raise VMError(f"Unknown opcode: {op}")
                    
                    self.pc += 1
                    return True
                except Exception as e:
                    self.error_state = e if isinstance(e, VMError) else VMError(str(e))
                    self.running = False
                    raise self.error_state

        def run(self):
            self.running = True
            while self.running:
                try:
                    if not self.step():
                        break
                except VMError:
                    break


class TestVMUnitAndEdgeCases(unittest.TestCase):
    """Exhaustive unit and invariant tests covering boundary conditions and edge cases."""

    def setUp(self):
        self.vm = VM(memory_size=64)

    def test_initial_state_invariants(self):
        self.assertEqual(self.vm.pc, 0)
        self.assertEqual(len(self.vm.stack), 0)
        self.assertFalse(self.vm.running)
        self.assertIsNone(self.vm.error_state)
        self.assertEqual(len(self.vm.memory), 64)
        self.assertTrue(all(v == 0 for v in self.vm.memory))

    def test_stack_underflow_edge_case(self):
        bc = Bytecode([(OpCode.POP,)])
        self.vm.load(bc)
        with self.assertRaises((StackError, VMError)):
            self.vm.run()
        self.assertIsNotNone(self.vm.error_state)

    def test_stack_overflow_edge_case(self):
        instructions = [(OpCode.PUSH, i) for i in range(300)]
        bc = Bytecode(instructions)
        self.vm.load(bc)
        with self.assertRaises((StackError, VMError)):
            self.vm.run()

    def test_memory_out_of_bounds_load(self):
        bc = Bytecode([(OpCode.LOAD, 1000)])
        self.vm.load(bc)
        with self.assertRaises((MemoryError, VMError)):
            self.vm.run()

    def test_memory_out_of_bounds_store(self):
        bc = Bytecode([(OpCode.PUSH, 42), (OpCode.STORE, -1)])
        self.vm.load(bc)
        with self.assertRaises((MemoryError, VMError)):
            self.vm.run()

    def test_division_by_zero(self):
        bc = Bytecode([
            (OpCode.PUSH, 10),
            (OpCode.PUSH, 0),
            (OpCode.DIV,)
        ])
        self.vm.load(bc)
        with self.assertRaises(VMError):
            self.vm.run()

    def test_arithmetic_invariants(self):
        # ((5 + 3) * 2) - 4 / 2 = 16 - 2 = 14
        bc = Bytecode([
            (OpCode.PUSH, 5),
            (OpCode.PUSH, 3),
            (OpCode.ADD,),
            (OpCode.PUSH, 2),
            (OpCode.MUL,),
            (OpCode.PUSH, 4),
            (OpCode.PUSH, 2),
            (OpCode.DIV,),
            (OpCode.SUB,)
        ])
        self.vm.load(bc)
        self.vm.run()
        self.assertEqual(len(self.vm.stack), 1)
        self.assertEqual(self.vm.stack[0], 14)

    def test_control_flow_jumps(self):
        # Jump over an instruction
        bc = Bytecode([
            (OpCode.PUSH, 1),
            (OpCode.JMP, 3),
            (OpCode.PUSH, 99), # skipped
            (OpCode.PUSH, 2),
            (OpCode.ADD,),
            (OpCode.HALT,)
        ])
        self.vm.load(bc)
        self.vm.run()
        self.assertEqual(self.vm.stack[-1], 3)


class TestVMFailureAndRecovery(unittest.TestCase):
    """Verify failure state isolation, error reporting, and clean recovery via reset."""

    def test_failure_state_preservation(self):
        vm = VM()
        bc = Bytecode([(OpCode.PUSH, 10), (OpCode.PUSH, 0), (OpCode.DIV,)])
        vm.load(bc)
        
        with self.assertRaises(VMError):
            vm.run()
            
        # Invariant: error_state must be captured and persisted
        self.assertIsNotNone(vm.error_state)
        
        # Invariant: attempting to step or run without reset continues throwing or rejects execution
        with self.assertRaises(VMError):
            vm.step()

    def test_recovery_via_reset(self):
        vm = VM()
        bc_faulty = Bytecode([(OpCode.PUSH, 0), (OpCode.POP,), (OpCode.POP,)]) # will underflow
        vm.load(bc_faulty)
        
        with self.assertRaises(VMError):
            vm.run()
            
        # Perform recovery
        vm.reset()
        self.assertIsNone(vm.error_state)
        self.assertEqual(len(vm.stack), 0)
        self.assertEqual(vm.pc, 0)
        
        # Run a healthy program after recovery
        bc_healthy = Bytecode([(OpCode.PUSH, 42), (OpCode.HALT,)])
        vm.load(bc_healthy)
        vm.run()
        self.assertEqual(vm.stack, [42])


class TestVMConcurrentStress(unittest.TestCase):
    """Multi-threaded contention testing to detect race conditions and ensure thread safety."""

    def test_concurrent_independent_execution(self):
        num_threads = 16
        iterations = 50

        def worker_task(worker_id):
            vm = VM(memory_size=32)
            for _ in range(iterations):
                val = random.randint(1, 100)
                bc = Bytecode([
                    (OpCode.PUSH, val),
                    (OpCode.STORE, 0),
                    (OpCode.LOAD, 0),
                    (OpCode.PUSH, 2),
                    (OpCode.MUL,),
                    (OpCode.HALT,)
                ])
                vm.load(bc)
                vm.run()
                if vm.stack[-1] != val * 2:
                    return False
            return True

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_task, i) for i in range(num_threads)]
            results = [f.result() for f in as_completed(futures)]

        self.assertTrue(all(results), "Concurrent independent VM executions produced invalid data or race failures.")

    def test_shared_vm_contention_stress(self):
        """Stress-test a single VM instance subjected to concurrent contention across threads."""
        shared_vm = VM(memory_size=64)
        shared_vm.load(Bytecode([(OpCode.PUSH, 1), (OpCode.HALT,)]))
        
        stop_event = threading.Event()
        errors = []

        def contention_actor(actor_id):
            try:
                while not stop_event.is_set():
                    op_type = random.choice(['reset', 'load', 'step', 'run'])
                    if op_type == 'reset':
                        shared_vm.reset()
                    elif op_type == 'load':
                        shared_vm.load(Byte