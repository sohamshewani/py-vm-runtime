# pyvm/parser.py
# Production-grade recursive descent parser for py-vm-runtime.
# Converts token streams or source strings into frozen AST nodes with __slots__.

from __future__ annotations

import sys
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Sequence, Union, Final


class TokenType(Enum):
    DEF = auto()
    RETURN = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    LET = auto()
    IDENTIFIER = auto()
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()
    ASSIGN = auto()
    PLUS = auto()
    MINUS = auto()
    MULTIPLY = auto()
    DIVIDE = auto()
    EQ = auto()
    NE = auto()
    LT = auto()
    LE = auto()
    GT = auto()
    GE = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    COMMA = auto()
    SEMICOLON = auto()
    EOF = auto()


@dataclass(frozen=True, slots=True)
class Token:
    __slots__ = ("type", "value", "line", "column")
    type: TokenType
    value: str
    line: int
    column: int


class ASTNode:
    __slots__ = ()


@dataclass(frozen=True, slots=True)
class Program(ASTNode):
    __slots__ = ("body",)
    body: Sequence[ASTNode]


@dataclass(frozen=True, slots=True)
class FunctionDecl(ASTNode):
    __slots__ = ("name", "params", "body")
    name: str
    params: Sequence[str]
    body: Sequence[ASTNode]


@dataclass(frozen=True, slots=True)
class LetStmt(ASTNode):
    __slots__ = ("name", "initializer")
    name: str
    initializer: ASTNode


@dataclass(frozen=True, slots=True)
class ReturnStmt(ASTNode):
    __slots__ = ("value",)
    value: Optional[ASTNode]


@dataclass(frozen=True, slots=True)
class IfStmt(ASTNode):
    __slots__ = ("condition", "then_branch", "else_branch")
    condition: ASTNode
    then_branch: Sequence[ASTNode]
    else_branch: Optional[Sequence[ASTNode]]


@dataclass(frozen=True, slots=True)
class WhileStmt(ASTNode):
    __slots__ = ("condition", "body")
    condition: ASTNode
    body: Sequence[ASTNode]


@dataclass(frozen=True, slots=True)
class ExprStmt(ASTNode):
    __slots__ = ("expression",)
    expression: ASTNode


@dataclass(frozen=True, slots=True)
class AssignExpr(ASTNode):
    __slots__ = ("name", "value")
    name: str
    value: ASTNode


@dataclass(frozen=True, slots=True)
class BinaryExpr(ASTNode):
    __slots__ = ("left", "operator", "right")
    left: ASTNode
    operator: str
    right: ASTNode


@dataclass(frozen=True, slots=True)
class CallExpr(ASTNode):
    __slots__ = ("callee", "arguments")
    callee: ASTNode
    arguments: Sequence[ASTNode]


@dataclass(frozen=True, slots=True)
class Identifier(ASTNode):
    __slots__ = ("name",)
    name: str


@dataclass(frozen=True, slots=True)
class IntegerLiteral(ASTNode):
    __slots__ = ("value",)
    value: int


@dataclass(frozen=True, slots=True)
class FloatLiteral(ASTNode):
    __slots__ = ("value",)
    value: float


@dataclass(frozen=True, slots=True)
class StringLiteral(ASTNode):
    __slots__ = ("value",)
    value: str


class ParserError(Exception):
    __slots__ = ("message", "line", "column")
    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(f"ParserError: {message} at line {line}, column {column}")
        self.message = message
        self.line = line
        self.column = column


class Lexer:
    __slots__ = ("source", "length", "index", "line", "column")

    KEYWORDS: Final = {
        "def": TokenType.DEF,
        "return": TokenType.RETURN,
        "if": TokenType.IF,
        "else": TokenType.ELSE,
        "while": TokenType.WHILE,
        "let": TokenType.LET,
    }

    def __init__(self, source: str) -> None:
        self.source = source
        self.length = len(source)
        self.index = 0
        self.line = 1
        self.column = 1

    def _peek(self) -> str:
        if self.index >= self.length:
            return "\0"
        return self.source[self.index]

    def _advance(self) -> str:
        ch = self._peek()
        self.index += 1
        if ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _match(self, expected: str) -> bool:
        if self.index >= self.length or self.source[self.index] != expected:
            return False
        self._advance()
        return True

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while self.index < self.length:
            ch = self._peek()
            if ch.isspace():
                self._advance()
                continue
            if ch.isalpha() or ch == "_":
                start_line = self.line
                start_col = self.column
                ident_val = []
                while self._peek().isalnum() or self._peek() == "_":
                    ident_val.append(self._advance())
                text = "".join(ident_val)
                ttype = self.KEYWORDS.get(text, TokenType.IDENTIFIER)
                tokens.append(Token(ttype, text, start_line, start_col))
                continue
            if ch.isdigit():
                start_line = self.line
                start_col = self.column
                num_val = []
                is_float = False
                while self._peek().isdigit() or (self._peek() == "." and not is_float):
                    if self._peek() == ".":
                        is_float = True
                    num_val.append(self._advance())
                text = "".join(num_val)
                if is_float:
                    tokens.append(Token(TokenType.FLOAT, text, start_line, start_col))
                else:
                    tokens.append(Token(TokenType.INTEGER, text, start_line, start_col))
                continue
            if ch == '"':
                start_line = self.line
                start_col = self.column
                self._advance()  # consume opening quote
                str_val = []
                while self._peek() != '"' and self._peek() != "\0":
                    str_val.append(self._advance())
                if self._peek() == "\0":
                    raise ParserError("Unterminated string literal", start_line, start_col)
                self._advance()  # consume closing quote
                tokens.append(Token(TokenType.STRING, "".join(str_val), start_line, start_col))
                continue

            start_line = self.line
            start_col = self.column
            if ch == "=":
                self._advance()
                if self._match("="):
                    tokens.append(Token(TokenType.EQ, "==", start_line, start_col))
                else:
                    tokens.append(Token(TokenType.ASSIGN, "=", start_line, start_col))
            elif ch == "!":
                self._advance()
                if self._match("="):
                    tokens.append(Token(TokenType.NE, "!=", start_line, start_col))
                else:
                    raise ParserError(f"Unexpected character '!'", start_line, start_col)
            elif ch == "<":
                self._advance()
                if self._match("="):
                    tokens.append(Token(TokenType.LE, "<=", start_line, start_col))
                else:
                    tokens.append(Token(TokenType.LT, "<", start_line, start_col))
            elif ch == ">":
                self._advance()
                if self._match("="):
                    tokens.append(Token(TokenType.GE, ">=", start_line, start_col))
                else:
                    tokens.append(Token(TokenType.GT, ">", start_line, start_col))
            elif ch == "+":
                self._advance()
                tokens.append(Token(TokenType.PLUS, "+", start_line, start_col))
            elif ch == "-":
                self._advance()
                tokens.append(Token(TokenType.MINUS, "-", start_line, start_col))
            elif ch == "*":
                self._advance()
                tokens.append(Token(TokenType.MULTIPLY, "*", start_line, start_col))
            elif ch == "/":
                self._advance()
                tokens.append(Token(TokenType.DIVIDE, "/", start_line, start_col))
            elif ch == "(":
                self._advance()
                tokens.append(Token(TokenType.LPAREN, "(", start_line, start_col))
            elif ch == ")":
                self._advance()
                tokens.append(Token(TokenType.RPAREN, ")", start_line, start_col))
            elif ch == "{":
                self._advance()
                tokens.append(Token(TokenType.LBRACE, "{", start_line, start_col))
            elif ch == "}":
                self._advance()
                tokens.append(Token(TokenType.RBRACE, "}", start_line, start_col))
            elif ch == ",":
                self._advance()
                tokens.append(Token(TokenType.COMMA, ",", start_line, start_col))
            elif ch == ";":
                self._advance()
                tokens.append(Token(TokenType.SEMICOLON, ";", start_line, start_col))
            else:
                raise ParserError(f"Unexpected character '{ch}'", start_line, start_col)

        tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        return tokens


class Parser:
    __slots__ = ("tokens", "pos", "length")

    def __init__(self, tokens: Sequence[Token]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.length = len(tokens)

    def _peek(self) -> Token:
        if self.pos >= self.length:
            return self.tokens[-1]
        return self.tokens[self.pos]

    def _previous(self) -> Token:
        return self.tokens[self.pos - 1]

    def _is_at_end(self) -> bool:
        return self._peek().type == TokenType.EOF

    def _advance(self) -> Token:
        if not self._is_at_end():
            self.pos += 1
        return self._previous()

    def _check(self, ttype: TokenType) -> bool:
        if self._is_at_end():
            return False
        return self._peek().type == ttype

    def _match(self, *types: TokenType) -> bool:
        for ttype in types:
            if self._check(ttype):
                self._advance()
                return True
        return False

    def _consume(self, ttype: TokenType, message: str) -> Token:
        if self._check(ttype):
            return self._advance()
        tok = self._peek()
        raise ParserError(message, tok.line, tok.column)

    def parse(self) -> Program:
        body: List[ASTNode] = []
        while not self._is_at_end():
            body.append(self._parse_declaration())
        return Program(body=body)

    def _parse_declaration(self) -> ASTNode:
        if self._match(TokenType.DEF):
            return self._parse_function_declaration()
        return self._parse_statement()

    def _parse_function_declaration(self) -> FunctionDecl:
        name_tok = self._consume(TokenType.IDENTIFIER, "Expect function name after 'def'.")
        self._consume(TokenType.LPAREN, "Expect '(' after function name.")
        params: List[str] = []
        if not self._check(TokenType.RPAREN):
            while True:
                param_tok = self._consume(TokenType.IDENTIFIER, "Expect parameter name.")
                params.append(param_tok.value)
                if not self._match(TokenType.COMMA):
                    break
        self._consume(TokenType.RPAREN, "Expect ')' after parameters.")
        self._consume(TokenType.LBRACE, "Expect '{' before function body.")
        body = self._parse_block()
        return FunctionDecl(name=name_tok.value, params=params, body=body)

    def _parse_block(self) -> List[ASTNode]:
        statements: List[ASTNode] = []
        while not self._check(TokenType.RBRACE) and not self._is_at_end():
            statements.append(self._parse_declaration())
        self._consume(TokenType.RBRACE, "Expect '}' after block.")
        return statements

    def _parse_statement(self) -> ASTNode:
        if self._match(TokenType.LET):
            return self._parse_let_statement()
        if self._match(TokenType.RETURN):
            return self._parse_return_statement()
        if self._match(TokenType.IF):
            return self._parse_if_statement()
        if self._match(TokenType.WHILE):
            return self._parse_while_statement()
        return self._parse_expression_statement()

    def _parse_let_statement(self) -> LetStmt:
        name_tok = self._consume(TokenType.IDENTIFIER, "Expect variable name after 'let'.")
        self._consume(TokenType.ASSIGN, "Expect '=' after variable name in 'let' statement.")
        initializer = self._parse_expression()
        self._match(TokenType.SEMICOLON)
        return LetStmt(name=name_tok.value, initializer=initializer)

    def _parse_return_statement(self) -> ReturnStmt:
        tok = self._previous()
        value: Optional[ASTNode] = None
        if not self._check(TokenType.SEMICOLON) and not self._check(TokenType.RBRACE):
            value = self._parse_expression()
        self._match(TokenType.SEMICOLON)
        return ReturnStmt(value=value)

    def _parse_if_statement(self) -> IfStmt:
        self._consume(TokenType.LPAREN, "Expect '(' after 'if'.")
        condition = self._parse_expression()
        self._consume(TokenType.RPAREN, "Expect ')' after if condition.")
        self._consume(TokenType.LBRACE, "Expect '{' before then branch.")
        then_branch = self._parse_block()
        else_branch: Optional[List[ASTNode]] = None
        if self._match(TokenType.ELSE):
            self._consume(TokenType.LBRACE, "Expect '{' before else branch.")
            else_branch = self._parse_block()
        return IfStmt(condition=condition, then_branch=then_branch, else_branch=else_branch)

    def _parse_while_statement(self) -> WhileStmt:
        self._consume(TokenType.LPAREN, "Expect '(' after 'while'.")
        condition = self._parse_expression()
        self._consume(TokenType.RPAREN, "Expect ')' after while condition.")
        self._consume(TokenType.LBRACE, "Expect '{' before while body.")
        body = self._parse_block()
        return WhileStmt(condition=condition, body=body)

    def _parse_expression_statement(self) -> ExprStmt:
        expr = self._parse_expression()
        self._match(TokenType.SEMICOLON)
        return ExprStmt(expression=expr)

    def _parse_expression(self) -> ASTNode:
        return self._parse_assignment()

    def _parse_assignment(self) -> ASTNode:
        expr = self._parse_equality()
        if self._match(TokenType.ASSIGN):
            equals