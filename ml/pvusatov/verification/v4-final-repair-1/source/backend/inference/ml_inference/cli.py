"""Trusted subprocess entry point; bounded requests and atomic finite JSON."""
import argparse
import json
import os
from pathlib import Path
import sys
from .contracts import InferenceError, MAX_RESULT_BYTES
from .detector import DetectionLimitError


def atomic_result(output,result):
    payload=json.dumps(result,allow_nan=False,separators=(',',':')).encode('utf-8')
    if len(payload)>MAX_RESULT_BYTES:
        raise InferenceError('output_limit','The computed review exceeds the supported result size')
    output.mkdir(parents=True,exist_ok=True)
    temporary=output/'result.json.tmp'
    try:
        with temporary.open('wb') as target:
            target.write(payload); target.flush(); os.fsync(target.fileno())
        temporary.replace(output/'result.json')
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Run bounded CPU SPHEREx motion inference')
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    request={}; analysis_id='unknown'
    try:
        if args.request.stat().st_size>128*1024:
            raise InferenceError('workload_limit','The analysis request exceeds the supported size')
        request=json.loads(args.request.read_text(encoding='utf-8'))
        if isinstance(request,dict) and isinstance(request.get('analysis_id'),str):
            analysis_id=request['analysis_id'][:128]
        from .pipeline import run
        def progress(stage):
            print(json.dumps({'schema_version':1,'stage':stage}),file=sys.stderr,flush=True)
        result=run(request,args.output,progress)
        atomic_result(args.output,result)
        return 0
    except DetectionLimitError:
        code='workload_limit'; message='The linking search exceeds the supported computation budget'
    except InferenceError as error:
        code=error.code; message=str(error)
    except (OSError,UnicodeError,json.JSONDecodeError):
        code='invalid_request'; message='Unable to read a bounded JSON analysis request'
    except Exception:
        code='inference_failed'; message='The analysis worker could not complete the requested computation'
    result={'schema_version':1,'analysis_id':analysis_id,'error':{'code':code,'message':message,'retryable':False}}
    try:
        atomic_result(args.output,result)
    except OSError:
        pass
    print(json.dumps({'schema_version':1,'stage':'failed','code':code}),file=sys.stderr,flush=True)
    return 2
