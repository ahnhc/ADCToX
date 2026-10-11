"""Rebuild the persistent caches the ML scripts read, from the collaborator workbooks in data/raw/atlas.

Run once:  /data/hyeongchanahn/envs/adctox/bin/python -I ml/prepare_data.py
The workbooks are not redistributed (docs/TEAMMATE_DATA_USE.md); neither are these caches.
"""
import pandas as pd, warnings
warnings.filterwarnings("ignore")
RAW = "/home/hyeongchanahn/CONI/adctox/data/raw/atlas/2026-10-10/"; C = "/data/hyeongchanahn/adctox/ml_cache/"
pd.read_excel(RAW + "finngen_outcome_mapping.xlsx", "Mapped_Data").to_parquet(C + "finngen.parquet")
x = pd.ExcelFile(RAW + "adc_db.xlsx"); x.parse("TOXICITY").to_pickle(C + "tox.pkl"); x.parse("ADC_MASTER").to_pickle(C + "master.pkl")
print("caches written to", C)
