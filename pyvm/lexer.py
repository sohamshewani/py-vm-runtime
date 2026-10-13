# pyvm/lexer.py
# py-vm-runtime Production-Grade Lexer

from __future__ annotations

import sys
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Tuple, Dict, Final

@dataclass(frozen=True, slots=True)
class SourceLocation:
    line: int
    column: int
    filename: str

class TokenType(Enum):
    # Keywords
    KW_DEF = auto()
    KW_LET = auto()
    KW_MUT = auto()
    KW_IF = auto()
    KW_ELSE = auto()
    KW_WHILE = auto()
    KW_RETURN = auto()
    KW_CLASS = auto()
    KW_STRUCT = auto()
    KW_NONE = auto()
    KW_TRUE = auto()
    KW_FALSE = auto()
    
    # Identifiers & Literals
    IDENTIFIER = auto()
    INT_LITERAL = auto()
    FLOAT_LITERAL = auto()
    STRING_LITERAL = auto()
    
    # Operators
    OP_ASSIGN = auto()
    OP_PLUS = auto()
    OP_MINUS = auto()
    OP_MUL = auto()
    OP_DIV = auto()
    OP_MOD = auto()
    OP_EQ = auto()
    OP_NEQ = auto()
    OP_LT = auto()
    OP_LE = auto()
    OP_GT = auto()
    OP_GE = auto()
    OP_AND = auto()
    OP_OR = auto()
    OP_NOT = auto()
    OP_DOT = auto()
    
    # Delimiters
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    COLON = auto()
    SEMICOLON = auto()
    ARROW = auto()
    
    # Special
    EOF = auto()
    ERROR = auto()

@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    lexeme: str
    literal: Optional[object]
    location: SourceLocation

class LexicalError(Exception):
    def __init__(self, message: str, location: SourceLocation) -> None:
        super().__init__(f"LexicalError[{location.filename}:{location.line}:{location.column}]: {message}")
        self.message = message
        self.location = location

class Lexer:
    KEYWORDS: Final[Dict[str, TokenType]] = {
        "def": TokenType.KW_DEF,
        "let": TokenType.KW_LET,
        "mut": TokenType.KW_MUT,
        "if": TokenType.KW_IF,
        "else": TokenType.KW_ELSE,
        "while": TokenType.KW_WHILE,
        "return": TokenType.KW_RETURN,
        "class": TokenType.KW_CLASS,
        "struct": TokenType.KW_STRUCT,
        "None": TokenType.KW_NONE,
        "True": TokenType.KW_TRUE,
        "False": TokenType.KW_FALSE,
    }

    __slots__ = ("_source", "_filename", "_length", "_start", "_current", "_line", "_column")

    def __init__(self, source: str, filename: str = "<string>") -> None:
        self._source: str = source
        self._filename: str = filename
        self._length: int = len(source)
        self._start: int = 0
        self._current: int = 0
        self._line: int = 1
        self._column: int = 1

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while not self._is_at_end():
            self._start = self._current
            token = self._scan_token()
            if token is not None:
                tokens.append(token)
        
        tokens.append(Token(
            type=TokenType.EOF,
            lexeme="",
            literal=None,
            location=SourceLocation(self._line, self._column, self._filename)
        ))
        return tokens

    def _is_at_end(self) -> bool:
        return self._current >= self._length

    def _advance(self) -> str:
        if self._is_at_end():
            return '\0'
        char = self._source[self._current]
        self._current += 1
        if char == '\n':
            self._line += 1
            self._column = 1
        else:
            self._column += 1
        return char

    def _peek(self) -> str:
        if self._is_at_end():
            return '\0'
        return self._source[self._current]

    def _peek_next(self) -> str:
        if self._current + 1 >= self._length:
            return '\0'
        return self._source[self._current + 1]

    def _match(self, expected: str) -> bool:
        if self._is_at_end():
            return False
        if self._source[self._current] != expected:
            return False
        self._current += 1
        self._column += 1
        return True

    def _scan_token(self) -> Optional[Token]:
        start_line = self._line
        start_col = self._column
        char = self._advance()

        # Whitespace handling
        if char in (' ', '\r', '\t', '\n'):
            return None

        # Comments
        if char == '#' and self._peek() == '#':
            while self._peek() != '\n' and not self._is_at_end():
                self._advance()
            return None

        # Single-character tokens
        if char == '(': return self._make_token(TokenType.LPAREN, start_line, start_col)
        if char == ')': return self._make_token(TokenType.RPAREN, start_line, start_col)
        if char == '{': return self._make_token(TokenType.LBRACE, start_line, start_col)
        if char == '}': return self._make_token(TokenType.RBRACE, start_line, start_col)
        if char == '[': return self._make_token(TokenType.LBRACKET, start_line, start_col)
        if char == ']': return self._make_token(TokenType.RBRACKET, start_line, start_col)
        if char == ',': return self._make_token(TokenType.COMMA, start_line, start_col)
        if char == ':': return self._make_token(TokenType.COLON, start_line, start_col)
        if char == ';': return self._make_token(TokenType.SEMICOLON, start_line, start_col)
        if char == '.': return self._make_token(TokenType.OP_DOT, start_line, start_col)
        if char == '+': return self._make_token(TokenType.OP_PLUS, start_line, start_col)
        if char == '-':
            if self._match('>'):
                return self._make_token(TokenType.ARROW, start_line, start_col)
            return self._make_token(TokenType.OP_MINUS, start_line, start_col)
        if char == '*': return self._make_token(TokenType.OP_MUL, start_line, start_col)
        if char == '/': return self._make_token(TokenType.OP_DIV, start_line, start_col)
        if char == '%': return self._make_token(TokenType.OP_MOD, start_line, start_col)

        # Multi-character or conditional tokens
        if char == '=':
            if self._match('='):
                return self._make_token(TokenType.OP_EQ, start_line, start_col)
            return self._make_token(TokenType.OP_ASSIGN, start_line, start_col)
        
        if char == '!':
            if self._match('='):
                return self._make_token(TokenType.OP_NEQ, start_line, start_col)
            return self._make_token(TokenType.OP_NOT, start_line, start_col)

        if char == '<':
            if self._match('='):
                return self._make_token(TokenType.OP_LE, start_line, start_col)
            return self._make_token(TokenType.OP_LT, start_line, start_col)

        if char == '>':
            if self._match('='):
                return self._make_token(TokenType.OP_GE, start_line, start_col)
            return self._make_token(TokenType.OP_GT, start_line, start_col)

        # String literals
        if char == '"':
            return self._string()

        # Numeric literals
        if self._is_digit(char):
            return self._number(char)

        # Identifiers and Keywords
        if self._is_alpha(char):
            return self._identifier()

        loc = SourceLocation(start_line, start_col, self._filename)
        raise LexicalError(f"Unexpected character '{char}'", loc)

    def _make_token(self, token_type: TokenType, line: int, col: int, literal: Optional[object] = None) -> Token:
        lexeme = self._source[self._start:self._current]
        return Token(
            type=token_type,
            lexeme=lexeme,
            literal=literal,
            location=SourceLocation(line, col, self._filename)
        )

    def _string(self) -> Token:
        start_line = self._line
        start_col = self._column - 1
        value_chars: List[str] = []

        while self._peek() != '"' and not self._is_at_end():
            if self._peek() == '\\':
                self._advance()
                escape_char = self._advance()
                if escape_char == 'n': value_chars.append('\n')
                elif escape_char == 't': value_chars.append('\t')
                elif escape_char == 'r': value_chars.append('\r')
                elif escape_char == '\\': value_chars.append('\\')
                elif escape_char == '"': value_chars.append('"')
                else:
                    loc = SourceLocation(self._line, self._column, self._filename)
                    raise LexicalError(f"Invalid escape sequence '\\{escape_char}'", loc)
            else:
                value_chars.append(self._advance())

        if self._is_at_end():
            loc = SourceLocation(start_line, start_col, self._filename)
            raise LexicalError("Unterminated string literal", loc)

        # Consume closing quote
        self._advance()
        literal_value = "".join(value_chars)
        return self._make_token(TokenType.STRING_LITERAL, start_line, start_col, literal_value)

    def _number(self, first_char: str) -> Token:
        start_line = self._line
        start_col = self._column - 1
        is_float = False

        while self._is_digit(self._peek()):
            self._advance()

        if self._peek() == '.' and self._is_digit(self._peek_next()):
            is_float = True
            self._advance() # Consume '.'
            while self._is_digit(self._peek()):
                self._advance()

        lexeme = self._source[self._start:self._current]
        literal_value = float(lexeme) if is_float else int(lexeme)
        token_type = TokenType.FLOAT_LITERAL if is_float else TokenType.INT_LITERAL

        return self._make_token(token_type, start_line, start_col, literal_value)

    def _identifier(self) -> Token:
        start_line = self._line
        start_col = self._column - 1

        while self._is_alphanumeric(self._peek()):
            self._advance()

        lexeme = self._source[self._start:self._current]
        token_type = self.KEYWORDS.get(lexeme, TokenType.IDENTIFIER)
        return self._make_token(token_type, start_line, start_col)

    def _is_digit(self, char: str) -> bool:
        return '0' <= char <= '9'

    def _is_alpha(self, char: str) -> bool:
        return ('a' <= char <= 'z') or ('A' <= char <= 'Z') or (char == '_')

    def _is_alphanumeric(self, char: str) -> bool:
        return self._is_alpha(char) or self._is_digit(char)