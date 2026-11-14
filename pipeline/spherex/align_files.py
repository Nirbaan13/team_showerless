import numpy as np
from reproject import reproject_interp

from spherex.cleaning import load_clean_cutout

def align_ref(paths):
  aligned = []
  metas = []
  ref_wcs = none
  ref_shape = none

  for i, p in enumerate(paths):
    _, _, clean_m, meta = load_clean_cutout(p)
    if i == 0:
      ref_wcs = meta['wcs']
      ref_shape = clean_m.shape
      aligned_frames.append(clean_m)
    else:
      warped, _ = reprojet_interp((clean_m, meta['wcs']), ref_wcs, shape_out = ref_shape)
      aligned.append(warped)
    metas.append(meta)

  return np.array(aligned), metas, ref_wcs)

def sub_med_ref(aligned):
  med_sky = np.nanmedian(aligned_stack, axis = 0)
  diff_stack = aligned_stack - med_sky
  return diff_stack, med_sky
