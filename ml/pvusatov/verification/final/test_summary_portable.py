"""Summary guard regressions using published, namespaced fixtures only.

Historical test_summarize_results.py remains hash-bound to the original external
DEV environment. This file provides portable CI coverage without rewriting it.
Fixture path translations affect in-memory copies only; no artifact is changed.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

DIRECTORY=Path(__file__).resolve().parent
NAMESPACE=DIRECTORY.parents[1]

def module(name):
    spec=importlib.util.spec_from_file_location(name,DIRECTORY/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

summary=module('summarize_results');audit=module('audit_snapshot')

def local_json(path):
    path=Path(path).resolve()
    if not path.is_relative_to(NAMESPACE):raise AssertionError('portable fixture attempted external read: '+str(path))
    return audit.read_json(path)

class PortableSummaryGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        freeze_path=NAMESPACE/'verification/final/frozen-331c6b1/final-freeze.json'
        audit.verify_file(freeze_path,audit.FREEZE_SHA)
        cls.freeze=local_json(freeze_path);cls.freeze['_sha256']=audit.FREEZE_SHA
        cls.freeze['package_root']=str(NAMESPACE/'backend/inference')
        for role in summary.ROLES:
            for key in ['artifact','metadata']:
                ref=cls.freeze['models'][role][key]
                ref['path']=str(audit.translate(ref['path'],NAMESPACE))
        cls.parent=cls.freeze['native']['parents'][0]
        cls.parent['_downloads']=local_json(audit.translate(cls.parent['downloads_manifest']['path'],NAMESPACE))
        snapshot=NAMESPACE/'artifacts/v3-final-331c6b1'
        cls.native=local_json(snapshot/'native/final01-primary-baseline.json.gz')
        cls.secondary=local_json(snapshot/'native/final01-secondary-candidate.json.gz')
        for cache in [cls.native,cls.secondary]:cache['model']=deepcopy(cls.freeze['models'][cache['system']])
        raw=local_json(snapshot/'synthetic/synthetic-primary-baseline.json.gz')
        cls.synthetic=deepcopy(next(field for field in raw['fields']if any(m>=0 for m in field['matches'])))
        # Retain just shared synthetic latents for cross-profile tests, not a
        # second copy of the candidate-heavy 2,000-field fixture.
        cls.synthetic_latents={key:raw[key]for key in summary.SOURCE_FIELDS['synthetic']}
        cls.synthetic_latents['fields']=[deepcopy(cls.synthetic)]
        del raw

    def test_published_positive_metadata_and_geometry_pass(self):
        original=summary.read_json
        try:
            summary.read_json=local_json
            summary.cache_metadata(deepcopy(self.native),self.freeze,'native',self.parent,'primary','baseline')
        finally:summary.read_json=original
        summary.validate_field(deepcopy(self.synthetic),'synthetic')
        summary.validate_field(deepcopy(self.native['fields'][0]),'native',self.native['times_hours'])

    def test_native_absolute_and_utc_times_rejected(self):
        original=summary.read_json
        try:
            summary.read_json=local_json
            for change in ['absolute','UTC']:
                with self.subTest(change=change):
                    cache=deepcopy(self.native)
                    if change=='absolute':
                        for frame in cache['frames']:frame['midpoint_mjd']+=1000
                    else:cache['frames'][0]['midpoint_utc']='2030-01-01T00:00:00.000Z'
                    with self.assertRaisesRegex(ValueError,change):summary.cache_metadata(cache,self.freeze,'native',self.parent,'primary','baseline')
        finally:summary.read_json=original

    def test_positive_matched_geometry_must_be_complete_and_accurate(self):
        for change in ['missing','duplicate','span','offset']:
            with self.subTest(change=change):
                field=deepcopy(self.synthetic)
                if change=='missing':field['matched_geometry']=[]
                elif change=='duplicate':field['matched_geometry'].append(deepcopy(field['matched_geometry'][0]))
                else:field['matched_geometry'][0]['true_displacement_px'if change=='span'else'max_offset_px']+=10
                with self.assertRaises(ValueError):summary.validate_field(field,'synthetic')

    def test_synthetic_time_shape_mode_and_full_metadata_required(self):
        for key,value in [('times_hours',[]),('registered_shape',[3,1,1]),('mode','bogus'),('metadata',{})]:
            with self.subTest(key=key):
                field=deepcopy(self.synthetic);field[key]=value
                with self.assertRaises(ValueError):summary.validate_field(field,'synthetic')

    def test_shared_latents_accept_different_candidates_and_attribution(self):
        registry={};summary.validate_shared_latents(self.native,'native',registry)
        changed=deepcopy(self.secondary)
        self.assertTrue(any(a['matches']!=b['matches']for a,b in zip(self.native['fields'],changed['fields'])))
        changed['fields'][0]['attribution_eligible']=False;changed['fields'][0]['preexisting_control_match']=True
        summary.validate_shared_latents(changed,'native',registry)
        for key in ['expected_xy','truth_count']:
            bad=deepcopy(changed)
            if key=='expected_xy':bad['fields'][0][key][0][0]+=1
            else:bad['fields'][0][key]+=1
            with self.assertRaisesRegex(ValueError,'shared latent'):summary.validate_shared_latents(bad,'native',registry)
        bad=deepcopy(changed);bad['times_hours'][1]+=1
        with self.assertRaisesRegex(ValueError,'shared latent'):summary.validate_shared_latents(bad,'native',registry)

    def test_synthetic_shared_generator_metadata_cannot_change(self):
        registry={};summary.validate_shared_latents(self.synthetic_latents,'synthetic',registry)
        for key in ['metadata','times_hours','registered_shape']:
            bad=deepcopy(self.synthetic_latents);bad['fields'][0][key]=None
            with self.assertRaisesRegex(ValueError,'shared latent'):summary.validate_shared_latents(bad,'synthetic',registry)

    def test_missing_trial_identity_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'trial'):summary.validate_trial_plan(self.native['fields'][:-1],'native',self.parent,self.freeze)

    def test_runtime_and_unknown_truth_failures_rejected(self):
        for error,truth in [({'phase':'detection'},True),(None,False)]:
            field=dict(matches=[],matched_geometry=[],error=error,truth_count_known=truth,peak_cap_reached=False)
            with self.assertRaises(ValueError):summary.recompute_summary([field],False)

    def test_incomplete_or_mismatched_run_rejected(self):
        run=dict(schema_version=1,kind='native',freeze_sha256=audit.FREEZE_SHA,scope='final',versions=self.freeze['versions'],options=self.freeze['options'],evaluation_complete=True)
        for key,value in [('evaluation_complete',False),('freeze_sha256','wrong')]:
            bad={**run,key:value}
            with self.assertRaises(ValueError):summary.validate_run_header(bad,self.freeze,'native')

    def test_physical_obsid_cannot_be_reassociated_with_other_hash(self):
        cache=deepcopy(self.native)
        cache['frames'][0]['physical_observation_id'],cache['frames'][1]['physical_observation_id']=cache['frames'][1]['physical_observation_id'],cache['frames'][0]['physical_observation_id']
        original=summary.read_json
        try:
            summary.read_json=local_json
            with self.assertRaisesRegex(ValueError,'association'):summary.cache_metadata(cache,self.freeze,'native',self.parent,'primary','baseline')
        finally:summary.read_json=original

    def test_clustered_bootstrap_uses_two_parents_not_three_hundred_derivatives(self):
        paired=summary.load_paired(NAMESPACE/'backend/inference')
        fields=[dict(parent_id=parent,seed=seed,trajectory_id=str(i),brightness=3.,truth_count=1,matches=[0])for parent,seed in [('a',1),('b',2)]for i in range(150)]
        report=paired.paired_report(fields,fields,[[.5]]*300,[[.5]]*300,bootstrap_samples=20)
        self.assertEqual(report['all_planned']['trials'],300)
        self.assertEqual(report['all_planned']['independent_groups'],2)
        self.assertEqual(report['all_planned']['paired_parent_ci95_top1'],[0.,0.])

if __name__=='__main__':unittest.main()
