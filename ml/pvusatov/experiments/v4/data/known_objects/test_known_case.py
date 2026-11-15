"""Portable archived known-case metadata audit, without original paths/FITS."""
from pathlib import Path
import importlib.util,shutil
import pytest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('known_case_auditor',HERE/'audit_known_case.py');auditor=importlib.util.module_from_spec(spec);spec.loader.exec_module(auditor)

def test_portable_relocation_has_no_native_or_original_path_reads(tmp_path,monkeypatch):
    case=tmp_path/'relocated-case';shutil.copytree(HERE/'point-grid-0750',case);original=Path.open
    def opened(path,*a,**kw):
        if not path.resolve().is_relative_to(case.resolve()):raise AssertionError('outside relocated capsule: '+str(path))
        if path.suffix.lower()in('.fits','.fit','.fts'):raise AssertionError('native bytes opened')
        return original(path,*a,**kw)
    monkeypatch.setattr(Path,'open',opened);result=auditor.audit(case)
    assert result['status']=='PASS'and result['query_responses']==90 and result['physical_exposures']==4

def test_changed_published_xml_bytes_reject(tmp_path):
    case=tmp_path/'case';shutil.copytree(HERE/'point-grid-0750',case);path=next((case/'evidence').glob('*.xml.gz'));value=bytearray(path.read_bytes());value[len(value)//2]^=1;path.write_bytes(value)
    with pytest.raises((AssertionError,OSError,EOFError)):auditor.audit(case)
