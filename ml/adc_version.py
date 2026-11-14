"""Application and model-runtime compatibility versions (Ubuntu and Windows share them)."""
APP_VERSION = "0.9.4"
RUNTIME_API = 1
REPOSITORY = "ahnhc/ADCToX"
# stable4.json: the organ judge and a name index only (model 0.8+, no BioLORD or SapBERT), read by app 0.6.11+.
# stable3.json stays at model 0.7 (ScratchJudge/ plus the encoders) for apps 0.5-0.6.10, whose updater requires the encoders.
# stable2.json stays at the Gemma bundles (model 0.5-0.6) for apps 0.3.8-0.4.x, and stable.json at 0.4 for apps up to 0.3.7:
# each older updater rejects the folder that came after it
MODEL_MANIFEST_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/main/releases/models/stable4.json"
APP_MANIFEST_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/main/releases/app/stable.json"
