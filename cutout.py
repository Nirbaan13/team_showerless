import argparse
import time
from pathlib import Path

import requests
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table
from astroquery.ipac.irsa import Irsa

DEFAULT = "spherex_qr" #May change based on data, pls check

def list_collections():
    tbl = Irsa.list_collections(servicetype = "SIA", filter ="spherex")
    tbl.pprint(max_lines = -1, max_width = -1)

def image_search(coordinates, deg, collection):
    res = Irsa.query_sia(pos=(coordinates, deg/2 * u.deg), collection = collection)
    if len(res) == 0:
      return res
    if "dataproduct_subtype" in res.colnames:
      res = res[res["dataproduct_subtype"] == "science"]
    if "t_min" in res.colnames:
      res.sort("t_min")
    return res
          
"""Finds overlapping spectral images @ position from IRSA SIA"""

def detector(row):
    for col in ("energy_bandpassname", "instrument_name"):
        if col in row.colnames:
            return str(row[col])
    return ""

def cutout(url, out, retries = 3):
    for tries in range(1, retries + 1):
        try:
            r = requests.get(url, timeout = 120)
            r.raise_for_status()
            out.write_bytes(r.content)
            fits.open(out).close()
            return "good"
        except Exception as e:

            if tries == retries:
                return f"failure: {e}"
            time.sleep(2 * tries)


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
    
        
          
          
          
    
