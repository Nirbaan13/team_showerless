import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from astropy.visualization import ZScaleInterval

path = sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spherex.cleaning import
load_clean_cutout


def main()
  if len(sys.argv) < 2: 
    print("python scripts/inspect_cutout.py")
    return

path = Path(sys.argv[1])

  img, bad, clean_m, meta = load_clean_cutout(path, show_info = True)
  print(\nMetadata:", meta)

  fig, ax = plt.subplots(1, 3, figsize = (7,4))
  panels = [
    (img, "IMAGE"),
    (bad, f"FLAGS ({meta['flag_pix_perc']}%"),
    (clean_m, "IMAGE - ZODI"),
    for a, (data, title) in zip(ax, panels):
      if data.dtype == bool:
        a.imshow(data, origin = "lower", cmap = "gray")
      else:
        finite = data[np.isfinite(data)]
        lo, hi = ZScaleInterval().get_limits(finite) if finite.size else (0,1)
        a.imshow(data, origin = "lower", cmap = "gray", vmin = lo, vmax = hi)
      a.set_title(title)
    plt.tight_layout
    plt.show()

if__name__ == "__main__":
  main()
