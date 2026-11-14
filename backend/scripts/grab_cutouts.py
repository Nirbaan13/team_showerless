import argparse
import time
from pathlib import Path

from astropy.coordinates import SkyCoord
from astropy.table import Table



def main():
  p = argparse.ArgumentParser()
  p.add_argument("--ra", type = float, help = "RA in degrees")
  p.add_argument("--dec", type = float, help = "Dec in degrees")
  p.add_argument("--size", type = float, default = 0.05, help = "cutout size in degrees")
  p.add_argument("--name", default = "target")
  p.add_argument("--collection", default = DEFAULT)
  p.add_argument("--max", type = int, default = 0, help = "limit frames")
  p.add_argument("--list-collections", action = "store_true")

  a = p.parse_args()

  if a.list_collections:
    list_collections()
    return

  coordinates = SkyCoord(a.ra * u.deg, a.dec * u.deg)
  out_d = Path("data/cutouts") /a.name
  out_d.mkdir(parents = True, exist_ok = True)

  images = image_search(coordinates, a.size, a.collection)
  print(f"Found {len(images)} in '{a.collection}'")
  if len(images) == 0:
    return
  if a.max:
    images = images[: a.max]

  rows = []
  for i, row in enumerate(images):
    b_url = str(row["access_url"]).split("?")[0]
    fname = Path(b_url).name
    out = out_d / fname
    cutout_url = f"{b_url}?center={a.ra},{a.dec}&size={a.size}"
    if out.exists():  #So we cache
      status = "Cached"
    else:
      status = cutout(cutout_url, out)
      rows.append({
          "file": fname,
          "t_min_mjd": float(row["t_min"]) if "t_min" in row.colnames else float("nan"),
          "detector": detector(row),
          "status": status,
          "url": cutout_url,
        })
      print(f"[{i+1}/{len(images)}] {fname}  {status}")
      Table (rows = rows).write(out_d / "index.csv", overwrite = True)
      print(f"Index written to {out_d / 'index.csv'}")

if __name__ == '__main__':
  main()
    
        
          
          
          
    
