import importlib.util,io,unittest
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('native_headers',Path(__file__).with_name('headers.py'));m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)
def header(cards):return ''.join([f'{key:<8}= {value:<70}'[:80]for key,value in cards]+['END'.ljust(80)]).ljust(2880).encode()
class HeaderOnly(unittest.TestCase):
    def test_image_payload_is_skipped_not_read(self):
        first=header([('SIMPLE','T'),('BITPIX','8'),('NAXIS','0')]);second=header([('XTENSION',"'IMAGE'"),('BITPIX','-32'),('NAXIS','2'),('NAXIS1','2'),('NAXIS2','3'),('PCOUNT','0'),('GCOUNT','1'),('EXTNAME',"'IMAGE'")])
        data=first+second+b'FORBIDDEN PIXEL PAYLOAD'.ljust(2880,b'X')
        class Traced(io.BytesIO):
            def read(self,n=-1):
                if self.tell()>=5760:raise AssertionError('pixel read attempted')
                return super().read(n)
        rows=m.scan(Traced(data),len(data));self.assertEqual([r['name']for r in rows],['PRIMARY','IMAGE']);self.assertEqual(rows[1]['data_bytes'],24)
    def test_truncated_extension_is_rejected(self):
        data=header([('SIMPLE','T'),('BITPIX','8'),('NAXIS','2'),('NAXIS1','100'),('NAXIS2','100')])
        with self.assertRaises(ValueError):m.scan(io.BytesIO(data),len(data))
if __name__=='__main__':unittest.main()
