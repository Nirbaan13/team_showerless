from pathlib import Path
import importlib.util,unittest
SPEC=importlib.util.spec_from_file_location('v4acquire',Path(__file__).with_name('acquire.py'));module=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(module)

class SelectionGuards(unittest.TestCase):
    def rows(self):
        return [dict(obs_id=f'obs{i}',t_min=str(60000+(i*.02 if i<4 else i-2)/24),t_max=str(60000+(i*.02 if i<4 else i-2)/24+.001),energy_bandpassname='SPHEREx-D1',access_url=f'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/{i}.fits')for i in range(12)]
    def test_excluded_physical_observation_never_selected(self):
        result=module.select(dict(group_id='a',parent_id='a',split='train',center=[0,0],preferred_detector=1),self.rows(),{'obs0'})
        self.assertNotIn('obs0',{r['obs_id']for r in result['exposures']})
    def test_processing_versions_do_not_count_as_independent_epochs(self):
        rows=self.rows()[:2];rows+=[{**rows[0],'access_url':'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/other.fits'}]*8
        result=module.select(dict(group_id='a',parent_id='a',split='final',center=[0,0],preferred_detector=1),rows,set())
        self.assertIn('error',result)

if __name__=='__main__':unittest.main()
