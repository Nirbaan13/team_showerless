"""Final summary guards use toy dictionaries or DEVELOPMENT caches only."""
import importlib.util
from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path

SPEC=importlib.util.spec_from_file_location('summarize_results',Path(__file__).with_name('summarize_results.py'))
summary=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(summary)

class SummaryGuards(unittest.TestCase):
    def test_mismatched_freeze_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'freeze'):
            summary.validate_run_header(dict(schema_version=1,kind='native',freeze_sha256='wrong',scope='final',versions={},options={},evaluation_complete=True),dict(_sha256='right',scope='final',versions={},options={}), 'native')
    def test_incomplete_manifest_is_rejected(self):
        freeze=dict(_sha256='right',scope='final',versions={},options={})
        run=dict(schema_version=1,kind='native',freeze_sha256='right',scope='final',versions={},options={},evaluation_complete=False)
        with self.assertRaisesRegex(ValueError,'complete'):summary.validate_run_header(run,freeze,'native')
    def test_missing_native_trial_is_rejected(self):
        fields=[dict(parent_id='final01',seed=2200001,trajectory_id='0.01-0',speed_px_hour=.01,direction_id=0,brightness=3.)]
        with self.assertRaisesRegex(ValueError,'trial'):summary.validate_trial_plan(fields,'native',dict(parent_id='final01',seed=2200001),{})
    def test_manifest_completion_cannot_hide_trial_error(self):
        field=dict(matches=[],matched_geometry=[],error={'phase':'detection'},truth_count_known=True,peak_cap_reached=False)
        with self.assertRaisesRegex(ValueError,'runtime'):summary.recompute_summary([field],False)
    def test_unknown_truth_is_rejected(self):
        field=dict(matches=[],matched_geometry=[],error=None,truth_count_known=False,peak_cap_reached=False)
        with self.assertRaisesRegex(ValueError,'truth'):summary.recompute_summary([field],False)
    def test_missing_manifest_output_is_rejected(self):
        freeze=dict(_sha256='right',scope='final',versions={},options={},native={'parents':[{'parent_id':'final01'}]})
        run=dict(schema_version=1,kind='native',freeze_sha256='right',scope='final',versions={},options={},evaluation_complete=True,outputs=[])
        with tempfile.TemporaryDirectory()as d:
            p=Path(d)/'run.json';p.write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError,'missing cache'):summary.read_run(p,freeze,'native')
    def test_cache_byte_hash_mismatch_is_rejected(self):
        freeze=dict(_sha256='right',scope='final',versions={},options={},native={'parents':[{'parent_id':'final01'}]})
        with tempfile.TemporaryDirectory()as d:
            cache=Path(d)/'final01-primary-baseline.json.gz';cache.write_bytes(b'changed cache')
            run=dict(schema_version=1,kind='native',freeze_sha256='right',scope='final',versions={},options={},evaluation_complete=True,
                     outputs=[dict(path=str(cache),sha256='0'*64,summary={})])
            p=Path(d)/'run.json';p.write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError,'cache byte hash'):summary.read_run(p,freeze,'native')
    def test_geometry_diagnostic_preserves_all_candidate_rows_and_main_labels(self):
        a=dict(seed=1,truth_count=2,expected_xy=[[[0.,0.],[4.,0.]],[[0.,0.],[1.,0.]]],matches=[1,0],scores=[.9,.8])
        result=summary.geometry_pair({'baseline':[a],'candidate':[a]},'synthetic')
        self.assertEqual(a['matches'],[1,0]);self.assertEqual(a['truth_count'],2)
        self.assertEqual(result['baseline'][0]['matches'],[-1,0]);self.assertEqual(len(result['baseline'][0]['scores']),2)
        self.assertEqual(result['baseline'][0]['truth_count'],1)
    def test_native_frame_hash_cannot_be_reassociated_with_another_obsid(self):
        dev=summary.DEV_ROOT;path=dev/'freeze-development.json'
        freeze,_=summary.verify_freeze(path,summary.digest(path),development=True)
        cache=summary.read_json(dev/'native/validation01-primary-baseline.json.gz')
        parent=freeze['native']['parents'][0]
        # The small DEV downloads schema predates obs_id; add the independently
        # recorded prepared physical IDs to exercise the final mapping guard.
        lookup={frame['sha256']:frame['physical_observation_id']for frame in cache['frames']}
        parent['_downloads']=[{**row,'obs_id':lookup[row['sha256']]}for row in parent['_downloads']]
        cache['frames'][0]['physical_observation_id'],cache['frames'][1]['physical_observation_id']=cache['frames'][1]['physical_observation_id'],cache['frames'][0]['physical_observation_id']
        with self.assertRaisesRegex(ValueError,'association'):summary.cache_metadata(cache,freeze,'native',parent,'primary','baseline')
    def native_dev(self):
        dev=summary.DEV_ROOT;path=dev/'freeze-development.json'
        freeze,_=summary.verify_freeze(path,summary.digest(path),development=True)
        cache=summary.read_json(dev/'native/validation01-primary-baseline.json.gz')
        parent=freeze['native']['parents'][0]
        return cache,freeze,parent
    def synthetic_dev(self):
        return summary.read_json(summary.DEV_ROOT/'synthetic/synthetic-primary-baseline.json.gz')
    def test_absolute_native_date_shift_rejected(self):
        cache,freeze,parent=self.native_dev()
        for frame in cache['frames']:frame['midpoint_mjd']+=1000
        with self.assertRaisesRegex(ValueError,'absolute'):summary.cache_metadata(cache,freeze,'native',parent,'primary','baseline')
    def test_native_utc_disagreement_rejected(self):
        cache,freeze,parent=self.native_dev();cache['frames'][0]['midpoint_utc']='2030-01-01T00:00:00.000Z'
        with self.assertRaisesRegex(ValueError,'UTC'):summary.cache_metadata(cache,freeze,'native',parent,'primary','baseline')
    def test_synthetic_times_shape_mode_and_metadata_rejected(self):
        original=self.synthetic_dev()['fields'][2]
        changes=[('times_hours',[]),('registered_shape',[3,1,1]),('mode','bogus'),('metadata',{})]
        for key,value in changes:
            with self.subTest(key=key):
                field=deepcopy(original);field[key]=value
                with self.assertRaises(ValueError):summary.validate_field(field,'synthetic')
    def test_positive_rows_require_exact_complete_geometry(self):
        original=next(f for f in self.synthetic_dev()['fields']if any(m>=0 for m in f['matches']))
        for change in ['missing','duplicate','wrong_span','wrong_offset']:
            with self.subTest(change=change):
                field=deepcopy(original)
                if change=='missing':field['matched_geometry']=[]
                elif change=='duplicate':field['matched_geometry'].append(deepcopy(field['matched_geometry'][0]))
                elif change=='wrong_span':field['matched_geometry'][0]['true_displacement_px']+=10
                else:field['matched_geometry'][0]['max_offset_px']+=10
                with self.assertRaisesRegex(ValueError,'geometry'):summary.validate_field(field,'synthetic')
    def test_cross_profile_latents_equal_but_attribution_and_candidates_may_differ(self):
        cache,_,_=self.native_dev();registry={}
        summary.validate_shared_latents(cache,'native',registry)
        changed=summary.read_json(summary.DEV_ROOT/'native/validation01-secondary-candidate.json.gz')
        self.assertTrue(any(a['matches']!=b['matches']for a,b in zip(cache['fields'],changed['fields'])))
        f=changed['fields'][0];f['attribution_eligible']=False;f['preexisting_control_match']=True
        summary.validate_shared_latents(changed,'native',registry)
        for column in ['expected_xy','truth_count']:
            bad=deepcopy(changed)
            if column=='expected_xy':bad['fields'][0][column][0][0]+=1
            else:bad['fields'][0][column]+=1
            with self.assertRaisesRegex(ValueError,'shared latent'):summary.validate_shared_latents(bad,'native',registry)
        bad=deepcopy(changed);bad['times_hours'][1]+=1
        with self.assertRaisesRegex(ValueError,'shared latent'):summary.validate_shared_latents(bad,'native',registry)
    def test_synthetic_cross_profile_full_metadata_and_time_equality(self):
        cache=self.synthetic_dev();registry={};summary.validate_shared_latents(cache,'synthetic',registry)
        for key in ['metadata','times_hours','registered_shape']:
            bad=deepcopy(cache);bad['fields'][2][key]=None
            with self.assertRaisesRegex(ValueError,'shared latent'):summary.validate_shared_latents(bad,'synthetic',registry)
    def test_clustered_bootstrap_counts_parents_not_derivatives(self):
        paired=summary.load_paired(Path(__file__).resolve().parents[2]/'backend/inference')
        fields=[dict(parent_id=p,seed=seed,trajectory_id=str(i),brightness=3.,truth_count=1,matches=[0])for p,seed in [('a',1),('b',2)]for i in range(150)]
        report=paired.paired_report(fields,fields,[[.5]]*300,[[.5]]*300,bootstrap_samples=20)
        self.assertEqual(report['all_planned']['independent_groups'],2)
        self.assertEqual(report['all_planned']['trials'],300)
        self.assertEqual(report['all_planned']['paired_parent_ci95_top1'],[0.,0.])

if __name__=='__main__':unittest.main()
