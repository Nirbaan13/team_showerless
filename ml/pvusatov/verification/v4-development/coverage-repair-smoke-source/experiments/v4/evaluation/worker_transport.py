"""Transport private worker failures as bounded, builtin-only error text.

Load this checked module before forking, then submit safe_call(function, task).
Successful calls pass through unchanged; scientific work remains in function.
"""
from __future__ import annotations

import traceback


def _text(value, limit):
    try:
        return str(value)[:limit]
    except Exception:
        return '<unprintable>'


def safe_call(function, task):
    """Preserve diagnostics without requiring the parent to import error types."""
    try:
        return function(task)
    except Exception as error:
        kind = type(error)
        identity = _text(kind.__module__ + '.' + kind.__qualname__, 1024)
        code = _text(getattr(error, 'code', None), 512)
        message = _text(error, 4096)
        diagnostic = traceback.TracebackException.from_exception(
            error, limit=20, lookup_lines=False, capture_locals=False)
        trace = ''.join(diagnostic.format(chain=False))
        header = f'Worker failure: {identity}; code={code}; message={message}\n'
        # Only a builtin str enters RuntimeError.args. Neither the original
        # exception nor its private class/module is serialized to the parent.
        raise RuntimeError(header + trace[:16384 - len(header)]) from None
