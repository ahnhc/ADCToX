"""Application and model-runtime compatibility versions (Ubuntu and Windows share them)."""
APP_VERSION = "0.5.3"
RUNTIME_API = 1
REPOSITORY = "ahnhc/ADCToX"
# stable3.json: model bundles with the from-scratch organ judge (model 0.7+, ScratchJudge/), read by app 0.5+.
# stable2.json stays at the Gemma bundles (model 0.5-0.6) for apps 0.3.8-0.4.x, and stable.json at 0.4 for apps up to 0.3.7:
# each older updater rejects the folder that came after it
MODEL_MANIFEST_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/main/releases/models/stable3.json"
APP_MANIFEST_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/main/releases/app/stable.json"
