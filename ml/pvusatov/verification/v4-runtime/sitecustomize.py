"""Engineering probe guard: inference must never import fitting packages."""
import sys

FORBIDDEN_FITTING_ROOTS = frozenset(('sklearn', 'skl2onnx', 'joblib', 'training'))


class _NoFitting:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition('.')[0] in FORBIDDEN_FITTING_ROOTS:
            raise RuntimeError('fitting package imported by inference: ' + fullname)
        return None


sys.meta_path.insert(0, _NoFitting())
