import importlib.util
from pathlib import Path
import numpy as np
import pytest
s=importlib.util.spec_from_file_location('ceres_offline',Path(__file__).with_name('offline.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_registered_wcs_is_zero_based_and_east_left():
 grid=dict(center_deg=[15.,-5.],crpix_fits=[30.,30.],cdelt_deg=[-6.15/3600,6.15/3600],width=59,height=59,projection='TAN',coordinate_origin='zero_based_xy')
 w=m.grid_wcs(grid);x,y=w.world_to_pixel_values(15.,-5.);assert np.allclose([x,y],[29.,29.],atol=1e-8)
 x2,y2=w.world_to_pixel_values(15.001,-5.);assert x2<x

def test_matching_uses_all_epochs_and_existing_radius_not_one_near_point():
 expected=np.array([[1.,1.],[2.,1.],[3.,1.],[4.,1.]])
 candidate=dict(detections=[dict(frame_index=i,x=float(x),y=float(y))for i,(x,y)in enumerate(expected)])
 assert m.offsets(candidate,expected)['compatible']is True
 candidate['detections'][3]['y']=3.;assert m.offsets(candidate,expected)['compatible']is False
 candidate['detections']=candidate['detections'][:2];assert m.offsets(candidate,expected)['compatible']is False
