"""Live API manual of the shared ``lib/src/<package>`` tree, extracted with :mod:`ast`.

The package is located with :func:`importlib.util.find_spec` (or an explicit ``package_dir``) and
every module is parsed from source, so nothing is imported or executed. Parsed modules are cached
by file mtime and size, so the manual follows the source on each request.

Google-style docstrings (``Args:``, ``Returns:``, ``Raises:``, ``Examples:`` ...) are converted to
Markdown, together with the common reStructuredText idioms of this code base: roles such as
``:class:`~emb.dem.core.DEM``` become links into the manual, double-backtick literals become code
spans, and ``::`` literal blocks and ``>>>`` sessions become fenced code blocks.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import os
import re
import textwrap
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SECTION_ALIASES = {
    "args": "Args", "arguments": "Args", "parameters": "Args", "params": "Args",
    "keyword args": "Keyword Args", "keyword arguments": "Keyword Args", "kwargs": "Keyword Args",
    "other parameters": "Other Parameters", "returns": "Returns", "return": "Returns",
    "yields": "Yields", "yield": "Yields", "raises": "Raises", "raise": "Raises",
    "exceptions": "Raises", "attributes": "Attributes", "examples": "Examples",
    "example": "Examples", "note": "Note", "notes": "Notes", "warning": "Warning",
    "warnings": "Warning", "see also": "See Also", "references": "References", "todo": "Todo",
    "methods": "Methods",
}
ITEM_SECTIONS = frozenset({"Args", "Keyword Args", "Other Parameters", "Attributes", "Raises", "Methods"})
RETURN_SECTIONS = frozenset({"Returns", "Yields"})
CALLOUT_SECTIONS = frozenset({"Note", "Notes", "Warning", "Todo"})
SECTION_HEADER = re.compile(r"^([A-Za-z][A-Za-z ]*?):\s*$")
ROLE = re.compile(r"(?::(?:py:)?([a-z]+):|\{(?:py:)?([a-z]+)\})`([^`]+)`")
LITERAL = re.compile(r"``(?!`)((?:[^`\n]|`(?!`)|\n(?![ \t]*\n))+?)``")
REST_LINK = re.compile(r"`([^`<]+?)\s*<(https?://[^>]+)>`_")
CONSTANT_NAME = re.compile(r"^_*[A-Z][A-Z0-9_]*$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
TYPE_LIKE = re.compile(r"^[\w.\[\](),|*'\" ]+$")
SPECIAL_METHODS = frozenset({"__call__"})
ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})
TYPE_VARIABLES = re.compile(r"^(?:typing\.)?(?:TypeVar|ParamSpec|TypeVarTuple)\(")
MAX_DEPTH = 8
INDEX_TTL = 1.0


def _unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001 - a display fallback only
        return "..."


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__") and len(name) > 4


def member_visible(name: str, include_private: bool) -> bool:
    if include_private:
        return True
    if is_dunder(name):
        return name in SPECIAL_METHODS
    return not name.startswith("_")


def module_private(qualname: str) -> bool:
    return any(is_private(part) for part in qualname.split(".")[1:])


# -- docstrings -----------------------------------------------------------------------------


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _take_block(lines: list[str], start: int, base: int) -> tuple[list[str], int]:
    """Lines from ``start`` that are blank or indented deeper than ``base``."""
    block, index = [], start
    while index < len(lines) and (not lines[index].strip() or _indent(lines[index]) > base):
        block.append(lines[index])
        index += 1
    while block and not block[-1].strip():
        block.pop()
    return block, index


def _dedent(lines: list[str]) -> list[str]:
    return textwrap.dedent("\n".join(lines)).split("\n") if lines else []


def _role_label(body: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)\s*<([^<>]+)>$", body.strip())
    if match and match.group(1):
        return match.group(1).strip(), match.group(2).strip()
    target = body.strip()
    if target.startswith("~"):
        target = target[1:]
        return target.rstrip("()").rsplit(".", 1)[-1] + ("()" if target.endswith("()") else ""), target
    return target, target


def rst_inline(text: str, resolve: Callable[[str], str | None] | None) -> str:
    """Convert reST roles, literals and links outside fenced code (a literal may wrap a line)."""
    out: list[str] = []
    block: list[str] = []
    fence = None

    def role(match: re.Match) -> str:
        kind = match.group(1) or match.group(2)
        label, target = _role_label(match.group(3))
        if kind == "math":
            return f"${match.group(3)}$"
        route = resolve(target) if resolve and kind not in ("ref", "doc", "term") else None
        code = f"`{label}`" if "`" not in label else label
        return f"[{code}]({route})" if route else code

    def literal(match: re.Match) -> str:
        body = re.sub(r"[ \t]*\n[ \t]*", " ", match.group(1))
        return f"``{body}``" if "`" in body else f"`{body}`"

    def flush() -> None:
        if block:
            chunk = ROLE.sub(role, "\n".join(block))
            chunk = LITERAL.sub(literal, chunk)
            out.append(REST_LINK.sub(lambda m: f"[{m.group(1)}]({m.group(2)})", chunk))
            block.clear()

    for line in text.split("\n"):
        marker = FENCE.match(line)
        if marker:
            flush()
            char = marker.group(1)[0]
            fence = char if fence is None else (None if fence == char else fence)
            out.append(line)
        elif fence:
            out.append(line)
        else:
            block.append(line)
    flush()
    return "\n".join(out)


def rst_blocks(text: str) -> str:
    """Turn ``::`` literal blocks, ``>>>`` sessions and ``..`` directives into Markdown blocks."""
    lines = text.split("\n")
    out: list[str] = []
    index, fence = 0, None
    while index < len(lines):
        line = lines[index]
        marker = FENCE.match(line)
        if marker:
            char = marker.group(1)[0]
            fence = char if fence is None else (None if fence == char else fence)
            out.append(line)
            index += 1
            continue
        if fence:
            out.append(line)
            index += 1
            continue
        stripped = line.strip()
        directive = re.match(r"^(\s*)\.\.\s+([\w-]+)::\s*(.*)$", line)
        if directive:
            base, name, argument = len(directive.group(1)), directive.group(2).lower(), directive.group(3)
            block, index = _take_block(lines, index + 1, base)
            body = [row for row in _dedent(block) if not re.match(r"^:[\w-]+:", row.strip())]
            while body and not body[0].strip():
                body.pop(0)
            if name in ("code-block", "code", "sourcecode", "doctest"):
                out += ["", f"```{argument.strip() or 'python'}", *body, "```", ""]
            elif name == "math":
                out += ["", "$$", argument, *body, "$$", ""]
            elif name in ("note", "warning", "tip", "important", "caution", "attention", "seealso",
                          "hint", "danger", "error", "todo", "deprecated", "versionadded", "versionchanged"):
                title = name.replace("seealso", "see also").capitalize()
                first = f"**{title}:** {argument}".rstrip()
                out += ["", f"> {first}", *[f"> {row}" if row else ">" for row in body], ""]
            else:
                out += [f"*{name}* {argument}".rstrip(), *body]
            continue
        if stripped.endswith("::") and not stripped.startswith(">>>"):
            probe = index + 1
            while probe < len(lines) and not lines[probe].strip():
                probe += 1
            deeper = probe < len(lines) and _indent(lines[probe]) > _indent(line)
            level = probe < len(lines) and _indent(line) > 0 and _indent(lines[probe]) == _indent(line)
            if deeper or level:
                head = line.strip()[:-2]
                if stripped != "::":
                    out.append(head.rstrip() if head.endswith(" ") else head + ":")
                if deeper:
                    block, index = _take_block(lines, probe, _indent(line))
                else:
                    block, index = [], probe
                    while index < len(lines) and lines[index].strip():
                        block.append(lines[index])
                        index += 1
                out += ["", "```", *_dedent(block), "```", ""]
                continue
        if stripped.startswith(">>>"):
            base = _indent(line)
            block = []
            while index < len(lines) and lines[index].strip():
                block.append(lines[index][base:] if _indent(lines[index]) >= base else lines[index].strip())
                index += 1
            out += ["", "```python", *block, "```", ""]
            continue
        out.append(line)
        index += 1
    return "\n".join(out)


def _parse_item(line: str) -> tuple[str, str | None, str] | None:
    match = re.match(r"^(\*{0,2}[A-Za-z_][\w.]*(?:\[[^\]]*\])?)\s*", line)
    if not match:
        return None
    name, rest = match.group(1), line[match.end():]
    kind = None
    if rest.startswith("("):
        depth = 0
        for position, char in enumerate(rest):
            depth += char == "("
            depth -= char == ")"
            if depth == 0:
                kind, rest = rest[1:position].strip(), rest[position + 1:].lstrip()
                break
        else:
            return None
    if not rest.startswith(":"):
        return None
    return name, kind, rest[1:].strip()


def _render_items(body: list[str], section: str) -> str:
    items: list[list] = []
    preamble: list[str] = []
    for line in body:
        parsed = _parse_item(line) if line.strip() and _indent(line) == 0 else None
        if parsed:
            items.append([parsed[0], parsed[1], [parsed[2]] if parsed[2] else []])
        elif items:
            items[-1][2].append(line)
        else:
            preamble.append(line)
    if not items:
        return rst_blocks("\n".join(body))
    out = []
    if any(row.strip() for row in preamble):
        out += [rst_blocks("\n".join(preamble)), ""]
    for name, kind, desc in items:
        head = f"`{name}`"
        if kind:
            head += f" ({kind if '`' in kind else '`' + kind + '`'})"
        first = desc[0] if desc else ""
        rest = _dedent(desc[1:]) if len(desc) > 1 else []
        text = rst_blocks("\n".join([first, *rest]).strip("\n"))
        rows = text.split("\n")
        separator = ": " if section != "Raises" or first else ""
        line = f"- {head}{separator}{rows[0]}" if rows and rows[0] else f"- {head}"
        out.append(line)
        out += [f"  {row}" if row.strip() else "" for row in rows[1:]]
    return "\n".join(out)


def _render_returns(body: list[str]) -> str:
    text = "\n".join(body).strip("\n")
    first, _, rest = text.partition("\n")
    match = re.match(r"^([^:]+?):\s+(.+)$", first)
    kind = match.group(1).replace(" | ", "|").replace(", ", ",") if match else ""
    if match and TYPE_LIKE.match(match.group(1)) and not re.search(r"\w \w", kind):
        text = f"`{match.group(1).strip()}`: {match.group(2)}" + (f"\n{rest}" if rest else "")
    return rst_blocks(text)


def docstring_markdown(doc: str | None, resolve: Callable[[str], str | None] | None = None) -> str:
    """Render a Google-style docstring (with light reST) as Markdown."""
    if not doc:
        return ""
    lines = inspect.cleandoc(doc).split("\n")
    chunks: list[str] = []
    buffer: list[str] = []
    index, fence = 0, None

    def flush() -> None:
        if any(row.strip() for row in buffer):
            chunks.append(rst_blocks("\n".join(buffer)))
        buffer.clear()

    while index < len(lines):
        line = lines[index]
        marker = FENCE.match(line)
        if marker:
            char = marker.group(1)[0]
            fence = char if fence is None else (None if fence == char else fence)
        header = SECTION_HEADER.match(line) if fence is None else None
        name = SECTION_ALIASES.get(header.group(1).strip().lower()) if header else None
        if name:
            probe = index + 1
            while probe < len(lines) and not lines[probe].strip():
                probe += 1
            if probe >= len(lines) or _indent(lines[probe]) > 0:
                flush()
                block, index = _take_block(lines, index + 1, 0)
                body = _dedent(block)
                if name in ITEM_SECTIONS:
                    rendered = _render_items(body, name)
                elif name in RETURN_SECTIONS:
                    rendered = _render_returns(body)
                else:
                    rendered = rst_blocks("\n".join(body))
                if name in CALLOUT_SECTIONS:
                    rows = rendered.split("\n")
                    chunks.append("\n".join([f"> **{name}:** {rows[0]}".rstrip(),
                                             *[f"> {row}" if row else ">" for row in rows[1:]]]))
                else:
                    chunks.append(f"**{name}**\n\n{rendered}")
                continue
        buffer.append(line)
        index += 1
    flush()
    return rst_inline("\n\n".join(chunk.strip("\n") for chunk in chunks if chunk.strip()), resolve)


def docstring_summary(doc: str | None) -> str:
    if not doc:
        return ""
    first = inspect.cleandoc(doc).split("\n\n", 1)[0]
    first = ROLE.sub(lambda m: _role_label(m.group(3))[0], first)
    first = LITERAL.sub(lambda m: m.group(1), first)
    return _short(first, 220)


# -- parsing --------------------------------------------------------------------------------


def _decorator_base(text: str) -> str:
    return re.sub(r"\(.*$", "", text, flags=re.S).rsplit(".", 1)[-1]


def _param(arg: ast.arg, default) -> str:
    text = arg.arg
    if arg.annotation is not None:
        text += ": " + _short(_unparse(arg.annotation), 80)
    if default is not None:
        text += (" = " if arg.annotation is not None else "=") + _short(_unparse(default), 60)
    return text


def format_arguments(args: ast.arguments, skip_first: bool = False) -> str:
    positional = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    posonly = len(args.posonlyargs)
    if skip_first and positional:
        positional, defaults, posonly = positional[1:], defaults[1:], max(0, posonly - 1)
    parts = []
    for position, (arg, default) in enumerate(zip(positional, defaults)):
        parts.append(_param(arg, default))
        if posonly and position == posonly - 1:
            parts.append("/")
    if args.vararg:
        parts.append("*" + _param(args.vararg, None))
    elif args.kwonlyargs:
        parts.append("*")
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        parts.append(_param(arg, default))
    if args.kwarg:
        parts.append("**" + _param(args.kwarg, None))
    return "(" + ", ".join(parts) + ")"


def _function(node, in_class: bool) -> dict:
    decorators = [_unparse(item) for item in node.decorator_list]
    bases = {_decorator_base(item) for item in decorators}
    skip_first = in_class
    if not in_class:
        kind = "function"
    elif "staticmethod" in bases:
        kind, skip_first = "staticmethod", False
    elif "classmethod" in bases:
        kind = "classmethod"
    elif bases & {"property", "cached_property"}:
        kind = "property"
    else:
        kind = "method"
    signature = format_arguments(node.args, skip_first)
    returns = _short(_unparse(node.returns), 120) if node.returns is not None else None
    return {
        "name": node.name, "kind": kind, "lineno": node.lineno, "decorators": decorators,
        "signature": signature, "returns": returns, "doc": ast.get_docstring(node),
        "async": isinstance(node, ast.AsyncFunctionDef), "abstract": "abstractmethod" in bases,
        "overload": "overload" in bases,
        "accessor": any(item.endswith((".setter", ".deleter")) for item in decorators),
    }


def _merge_functions(functions: list[dict]) -> list[dict]:
    """Fold ``@overload`` stubs and property setters into the implementation."""
    merged: dict[str, dict] = {}
    overloads: dict[str, list[str]] = {}
    for item in functions:
        if item["overload"]:
            overloads.setdefault(item["name"], []).append(item["signature"] + (
                f" -> {item['returns']}" if item["returns"] else ""))
            continue
        if item["accessor"]:
            if item["name"] in merged:
                merged[item["name"]]["settable"] = True
            continue
        merged.setdefault(item["name"], item)
    for name, signatures in overloads.items():
        if name in merged:
            merged[name]["overloads"] = signatures
    return sorted(merged.values(), key=lambda item: item["lineno"])


def _assignment(node, source: str) -> list[dict]:
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        value = node.value
        return [{"name": node.target.id, "annotation": _short(_unparse(node.annotation), 100),
                 "value": _short(ast.get_source_segment(source, value) or _unparse(value), 120) if value else None,
                 "lineno": node.lineno}]
    if isinstance(node, ast.Assign):
        value = _short(ast.get_source_segment(source, node.value) or _unparse(node.value), 120)
        return [{"name": target.id, "annotation": None, "value": value, "lineno": node.lineno}
                for target in node.targets if isinstance(target, ast.Name)]
    return []


def _docstring_after(body: list, position: int) -> str | None:
    if position + 1 < len(body):
        nxt = body[position + 1]
        if isinstance(nxt, ast.Expr) and isinstance(nxt.value, ast.Constant) and isinstance(nxt.value.value, str):
            return inspect.cleandoc(nxt.value.value)
    return None


def _class(node: ast.ClassDef, source: str) -> dict:
    decorators = [_unparse(item) for item in node.decorator_list]
    bases = [_unparse(item) for item in node.bases] + [
        f"{item.arg}={_unparse(item.value)}" for item in node.keywords if item.arg]
    base_names = {re.sub(r"\[.*$", "", base).rsplit(".", 1)[-1] for base in bases}
    decorator_names = {_decorator_base(item) for item in decorators}
    if "dataclass" in decorator_names:
        kind = "dataclass"
    elif base_names & ENUM_BASES:
        kind = "enum"
    elif "Protocol" in base_names:
        kind = "protocol"
    elif "NamedTuple" in base_names:
        kind = "namedtuple"
    elif "TypedDict" in base_names:
        kind = "typeddict"
    elif any(name.endswith(("Error", "Exception", "Warning")) for name in base_names):
        kind = "exception"
    else:
        kind = "class"
    functions, attributes, nested = [], [], []
    for position, stmt in enumerate(node.body):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_function(stmt, True))
        elif isinstance(stmt, ast.ClassDef):
            nested.append({"name": stmt.name, "lineno": stmt.lineno,
                           "summary": docstring_summary(ast.get_docstring(stmt))})
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            doc = _docstring_after(node.body, position)
            for item in _assignment(stmt, source):
                item["doc"] = doc
                attributes.append(item)
    methods = _merge_functions(functions)
    signature = None
    doc = ast.get_docstring(node)
    init = next((item for item in methods if item["name"] == "__init__"), None)
    if init is not None:
        signature = init["signature"]
        if init["doc"]:
            doc = f"{doc}\n\n{init['doc']}" if doc else init["doc"]
    elif kind in ("dataclass", "namedtuple", "typeddict"):
        fields = [item for item in attributes if item["annotation"] is not None
                  and not item["annotation"].startswith(("ClassVar", "typing.ClassVar"))
                  and not item["name"].startswith("_")]
        signature = "(" + ", ".join(
            f"{item['name']}: {item['annotation']}" + (f" = {item['value']}" if item["value"] else "")
            for item in fields) + ")"
    else:
        new = next((item for item in methods if item["name"] == "__new__"), None)
        if new is not None:
            signature = new["signature"]
    return {"name": node.name, "kind": kind, "lineno": node.lineno, "bases": bases,
            "decorators": decorators, "doc": doc, "signature": signature,
            "methods": methods, "attributes": attributes, "nested": nested}


def _main_guard(test) -> bool:
    return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
            and test.left.id == "__name__")


def _flatten(nodes: list) -> list:
    out = []
    for node in nodes:
        if isinstance(node, ast.If):
            if _main_guard(node.test):
                continue
            out += _flatten(node.body) + _flatten(node.orelse)
        elif isinstance(node, ast.Try) or type(node).__name__ == "TryStar":
            out += _flatten(node.body) + _flatten(node.orelse) + _flatten(node.finalbody)
            for handler in node.handlers:
                out += _flatten(handler.body)
        else:
            out.append(node)
    return out


def _string_list(node) -> list[str] | None:
    if isinstance(node, (ast.List, ast.Tuple)):
        return [item.value for item in node.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)]
    return None


@dataclass
class ModuleInfo:
    name: str
    path: Path | None
    is_package: bool
    doc: str | None = None
    all: list[str] | None = None
    classes: list[dict] = field(default_factory=list)
    functions: list[dict] = field(default_factory=list)
    constants: list[dict] = field(default_factory=list)
    imports: dict[str, str] = field(default_factory=dict)
    error: str | None = None


def _relative_base(module: str, is_package: bool, level: int) -> str | None:
    parts = module.split(".")
    if not is_package:
        parts = parts[:-1]
    if level > 1:
        if level - 1 > len(parts):
            return None
        parts = parts[: len(parts) - (level - 1)]
    return ".".join(parts) if parts else None


def parse_module(name: str, path: Path | None, is_package: bool, package: str) -> ModuleInfo:
    info = ModuleInfo(name=name, path=path, is_package=is_package)
    if path is None:
        return info
    try:
        source = path.read_bytes().decode("utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, ValueError) as exc:
        info.error = f"{type(exc).__name__}: {exc}"
        return info
    info.doc = ast.get_docstring(tree)
    body = _flatten(list(tree.body))
    functions = []
    seen: set[str] = set()
    for position, node in enumerate(body):
        if isinstance(node, ast.ClassDef):
            if node.name not in seen:
                seen.add(node.name)
                info.classes.append(_class(node, source))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_function(node, False))
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            single = isinstance(node, ast.Assign) and len(node.targets) == 1
            target = node.targets[0] if single else getattr(node, "target", None)
            if isinstance(target, ast.Name) and target.id == "__all__":
                names = _string_list(node.value)
                if names is not None:
                    info.all = (info.all or []) + names if isinstance(node, ast.AugAssign) else names
                continue
            if isinstance(node, ast.AugAssign):
                continue
            doc = _docstring_after(body, position)
            for item in _assignment(node, source):
                annotation = item["annotation"] or ""
                if item["value"] and TYPE_VARIABLES.match(item["value"]):
                    continue
                if (CONSTANT_NAME.match(item["name"]) or "Final" in annotation or "TypeAlias" in annotation
                        or (info.all and item["name"] in info.all)) and item["name"] not in seen:
                    seen.add(item["name"])
                    item["doc"] = doc
                    info.constants.append(item)
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "extend"
              and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "__all__"
              and node.value.args):
            names = _string_list(node.value.args[0])
            if names:
                info.all = (info.all or []) + names
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = _relative_base(name, is_package, node.level)
                if base is None:
                    continue
                target_module = f"{base}.{node.module}" if node.module else base
            else:
                target_module = node.module or ""
            if not (target_module == package or target_module.startswith(package + ".")):
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                info.imports[alias.asname or alias.name] = f"{target_module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname and (alias.name == package or alias.name.startswith(package + ".")):
                    info.imports[alias.asname] = alias.name
    info.functions = [item for item in _merge_functions(functions) if item["name"] not in seen]
    return info


# -- the manual -----------------------------------------------------------------------------


@dataclass
class Index:
    generation: tuple
    root: Path | None
    modules: dict[str, ModuleInfo]
    symbols: dict[str, dict]
    aliases: dict[str, str]


class ApiDocs:
    """The manual of one package. ``package_dir`` overrides the ``find_spec`` lookup (tests)."""

    def __init__(self, package: str = "(none)", package_dir: str | os.PathLike | None = None):
        self.package = package
        self._package_dir = Path(package_dir).resolve() if package_dir else None
        self._lock = threading.Lock()
        self._files: dict[str, tuple[tuple[int, int], ModuleInfo]] = {}
        self._index: Index | None = None
        self._checked = 0.0
        self._build_lock = threading.Lock()

    def locate(self) -> tuple[Path | None, str | None]:
        """Return ``(package_directory, error)`` without importing the package."""
        if self.package in {"(none)", "", "null", "none"} and self._package_dir is None:
            return None, "no package configured"
        if self._package_dir is not None:
            if self.package in {"(none)", "", "null", "none"}:
                return None, "no package configured"
            if self._package_dir.is_dir():
                return self._package_dir, None
            return None, f"{self._package_dir} is not a directory"
        try:
            spec = importlib.util.find_spec(self.package)
        except (ImportError, ValueError) as exc:
            return None, f"cannot locate {self.package}: {exc}"
        if spec is None:
            return None, f"the {self.package} package is not installed in this interpreter"
        locations = list(spec.submodule_search_locations or [])
        if locations:
            return Path(locations[0]).resolve(), None
        if spec.origin and spec.origin.endswith(".py"):
            return Path(spec.origin).resolve().parent, None
        return None, f"{self.package} is not a source package"

    def _discover(self, root: Path) -> list[tuple[str, Path | None, bool]]:
        found = []
        for dirpath, dirnames, filenames in os.walk(root):
            rel = Path(dirpath).relative_to(root).parts
            dirnames[:] = sorted(d for d in dirnames if d.isidentifier() and not d.startswith(".")
                                 and d != "__pycache__" and len(rel) < MAX_DEPTH)
            prefix = [self.package, *rel]
            py_files = sorted(f for f in filenames if f.endswith(".py") and f[:-3].isidentifier())
            has_init = "__init__.py" in filenames
            if not rel or has_init or any(f != "__init__.py" for f in py_files):
                found.append((".".join(prefix), Path(dirpath) / "__init__.py" if has_init else None, True))
            for name in py_files:
                if name != "__init__.py":
                    found.append((".".join(prefix + [name[:-3]]), Path(dirpath) / name, False))
        return found

    def peek(self) -> dict | None:
        """Totals of the last built index, without building one (None before the first build)."""
        with self._lock:
            index = self._index
        if index is None or index.root is None:
            return None
        return {"package": self.package, "modules": len(index.modules),
                "classes": sum(len(m.classes) for m in index.modules.values()),
                "functions": sum(len(m.functions) for m in index.modules.values())}

    def index(self) -> Index:
        with self._lock:
            if self._index is not None and time.monotonic() - self._checked < INDEX_TTL:
                return self._index
        with self._build_lock:
            with self._lock:
                if self._index is not None and time.monotonic() - self._checked < INDEX_TTL:
                    return self._index
            index = self._build()
            with self._lock:
                self._index, self._checked = index, time.monotonic()
            return index

    def _build(self) -> Index:
        root, _ = self.locate()
        if root is None:
            return Index((), None, {}, {}, {})
        discovered = self._discover(root)
        signatures = []
        modules: dict[str, ModuleInfo] = {}
        for name, path, is_package in discovered:
            try:
                st = path.stat() if path else None
            except OSError:
                continue
            sig = (st.st_mtime_ns, st.st_size) if st else (0, 0)
            signatures.append((name, sig))
            key = f"{name}:{path}"
            with self._lock:
                hit = self._files.get(key)
            if hit and hit[0] == sig:
                modules[name] = hit[1]
                continue
            info = parse_module(name, path, is_package, self.package)
            with self._lock:
                self._files[key] = (sig, info)
            modules[name] = info
        generation = (str(root), tuple(signatures))
        with self._lock:
            previous = self._index
        if previous is not None and previous.generation == generation:
            return previous
        return Index(generation, root, modules, *self._symbols(modules))

    def _symbols(self, modules: dict[str, ModuleInfo]) -> tuple[dict, dict]:
        symbols: dict[str, dict] = {}
        aliases: dict[str, str] = {}
        for mod in modules.values():
            private = module_private(mod.name)
            symbols[mod.name] = {"kind": "package" if mod.is_package else "module", "module": mod.name,
                                 "anchor": "", "summary": docstring_summary(mod.doc), "private": private}
            for cls in mod.classes:
                qual = f"{mod.name}.{cls['name']}"
                cls_private = private or is_private(cls["name"])
                symbols[qual] = {"kind": "class", "module": mod.name, "anchor": cls["name"],
                                 "summary": docstring_summary(cls["doc"]), "private": cls_private}
                for member in cls["methods"]:
                    symbols[f"{qual}.{member['name']}"] = {
                        "kind": member["kind"], "module": mod.name, "anchor": f"{cls['name']}.{member['name']}",
                        "summary": docstring_summary(member["doc"]),
                        "private": cls_private or not member_visible(member["name"], False)}
                for attr in cls["attributes"]:
                    symbols.setdefault(f"{qual}.{attr['name']}", {
                        "kind": "attribute", "module": mod.name, "anchor": f"{cls['name']}.{attr['name']}",
                        "summary": docstring_summary(attr.get("doc")),
                        "private": cls_private or attr["name"].startswith("_")})
            for func in mod.functions:
                symbols[f"{mod.name}.{func['name']}"] = {
                    "kind": "function", "module": mod.name, "anchor": func["name"],
                    "summary": docstring_summary(func["doc"]), "private": private or is_private(func["name"])}
            for const in mod.constants:
                symbols.setdefault(f"{mod.name}.{const['name']}", {
                    "kind": "constant", "module": mod.name, "anchor": const["name"],
                    "summary": docstring_summary(const.get("doc")),
                    "private": private or const["name"].startswith("_")})
            for local, target in mod.imports.items():
                if self._exported(mod, local):
                    aliases[f"{mod.name}.{local}"] = target
        return symbols, aliases

    @staticmethod
    def _exported(mod: ModuleInfo, name: str) -> bool:
        if mod.all is not None:
            return name in mod.all
        return mod.is_package and not name.startswith("_")

    # -- resolution ------------------------------------------------------------------------

    def _route(self, index: Index, qualname: str, depth: int = 0) -> str | None:
        if depth > 8 or not qualname:
            return None
        symbol = index.symbols.get(qualname)
        if symbol:
            return f"/apidocs/{symbol['module']}" + (f"#{symbol['anchor']}" if symbol["anchor"] else "")
        if qualname in index.aliases:
            return self._route(index, index.aliases[qualname], depth + 1)
        head, _, tail = qualname.rpartition(".")
        if head in index.aliases:
            return self._route(index, f"{index.aliases[head]}.{tail}", depth + 1)
        if head and index.symbols.get(head, {}).get("kind") == "class":
            return self._route(index, head, depth + 1)
        return None

    def route_for(self, target: str, module: str | None = None, cls: str | None = None,
                  index: Index | None = None) -> str | None:
        """Dashboard route of a (possibly relative) dotted name, or None when unknown."""
        index = index or self.index()
        name = target.strip().lstrip("~").strip()
        name = name[:-2] if name.endswith("()") else name
        if not name or not re.match(r"^[A-Za-z_][\w.]*$", name):
            return None
        candidates = [name]
        if module:
            if cls:
                candidates.append(f"{module}.{cls}.{name}")
            candidates.append(f"{module}.{name}")
            parent = module.rpartition(".")[0]
            if parent:
                candidates.append(f"{parent}.{name}")
        candidates.append(f"{self.package}.{name}")
        for candidate in candidates:
            route = self._route(index, candidate)
            if route:
                return route
        matches = [qual for qual in index.symbols if qual.endswith("." + name)]
        if len(matches) == 1:
            return self._route(index, matches[0])
        return None

    # -- payloads --------------------------------------------------------------------------

    def _source(self, path: Path | None, repo_root: Path | None) -> str | None:
        if path is None or repo_root is None:
            return None
        try:
            return path.resolve().relative_to(repo_root).as_posix()
        except ValueError:
            return None

    def tree(self, include_private: bool = False, repo_root: Path | None = None) -> dict:
        root, error = self.locate()
        if root is None:
            return {"available": False, "package": self.package, "error": error, "modules": []}
        index = self.index()
        modules = []
        for name in sorted(index.modules):
            mod = index.modules[name]
            private = module_private(name)
            if private and not include_private:
                continue
            modules.append({
                "name": name, "is_package": mod.is_package, "private": private,
                "summary": docstring_summary(mod.doc), "error": mod.error,
                "classes": sum(1 for c in mod.classes if include_private or not is_private(c["name"])),
                "functions": sum(1 for f in mod.functions if include_private or not is_private(f["name"])),
            })
        totals = {
            "modules": len(index.modules),
            "classes": sum(len(m.classes) for m in index.modules.values()),
            "functions": sum(len(m.functions) for m in index.modules.values()),
        }
        return {"available": True, "package": self.package, "location": str(root),
                "source": self._source(root, repo_root), "modules": modules, "totals": totals,
                "include_private": include_private}

    def module(self, name: str, include_private: bool = False, repo_root: Path | None = None) -> dict | None:
        index = self.index()
        mod = index.modules.get(name)
        if mod is None:
            return None

        def render(doc: str | None, cls: str | None = None) -> str:
            return docstring_markdown(doc, lambda target: self.route_for(target, name, cls, index))

        def function_payload(item: dict, cls: str | None = None) -> dict:
            anchor = f"{cls}.{item['name']}" if cls else item["name"]
            return {key: item.get(key) for key in (
                "name", "kind", "lineno", "decorators", "signature", "returns", "async", "abstract",
                "overloads", "settable")} | {"anchor": anchor, "doc": render(item["doc"], cls),
                                             "private": not member_visible(item["name"], False)}

        classes = []
        for cls in mod.classes:
            if is_private(cls["name"]) and not include_private:
                continue
            classes.append({
                "name": cls["name"], "anchor": cls["name"], "kind": cls["kind"], "lineno": cls["lineno"],
                "bases": [{"text": base, "route": self.route_for(re.sub(r"\[.*$", "", base), name, None, index)}
                          for base in cls["bases"]],
                "decorators": cls["decorators"], "signature": cls["signature"],
                "doc": render(cls["doc"], cls["name"]), "private": is_private(cls["name"]),
                "methods": [function_payload(item, cls["name"]) for item in cls["methods"]
                            if item["name"] != "__init__" and member_visible(item["name"], include_private)],
                "attributes": [{**attr, "anchor": f"{cls['name']}.{attr['name']}",
                                "doc": render(attr.get("doc"), cls["name"])}
                               for attr in cls["attributes"]
                               if include_private or not attr["name"].startswith("_")],
                "nested": [item for item in cls["nested"] if include_private or not is_private(item["name"])],
            })
        functions = [function_payload(item) for item in mod.functions
                     if include_private or not is_private(item["name"])]
        constants = [{**item, "anchor": item["name"], "doc": render(item.get("doc"))}
                     for item in mod.constants if include_private or not item["name"].startswith("_")]
        prefix = name + "."
        submodules = []
        for other in sorted(index.modules):
            if other.startswith(prefix) and "." not in other[len(prefix):]:
                if module_private(other) and not include_private:
                    continue
                child = index.modules[other]
                submodules.append({"name": other, "is_package": child.is_package,
                                   "summary": docstring_summary(child.doc), "private": module_private(other)})
        order = {item: position for position, item in enumerate(mod.all or [])}
        exports = sorted(
            ({"name": local, "target": target, "route": self._route(index, target)}
             for local, target in mod.imports.items() if self._exported(mod, local)),
            key=lambda item: (order.get(item["name"], len(order)), item["name"].casefold()))
        parts = name.split(".")
        return {
            "name": name, "is_package": mod.is_package, "private": module_private(name),
            "source": self._source(mod.path, repo_root), "error": mod.error,
            "doc": render(mod.doc), "summary": docstring_summary(mod.doc),
            "parents": [".".join(parts[: i + 1]) for i in range(len(parts) - 1)],
            "all": mod.all, "submodules": submodules, "exports": exports, "classes": classes,
            "functions": functions, "constants": constants, "include_private": include_private,
        }

    def search(self, query: str, include_private: bool = False, limit: int = 60) -> list[dict]:
        terms = [term for term in query.lower().split() if term]
        if not terms:
            return []
        index = self.index()
        needle = terms[-1]
        scored = []
        for qualname, symbol in index.symbols.items():
            if symbol["private"] and not include_private:
                continue
            lowered = qualname.lower()
            if not all(term in lowered for term in terms):
                continue
            last = lowered.rsplit(".", 1)[-1]
            score = 100 if last == needle else 60 if last.startswith(needle) else 35 if needle in last else 10
            score += {"class": 6, "function": 5, "package": 4, "module": 4}.get(symbol["kind"], 0)
            scored.append((score, qualname, symbol))
        for alias, target in index.aliases.items():
            lowered = alias.lower()
            if all(term in lowered for term in terms):
                last = lowered.rsplit(".", 1)[-1]
                score = (70 if last == needle else 30) - 5
                scored.append((score, alias, {"kind": "alias", "module": alias.rsplit(".", 1)[0],
                                              "anchor": None, "summary": f"re-export of {target}",
                                              "target": target}))
        scored.sort(key=lambda row: (-row[0], len(row[1]), row[1]))
        results = []
        for _score, qualname, symbol in scored[:limit]:
            route = (self._route(index, symbol["target"]) if symbol["kind"] == "alias"
                     else self._route(index, qualname))
            results.append({"qualname": qualname, "kind": symbol["kind"], "module": symbol["module"],
                            "route": route, "summary": symbol["summary"]})
        return results
