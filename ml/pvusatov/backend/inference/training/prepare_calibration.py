"""Build a compact instrument-only ePSF bank from checksum-verified public products."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from astropy.io import fits


def spatial_subset(x,y,points_per_axis=8):
    selected=[]
    for yy in np.linspace(min(y),max(y),points_per_axis):
        for xx in np.linspace(min(x),max(x),points_per_axis):
            index=int(np.argmin((x-xx)**2+(y-yy)**2))
            if index not in selected:selected.append(index)
    return selected


def build(input_dir,output):
    input_dir=Path(input_dir);sources=json.loads((input_dir/'calibration-inputs.json').read_text())
    stamps=[];detectors=[];provenance=[]
    for source in sources:
        path=input_dir/Path(source['path']).name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:
            raise ValueError('calibration checksum mismatch')
        with fits.open(path,memmap=False)as h:
            table=h['EPSF'].data;header=h['EPSF'].header
            if header['OVSMPX']!=5 or header['OVSMPY']!=5:raise ValueError('unsupported calibration sampling')
            selected=spatial_subset(table['XCENTER'],table['YCENTER'])
            for index in selected:
                stamp=np.asarray(table[index]['EPSF'],dtype=np.float32)
                if stamp.shape!=(33,33)or not np.isfinite(stamp).all()or stamp.sum()<=0:
                    raise ValueError('invalid calibration PSF')
                stamps.append(stamp);detectors.append(source['detector'])
            provenance.append(dict(detector=source['detector'],url=source['url'],sha256=source['sha256'],
                                   filename=path.name,selected_table_rows=selected,
                                   selected_bin_xy=[[int(table[i]['BINX']),int(table[i]['BINY'])]for i in selected]))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(output,stamps=np.asarray(stamps),detectors=np.asarray(detectors),oversampling=5,
                        provenance_json=json.dumps(dict(kind='public_instrument_calibration',sources=provenance)))
    print(json.dumps(dict(stamps=len(stamps),output=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest()),indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',required=True)
    parser.add_argument('--output',default=str(Path(__file__).resolve().parent/'calibration'/'instrument-epsf-bank.npz'))
    args=parser.parse_args();build(args.input_dir,args.output)


if __name__=='__main__':main()
