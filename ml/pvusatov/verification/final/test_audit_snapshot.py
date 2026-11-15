"""Portable snapshot audit guards; no native data or original /tmp paths used."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('audit_snapshot',Path(__file__).with_name('audit_snapshot.py'))
audit=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(audit)

class PortableAuditGuards(unittest.TestCase):
    def test_snapshot_traversal_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            with self.assertRaisesRegex(ValueError,'escape'):audit.snapshot_location(Path(d),'../outside')
    def test_opaque_byte_corruption_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            p=Path(d)/'cache';p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'hash'):audit.verify_file(p,'0'*64,len(b'changed'))
    def test_relocation_translates_namespaced_suffix_only(self):
        with tempfile.TemporaryDirectory()as d:
            namespace=Path(d)/'ml/pvusatov'
            self.assertEqual(audit.translate('/old/checkout/ml/pvusatov/backend/inference/example.py',namespace),namespace/'backend/inference/example.py')
            with self.assertRaisesRegex(ValueError,'external'):audit.translate('/tmp/original-observations.fits',namespace)
    def test_changed_primary_count_rejected(self):
        with self.assertRaisesRegex(ValueError,'metric'):audit.compare({'all_planned':{'candidate':{'top1':2}}},{'all_planned':{'candidate':{'top1':3}}})
    def test_roundoff_tolerance_does_not_hide_changed_denominators(self):
        audit.compare({'delta':.1+1e-15,'trials':2700},{'delta':.1,'trials':2700})
        with self.assertRaisesRegex(ValueError,'metric'):audit.compare({'trials':2699},{'trials':2700})

if __name__=='__main__':unittest.main()
