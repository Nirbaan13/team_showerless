"""Verify loaded own Python code/defaults/constants against freshly compiled text.

Timestamp-and-size pyc validation alone cannot establish source execution when a
same-size edit shares the timestamp second. This guard runs BEFORE cache reads.
"""
from pathlib import Path
import hashlib,inspect,json,types


def canonical(value):
    if isinstance(value,types.CodeType):
        return dict(code=value.co_code.hex(),constants=canonical(value.co_consts),names=value.co_names,varnames=value.co_varnames,freevars=value.co_freevars,cellvars=value.co_cellvars,args=[value.co_argcount,value.co_posonlyargcount,value.co_kwonlyargcount],flags=value.co_flags,exceptiontable=value.co_exceptiontable.hex(),firstlineno=value.co_firstlineno,linetable=value.co_linetable.hex())
    if isinstance(value,slice):return dict(slice=canonical((value.start,value.stop,value.step)))
    if isinstance(value,bytes):return dict(bytes=value.hex())
    if isinstance(value,Path):return dict(path=str(value))
    if isinstance(value,dict):return {str(k):canonical(v)for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [canonical(v)for v in value]
    if isinstance(value,frozenset):return dict(frozenset=sorted([canonical(v)for v in value],key=repr))
    if isinstance(value,complex):return dict(complex=[value.real,value.imag])
    if value is Ellipsis:return dict(ellipsis=True)
    if value is None or type(value)in(bool,int,float,str):return value
    raise TypeError('unsupported semantic constant '+type(value).__name__)


def digest(value):return hashlib.sha256(json.dumps(canonical(value),sort_keys=True).encode()).hexdigest()


def functions(module):
    result={}
    for name,value in vars(module).items():
        if inspect.isfunction(value)and value.__module__==module.__name__:
            result[name]=digest((value.__code__,value.__defaults__,value.__kwdefaults__))
        elif inspect.isclass(value)and value.__module__==module.__name__:
            for method,function in vars(value).items():
                if inspect.isfunction(function):result[name+'.'+method]=digest((function.__code__,function.__defaults__,function.__kwdefaults__))
    return result


def constants(module):
    result={}
    for name,value in vars(module).items():
        if not name.isupper():continue
        try:result[name]=canonical(value)
        except TypeError:continue
    return result


def verify_module(module):
    path=Path(module.__file__);blob=path.read_bytes();fresh=types.ModuleType(module.__name__+'.__verified_source__');fresh.__file__=str(path);fresh.__package__=module.__package__
    exec(compile(blob,str(path),'exec',dont_inherit=True),fresh.__dict__)
    actual=functions(module);expected=functions(fresh)
    if actual!=expected:raise ValueError('loaded bytecode/defaults do not match exact source: '+str(path))
    actual_globals=constants(module);expected_globals=constants(fresh)
    if actual_globals!=expected_globals:raise ValueError('loaded semantic globals do not match exact source: '+str(path))
    return dict(path=str(path),source_sha256=hashlib.sha256(blob).hexdigest(),function_count=len(actual),function_fingerprints=actual,semantic_globals_sha256=digest(actual_globals),loaded_code_matches_fresh_source=True)
