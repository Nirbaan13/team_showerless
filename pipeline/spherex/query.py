import time

import requests
import astropy.units as u
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
