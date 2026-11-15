"""Metadata-only freeze builder guards; fixtures are tiny byte files, never FITS."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC=importlib.util.spec_from_file_location('build_freeze',Path(__file__).with_name('build_freeze.py'))
builder=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(builder)

class MetadataGuards(unittest.TestCase):
    def row(self,path,obs='obs1'):
        return dict(path=str(path),sha256=builder.digest(path),bytes=path.stat().st_size,obs_id=obs,detector=1,t_min_mjd=1.,t_max_mjd=2.)
    def test_cross_parent_physical_obsid_is_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            f=Path(d)/'bytes';f.write_bytes(b'bytes');row=self.row(f)
            groups=[dict(parent_group_id=p,split=s,downloads=[row])for p,s in [('train01','train'),('final01','final')]]
            with self.assertRaisesRegex(ValueError,'cross-parent'):builder.audit_groups(groups)
    def test_changed_observation_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            f=Path(d)/'bytes';f.write_bytes(b'old');row=self.row(f);f.write_bytes(b'new')
            with self.assertRaisesRegex(ValueError,'byte hash'):builder.audit_groups([dict(parent_group_id='final01',split='final',downloads=[row])])
    def test_same_parent_variants_remain_one_physical_observation(self):
        with tempfile.TemporaryDirectory()as d:
            f=Path(d)/'bytes';f.write_bytes(b'bytes');row=self.row(f)
            groups=[dict(parent_group_id='final01',split='final',downloads=[row])]*2
            result=builder.audit_groups(groups)
            self.assertEqual(len(result),1);self.assertEqual(result[0]['parent_id'],'final01')
    def test_draft_is_rejected_before_any_science_or_file_discovery(self):
        with tempfile.TemporaryDirectory()as d:
            f=Path(d)/'draft.json';f.write_text('{"schema_version":1,"status":"draft","scope":"final","authorized_final":false}')
            runner=builder.load_runner(Path(__file__).resolve().parents[2]/'backend/inference')
            with self.assertRaisesRegex(ValueError,'status frozen'):runner.validate_freeze(f,builder.digest(f))

if __name__=='__main__':unittest.main()
