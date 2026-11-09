"""Reject known synthetic-browser-HTTP constructs in the immutable UX plan.

This is a bounded source preflight, not a JavaScript interpreter or a general
no-mocking proof. Python AST selects literal scripts actually submitted to
browser evaluation methods. Comment/string-aware tokens then recognize direct
window/globalThis/self.fetch function replacements constructing new Response
or new DOMException with a literal second argument naming AbortError.
Aliases, assembled scripts, template interpolations and indirect helpers are
outside this narrow check.
Actual ASGI transport, unit fixtures and real-response instrumentation remain
subject to the existing behavioral checks. Candidate code is never executed.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shlex

from .python_global_preflight import _candidate_bytes, _Unavailable

SPEC_RELATIVE = 'docs/task_boards/complaint_gui_ux_overhaul_spec.json'
SPEC_SHA256 = 'bd94395a17a4da882740fcf30ca2628143a9ffa6ef497906ced70243530178c3'
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_MAX_TOKENS = 100_000
_MAX_NODES = 100_000
_BROWSER_CALLS = {'evaluate', 'evaluate_handle', 'add_init_script', 'wait_for_function'}


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    line: int


def _tokens(text):
    """Lex just enough JS to distinguish names/calls from comments and strings."""
    result, index, line = [], 0, 1
    while index < len(text):
        start, character = index, text[index]
        if character.isspace():
            line += character == '\n'; index += 1; continue
        if text.startswith('//', index):
            end = text.find('\n', index + 2)
            index = len(text) if end < 0 else end
            continue
        if text.startswith('/*', index):
            end = text.find('*/', index + 2)
            if end < 0:
                raise _Unavailable('script_uninspectable')
            line += text[index:end + 2].count('\n'); index = end + 2; continue
        if character in {'\"', "'", '`'}:
            quote, value, token_line = character, [], line
            index += 1
            while index < len(text) and text[index] != quote:
                current = text[index]
                if current == '\\':
                    index += 1
                    if index >= len(text):
                        raise _Unavailable('script_uninspectable')
                    current = text[index]
                    # Keep escaped text opaque; computed aliases are not part
                    # of the direct-property construct this check recognizes.
                    value.append('\\' + current)
                else:
                    value.append(current)
                line += current == '\n'; index += 1
            if index >= len(text):
                raise _Unavailable('script_uninspectable')
            index += 1
            result.append(_Token('string', ''.join(value), token_line))
        elif character.isalpha() or character in {'_', '$'}:
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] in {'_', '$'}):
                index += 1
            result.append(_Token('name', text[start:index], line))
        else:
            # JS regexp literals must also be opaque. A slash after an
            # expression is division; after these operators it starts a regex.
            previous = result[-1].value if result else ''
            if character == '/' and previous in {'', '(', '[', '{', '=', ':', ',', 'return', '=>', '!', '&', '|', '?'}:
                index += 1; bracket = False
                while index < len(text):
                    current = text[index]
                    if current == '\\':
                        index += 2; continue
                    if current == '[': bracket = True
                    if current == ']': bracket = False
                    if current == '/' and not bracket: break
                    if current == '\n': raise _Unavailable('script_uninspectable')
                    index += 1
                if index >= len(text): raise _Unavailable('script_uninspectable')
                index += 1
                while index < len(text) and text[index].isalpha(): index += 1
                result.append(_Token('string', '', line))
            else:
                operator = next((op for op in ('=>', '===', '!==', '==', '!=', '&&', '||', '?.')
                                 if text.startswith(op, index)), character)
                result.append(_Token('punctuation', operator, line)); index += len(operator)
        if len(result) > _MAX_TOKENS:
            raise _Unavailable('script_bound')
    return result


def _balanced(tokens, start, opening='(', closing=')'):
    if start >= len(tokens) or tokens[start].value != opening:
        return None
    depth = 0
    for index in range(start, len(tokens)):
        if tokens[index].kind == 'string': continue
        value = tokens[index].value
        depth += value == opening
        depth -= value == closing
        if depth == 0: return index
    raise _Unavailable('script_uninspectable')


def _replacement_body(tokens, start):
    """Find a direct function/arrow RHS; do not scan unrelated later code."""
    index = start
    if index < len(tokens) and tokens[index].value == 'async': index += 1
    if index >= len(tokens): return None
    if tokens[index].value == 'function':
        index += 1
        if index < len(tokens) and tokens[index].kind == 'name': index += 1
        end = _balanced(tokens, index)
        if end is None: return None
        index = end + 1
    else:
        if tokens[index].value == '(':
            end = _balanced(tokens, index)
            if end is None: return None
            index = end + 1
        elif tokens[index].kind == 'name': index += 1
        else: return None
        if index >= len(tokens) or tokens[index].value != '=>': return None
        index += 1
    if index < len(tokens) and tokens[index].value == '{':
        return index + 1, _balanced(tokens, index, '{', '}')
    # Expression-bodied arrow: stop at this assignment's top-level separator.
    end, depth = index, 0
    while end < len(tokens):
        value = tokens[end].value
        if (depth == 0 and end > index and tokens[end].line > tokens[end - 1].line
                and value in {'const', 'let', 'var', 'function', 'class'}):
            break  # A new declaration after an expression ends an ASI arrow.
        if tokens[end].kind != 'string':
            if depth == 0 and value in {';', ',', '}'}: break
            if value in {'(', '['}: depth += 1
            if value in {')', ']'}:
                if depth == 0: break
                depth -= 1
        end += 1
    return index, end


def _abort_error_name(tokens, start, end):
    """Recognize the literal name argument, skipping the first argument's groups."""
    groups = []
    for index in range(start + 3, end):
        token = tokens[index]
        if token.kind == 'string': continue
        value = token.value
        if value in {'(', '[', '{'}:
            groups.append({'(': ')', '[': ']', '{': '}'}[value])
        elif value in {')', ']', '}'}:
            if not groups: return False
            if groups.pop() != value: raise _Unavailable('script_uninspectable')
        elif value == ',' and not groups:
            # DOMException(message, name): an AbortError mentioned only in the
            # message, a nested argument or a different error name is ordinary.
            return (index + 2 < end and tokens[index + 1].kind == 'string'
                and tokens[index + 1].value == 'AbortError'
                and tokens[index + 2].kind == 'punctuation'
                and tokens[index + 2].value in {')', ','})
    return False


def _synthetic_findings(script):
    tokens, found, replacements, abort_constructors = _tokens(script), [], 0, 0
    for index, token in enumerate(tokens):
        if token.kind != 'name' or token.value not in {'window', 'globalThis', 'self'}: continue
        following = tokens[index + 1:index + 5]
        if len(following) >= 3 and [t.value for t in following[:3]] == ['.', 'fetch', '=']:
            start = index + 4
        elif (len(following) == 4 and [t.value for t in following] == ['[', 'fetch', ']', '=']
              and following[1].kind == 'string'):
            start = index + 5
        else: continue
        replacements += 1
        if replacements > 64: raise _Unavailable('replacement_bound')
        span = _replacement_body(tokens, start)
        if span is None: continue
        for cursor in range(span[0], span[1] - 2):
            group = tokens[cursor:cursor + 3]
            if ([t.value for t in group] == ['new', 'Response', '(']
                    and all(t.kind == 'name' for t in group[:2])):
                found.append((group[0].line, 'fetch_replacement_constructs_response'))
            elif ([t.value for t in group] == ['new', 'DOMException', '(']
                    and all(t.kind == 'name' for t in group[:2])):
                abort_constructors += 1
                if abort_constructors > 64: raise _Unavailable('constructor_bound')
                if _abort_error_name(tokens, cursor, span[1]):
                    found.append((group[0].line, 'fetch_replacement_constructs_abort_error'))
            if len(found) >= 16: return sorted(set(found))
    return sorted(set(found))


def _browser_scripts(source):
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_NODES: raise _Unavailable('python_ast_bound')
    # Only executable browser API arguments, not docstrings, assertions, unit
    # fixture strings, or arbitrary new Response in unrelated production code.
    for node in nodes:
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in _BROWSER_CALLS):
            keyword_name = 'script' if node.func.attr == 'add_init_script' else 'expression'
            argument = node.args[0] if node.args else next(
                (keyword.value for keyword in node.keywords if keyword.arg == keyword_name), None)
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                yield argument.value, argument.lineno - 1, argument.end_lineno


def inspect_complaint_browser_http(root, task, declared_command, *, campaign_spec=None):
    """Inspect the pinned campaign's UI-task browser literals, without dispatch."""
    task_id = task.get('id') if isinstance(task, dict) else None
    # Native owns task identity. This only excludes other namespaces before
    # touching campaign-specific inputs; it grants no UX-task admission.
    if not isinstance(task_id, str) or not task_id.startswith('CIMP-UX-'):
        return None
    result = {'schema': 'complaint-browser-http-preflight@1', 'passed': False,
              'reason': 'browser_http_preflight_unavailable', 'findings': [], 'files': [],
              'candidate_executed': False, 'completion_authority': False,
              'scope': 'pinned UX campaign; direct fetch replacement Response or AbortError constructor only'}
    try:
        trusted = _candidate_bytes(_SOURCE_ROOT, SPEC_RELATIVE)
        if trusted is None or hashlib.sha256(trusted).hexdigest() != SPEC_SHA256:
            raise _Unavailable('trusted_spec_changed')
        spec = json.loads(trusted)
        canonical = next((t for t in spec['tasks'] if t['id'] == task_id), None)
        if canonical is None or not any(p.startswith(('static/', 'templates/')) for p in canonical['targets']):
            return None
        if canonical != task or (campaign_spec is not None and campaign_spec != spec):
            raise _Unavailable('task_or_campaign_contract_changed')
        if declared_command not in canonical['validation_commands']:
            raise _Unavailable('declared_command_changed')
        candidate = _candidate_bytes(Path(root), SPEC_RELATIVE)
        if candidate != trusted: raise _Unavailable('candidate_spec_changed')
        words = shlex.split(declared_command)
        tests = [word for word in words if re.fullmatch(r'tests/test_[A-Za-z0-9_]+\.py', word)]
        if len(tests) != 1 or tests[0] not in canonical['targets']:
            raise _Unavailable('declared_test_scope_unavailable')
        result['spec_sha256'] = SPEC_SHA256
        for relative in tests:
            data = _candidate_bytes(Path(root), relative)
            if data is None: raise _Unavailable('declared_test_unavailable')
            result['files'].append({'path': relative, 'sha256': hashlib.sha256(data).hexdigest()})
            for script, offset, end_line in _browser_scripts(data.decode('utf8', errors='strict')):
                for line, code in _synthetic_findings(script):
                    result['findings'].append({'path': relative, 'line': min(offset + line, end_line),
                        'code': code})
                    if len(result['findings']) >= 16: break
                if len(result['findings']) >= 16: break
        result['passed'] = not result['findings']
        result['reason'] = '' if result['passed'] else 'synthetic_browser_http_response'
    except (OSError, ValueError, TypeError, KeyError, SyntaxError, UnicodeError):
        # Never expose exception strings, script bytes, response bodies, or
        # absolute/private source locators in the Native retry diagnostic.
        result['reason'] = 'browser_http_preflight_unavailable'
    return result
