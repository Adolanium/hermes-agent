"""Grammar-aware masking for credential-store content (``.netrc`` / ``_netrc``, ``.pgpass``, INI
stores such as ``.pypirc`` / ``~/.aws/credentials`` / ``~/.aws/config`` / ``.npmrc``,
``.git-credentials``).

A stored credential is owned by its file grammar, not by a regex token: a netrc password is a
lexer token (quoted, backslash-escaped, or on the line after ``password``) and an INI password
runs to end of line plus any more-indented continuation lines. The text reaching the redactor
is often a SLICE of the file (a read_file page, one search_files match, ``tail`` output), so a
value can arrive without the keyword that introduces it. Unless the text is known to start at
the top of the file, every parser here therefore starts in an unknown state and masks whatever
it cannot prove public: an orphan netrc token, a leading indented INI line, a pgpass line
without its four host fields.

That catch-all is only sound while the text is nothing BUT store content. Terminal output of
``cat ~/.netrc app.py`` or ``grep -rn X ~/.netrc src`` also carries other files, whose lines are
indistinguishable from orphan tokens, so ``extent="mixed"`` drops every catch-all and masks only
values the grammar ties to a keyword or a field layout.
"""

import re
from typing import Callable, Iterable, Literal

Mask = Callable[[str], str]
SecretOption = Callable[[str, str], bool]  # (option name, first value line) -> is it a secret
# "start": the text begins at the top of the store; "slice": a contiguous part of the store
# that may begin anywhere; "mixed": store content alongside other output.
Extent = Literal["start", "slice", "mixed"]
Span = tuple[int, int, str]  # (start, end, replacement) in the original text

# ``cat -n`` / read_file gutter: only trusted when EVERY line carries one and the numbers are
# consecutive, because a lone digit prefix on a netrc line may be password bytes.
_GUTTER_RE = re.compile(r"[ \t]*(\d+)[|\t]")
# Any rendered line-number prefix (read_file ``5|``, grep ``6:`` / ``7-``, ``cat -n``). Used by
# the line-atomic grammars as a SECOND reading of each line, unioned with the raw reading.
_LOOSE_GUTTER_RE = re.compile(r"[ \t]*\d+(?:[|:\-]|\t)")
_URL_USERINFO_PASSWORD_RE = re.compile(r"://[^:/\s@]*:([^@\s]+)@")
# An option name as a store spells it (``index-servers``, ``//registry.npmjs.org/:_authToken``,
# ``@scope:registry``); in mixed output this keeps source lines like ``def f(token: str):`` out.
_OPTION_NAME_RE = re.compile(r"[\w.\-/@:]+")
_PGPASS_PORT_RE = re.compile(r"\d+|\*")
# Mixed output is often multi-file grep: ``/home/u/.netrc:3:password hunter2``. The line-atomic
# grammars get a third reading past such a ``path:N:`` prefix; netrc accepts a keyword glued to it.
_GREP_PREFIX_RE = re.compile(r"\S*?[:\-]\d+[:\-]")
_PREFIXED_NETRC_KEYWORD_RE = re.compile(r".*[:\-|](machine|default|login|user|account|password|macdef)")

_NETRC_WS = " \t\r\n"
_NETRC_KEYWORDS = frozenset({"machine", "default", "login", "user", "account", "password", "macdef"})
_NETRC_PUBLIC_FOLLOWERS = frozenset({"machine", "login", "user", "macdef"})
_NETRC_SECRET_FOLLOWERS = frozenset({"password", "account"})


def _line_spans(text: str) -> list[tuple[int, int]]:
    spans, pos = [], 0
    for line in text.split("\n"):
        spans.append((pos, pos + len(line)))
        pos += len(line) + 1
    return spans


def _trusted_gutter(text: str) -> tuple[list[tuple[int, int]], int] | None:
    """Per-line ``(start, end)`` past a trusted gutter plus its first line number, or None
    when there is none."""
    spans = _line_spans(text)
    checked = spans[:-1] if len(spans) > 1 and spans[-1][0] == spans[-1][1] else spans
    gutters = [_GUTTER_RE.match(text, start, end) for start, end in checked]
    if not all(gutters):
        return None
    first = int(gutters[0].group(1))
    if any(int(g.group(1)) != first + i for i, g in enumerate(gutters)):
        return None
    return [(g.end(), end) for g, (_, end) in zip(gutters, checked)] + spans[len(checked):], first


def _prefixed_bodies(text: str, prefix_re: re.Pattern) -> list[tuple[int, int]]:
    out = []
    for start, end in _line_spans(text):
        g = prefix_re.match(text, start, end)
        out.append((g.end() if g else start, end))
    return out


class _NetrcLexer:
    """CPython ``netrc._netrclex`` over the line bodies, reporting each token's original spans."""

    def __init__(self, text: str, bodies: list[tuple[int, int]], *, quotes_span_lines: bool):
        self.text = text
        self.bodies = bodies
        self.quotes_span_lines = quotes_span_lines
        self.line = 0
        self.pos = bodies[0][0] if bodies else 0

    def _char(self) -> tuple[str, int]:
        """Next char and its original index (-1 for the virtual newline between bodies)."""
        while self.line < len(self.bodies):
            _, end = self.bodies[self.line]
            if self.pos < end:
                self.pos += 1
                return self.text[self.pos - 1], self.pos - 1
            self.line += 1
            if self.line < len(self.bodies):
                self.pos = self.bodies[self.line][0]
                return "\n", -1
        return "", -1

    def token(self) -> tuple[str, list[int], int] | None:
        """``(value, original char indices, starting line)`` or None at end of text."""
        ch, idx = self._char()
        while ch and ch in _NETRC_WS:
            ch, idx = self._char()
        if not ch:
            return None
        line, value, indices = self.line, "", [idx]
        if ch == '"':
            while True:
                ch, idx = self._char()
                indices.append(idx)
                if not ch or ch == '"' or (idx < 0 and not self.quotes_span_lines):
                    return value, indices, line
                if ch == "\\":
                    ch, idx = self._char()
                    indices.append(idx)
                value += ch
        while True:
            if ch == "\\":
                ch, idx = self._char()
                indices.append(idx)
            value += ch
            ch, idx = self._char()
            if not ch or ch in _NETRC_WS:
                return value, indices, line
            indices.append(idx)

    def skip_rest_of_line(self) -> None:
        if self.line < len(self.bodies):
            self.pos = self.bodies[self.line][1]

    def at_blank_line(self) -> bool:
        start, end = self.bodies[self.line]
        return not self.text[start:end].strip("\r")

    def next_line(self) -> bool:
        self.line += 1
        if self.line >= len(self.bodies):
            return False
        self.pos = self.bodies[self.line][0]
        return True


def _index_runs(indices: Iterable[int]) -> list[tuple[int, int]]:
    """Contiguous original-index runs of a token (a quoted token may span lines)."""
    runs: list[list[int]] = []
    for i in indices:
        if i < 0:
            continue
        if runs and i == runs[-1][1]:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1])
    return [(a, b) for a, b in runs]


def _netrc_spans(text: str, mask: Mask, extent: Extent) -> list[Span]:
    """Mask password/account values; outside mixed output also every token that is not
    provably a keyword or a machine/login/macdef name, since an orphan at the start of a slice
    is a value whose keyword was cut off. Comments and macro bodies stay intact."""
    trusted = _trusted_gutter(text)
    mixed = extent == "mixed"
    # Mixed output: a stray quote in another file must not swallow the store's lines.
    lexer = _NetrcLexer(text, trusted[0] if trusted else _line_spans(text), quotes_span_lines=not mixed)
    spans: list[Span] = []

    def _mask(value: str, indices: list[int]) -> None:
        for n, (a, b) in enumerate(_index_runs(indices)):
            spans.append((a, b, mask(value) if n == 0 else ""))

    # ``#...`` in keyword position is a comment to CPython and curl. Only while a slice may open
    # on a value line (``password`` cut off above a ``#hunter2`` line) is a glued ``#x`` first
    # token ambiguous; a bare ``#`` never is.
    in_context = mixed or extent == "start" or (trusted is not None and trusted[1] == 1)
    while (tok := lexer.token()) is not None:
        value, indices, line = tok
        raw_first = text[indices[0]] if indices[0] >= 0 else ""
        if raw_first == "#" and (value == "#" or in_context):
            if lexer.line == line:
                lexer.skip_rest_of_line()
            continue
        if value not in _NETRC_KEYWORDS and mixed:
            if not (glued := _PREFIXED_NETRC_KEYWORD_RE.fullmatch(value)):
                continue
            value = glued.group(1)
        if value not in _NETRC_KEYWORDS:
            _mask(value, indices)
            continue
        in_context = True
        if value in _NETRC_SECRET_FOLLOWERS:
            if (follower := lexer.token()) is not None:
                _mask(follower[0], follower[1])
        elif value in _NETRC_PUBLIC_FOLLOWERS:
            lexer.token()
            # The body runs to the next empty line. Not honoured in mixed output, where a
            # ``macdef`` word in another file would hide the store lines after it.
            if value == "macdef" and not mixed:
                lexer.skip_rest_of_line()
                while lexer.next_line() and not lexer.at_blank_line():
                    lexer.skip_rest_of_line()
    return spans


def _ini_spans(text: str, mask: Mask, secret_option: SecretOption, delimiters: str,
               bodies: list[tuple[int, int]], extent: Extent) -> list[Span]:
    """``configparser`` option grammar: a secret option's value is the rest of its line plus
    every following line indented deeper than the option (blank and comment lines do not end
    it). A ``slice`` starts as if inside a secret value, so indented lines that open it are
    masked until a section or option line establishes context."""
    spans: list[Span] = []
    in_secret, cur_indent = extent == "slice", 0
    for start, end in bodies:
        body = text[start:end]
        stripped = body.strip(" \t\r")
        if not stripped or stripped[0] in "#;":
            continue
        indent = len(body) - len(body.lstrip(" \t"))
        lead = start + indent
        if indent > cur_indent and cur_indent >= 0:
            if in_secret:
                spans.append((lead, lead + len(stripped), mask(stripped)))
            continue
        cur_indent = -1  # no open option until one is parsed
        if stripped.startswith("[") and stripped.endswith("]"):
            continue
        cut = min((i for i in (stripped.find(d) for d in delimiters) if i >= 0), default=-1)
        if cut < 0:
            continue
        key = stripped[:cut].strip(" \t")
        value = stripped[cut + 1:]
        value_start = lead + cut + 1 + (len(value) - len(value.lstrip(" \t")))
        value = value.strip(" \t")
        if extent == "mixed" and not _OPTION_NAME_RE.fullmatch(key):
            continue
        in_secret, cur_indent = secret_option(key, value), indent
        if in_secret and value:
            spans.append((value_start, value_start + len(value), mask(value)))
    return spans


def _pgpass_spans(text: str, mask: Mask, bodies: list[tuple[int, int]], extent: Extent) -> list[Span]:
    """``host:port:db:user:password`` with ``\\`` escapes; the password is the rest of the line.
    A non-comment line without four field separators is masked whole, except in mixed output,
    where only a line with a real port field (digits or ``*``) counts as a pgpass line."""
    spans: list[Span] = []
    for start, end in bodies:
        body = text[start:end].rstrip("\r")
        stripped = body.lstrip(" \t")
        if not stripped or stripped.startswith("#"):
            continue
        seps, i, field_starts = 0, 0, [0]
        while i < len(body) and seps < 4:
            if body[i] == "\\":
                i += 1
            elif body[i] == ":":
                seps += 1
                field_starts.append(i + 1)
            i += 1
        if extent == "mixed" and (
                seps < 4 or not _PGPASS_PORT_RE.fullmatch(body[field_starts[1]:field_starts[2] - 1])):
            continue
        value_start = start + (i if seps == 4 else len(body) - len(stripped))
        value = text[value_start:start + len(body)]
        if value:
            spans.append((value_start, value_start + len(value), mask(value)))
    return spans


def _url_userinfo_spans(text: str, mask: Mask) -> list[Span]:
    return [(m.start(1), m.end(1), mask(m.group(1))) for m in _URL_USERINFO_PASSWORD_RE.finditer(text)]


def _format_spans(text: str, fmt: str, mask: Mask, secret_option: SecretOption,
                  extent: Extent) -> list[Span]:
    if fmt == "netrc":
        return _netrc_spans(text, mask, extent)
    # Line-atomic grammars: without a trusted gutter, read each line both raw and past any
    # line-number prefix and mask the union, so an unrecognized gutter (``grep -n``) can only
    # over-mask.
    trusted = _trusted_gutter(text)
    if trusted and trusted[1] == 1 and extent == "slice":
        extent = "start"
    if trusted:
        readings = (trusted[0],)
    else:
        readings = (_line_spans(text), _prefixed_bodies(text, _LOOSE_GUTTER_RE))
        if extent == "mixed":
            readings += (_prefixed_bodies(text, _GREP_PREFIX_RE),)
    if fmt == "pgpass":
        return [s for bodies in readings for s in _pgpass_spans(text, mask, bodies, extent)]
    delimiters = {"ini": "=:", "npmrc": "="}.get(fmt)
    if delimiters is None:  # git-credentials: URL userinfo only
        return []
    return [s for bodies in readings
            for s in _ini_spans(text, mask, secret_option, delimiters, bodies, extent)]


def mask_credential_stores(text: str, formats: Iterable[str], mask: Mask, secret_option: SecretOption,
                           extent: Extent = "slice") -> str:
    """Mask every credential value ``text`` holds under each of ``formats`` (from
    ``agent.redact._credential_store_format``). URL userinfo passwords are masked for every
    format — a ``.pypirc`` ``repository`` URL can carry one as well as ``.git-credentials``.
    ``secret_option`` decides which INI options are secret, so this pass applies the same key
    policy as the generic assignment passes it runs before."""
    spans = _url_userinfo_spans(text, mask)
    for fmt in formats:
        spans += _format_spans(text, fmt, mask, secret_option, extent)
    if not spans:
        return text
    merged: list[list] = []
    for start, end, repl in sorted(spans):
        if merged and start < merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1][1] = end
                merged[-1][2] = None  # overlapping readings: re-mask the widened span
            continue
        merged.append([start, end, repl])
    out, pos = [], 0
    for start, end, repl in merged:
        out.append(text[pos:start])
        out.append(mask(text[start:end]) if repl is None else repl)
        pos = end
    out.append(text[pos:])
    return "".join(out)
