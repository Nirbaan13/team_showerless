"""Offline portability check with every original data/metadata path forbidden."""
import importlib.util,json,shutil
from pathlib import Path

DATA=Path(__file__).resolve().parent

def test_portable_exact_selection_replay_needs_only_published_metadata(tmp_path,monkeypatch,capsys):
    namespace=tmp_path/'checkout/ml/pvusatov';destination=namespace/'experiments/v4/data'
    shutil.copytree(DATA,destination,ignore=shutil.ignore_patterns('physics_validation','__pycache__'))
    plan=json.loads((DATA/'partition-plan.json').read_text())
    for reference in plan['input_provenance']:
        relative=reference['path'].split('/ml/pvusatov/',1)[1];source=DATA.parents[2]/relative;target=namespace/relative
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
    spec=importlib.util.spec_from_file_location('relocated_v4_cohort_replay',destination/'replay_cohort.py')
    replay=importlib.util.module_from_spec(spec);spec.loader.exec_module(replay)
    original=Path.open
    def only_relocated_metadata(path,*args,**kwargs):
        location=path.resolve()
        if not location.is_relative_to(namespace)or location.suffix.lower()in ['.fits','.fit','.fts']:
            raise AssertionError('Attempted nonportable or native-file read: '+str(location))
        return original(path,*args,**kwargs)
    with monkeypatch.context()as scoped:
        scoped.setattr(Path,'open',only_relocated_metadata)
        replay.main()
    result=json.loads(capsys.readouterr().out)
    assert result['passes']is True
    assert result['selected_physical_observations']==224
    assert result['exact_query_archives_verified']==56
    assert result['raw_native_files_opened']is False
