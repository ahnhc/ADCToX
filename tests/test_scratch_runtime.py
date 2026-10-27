"""The from-scratch organ judge's app runtime (ml/scratch_runtime.py) on a tiny random model folder, and how its rows enter the
app's linking (recommend._scratch_link). The real folder is checked against the research code by ml/scratch_export.py."""
import json, sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))
torch = pytest.importorskip("torch"); T = pytest.importorskip("transformers")
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]


@pytest.fixture
def folder(tmp_path):
    from tokenizers import Tokenizer, models, pre_tokenizers
    from safetensors.torch import save_file
    vocab = {w: i for i, w in enumerate(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "tuberculosis", "glaucoma", "xyz"])}
    tk = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]")); tk.pre_tokenizer = pre_tokenizers.Whitespace(); tk.save(str(tmp_path / "tokenizer.json"))
    T.PreTrainedTokenizerFast(tokenizer_object=tk, pad_token="[PAD]", unk_token="[UNK]").save_pretrained(tmp_path)
    cfg = T.BertConfig(vocab_size=len(vocab), hidden_size=16, num_hidden_layers=1, num_attention_heads=2, intermediate_size=32); cfg.save_pretrained(tmp_path)
    torch.manual_seed(0); bb = T.BertModel(cfg, add_pooling_layer=False)
    sd = {"bb." + k: v for k, v in bb.state_dict().items()}
    for n, k in (("organ", 13), ("valid", 1), ("proj", 8)):
        lin = torch.nn.Linear(16, k); sd[f"{n}.weight"], sd[f"{n}.bias"] = lin.weight.data, lin.bias.data
    sd["valid.bias"] = torch.tensor([20.0]); save_file({k: v.half().contiguous() for k, v in sd.items()}, str(tmp_path / "weights.safetensors"))
    json.dump(dict(axes=AXES, temp=[1.0] * 13, thr=[0.5] * 13, vthr=0.5, theta=-1.0, maxlen=16, mondo_first=0.02), open(tmp_path / "judge.json", "w"))
    import scratch_runtime as SR
    SR._M.clear(); json.dump({}, open(tmp_path / "concepts.json", "w")); np.savez(tmp_path / "index.npz", E=np.zeros((1, 8), np.float16), ids=np.array(["X:1"]))
    M = SR.load(str(tmp_path)); _, _, va = SR._outputs(M, ["tuberculosis", "glaucoma"]); SR._M.clear()
    np.savez(tmp_path / "index.npz", E=np.vstack([va, -va[:1]]).astype(np.float16), ids=np.array(["MONDO:1", "HP:2", "MONDO:3"]))
    json.dump({"MONDO:1": ["tuberculosis", ["pulmonary", "infectious_immune"], "record"], "HP:2": ["Glaucoma", [], ""], "MONDO:3": ["other", ["renal"], "label"]},
              open(tmp_path / "concepts.json", "w"))
    return str(tmp_path)


def test_rows_follow_the_rule(folder):
    import scratch_runtime as SR
    a, b = SR.judge(["tuberculosis", "glaucoma"], folder)
    assert a["concept"] == "MONDO:1" and a["organs"] == ["pulmonary", "infectious_immune"] and a["via"] == "record" and a["ok"]
    assert b["concept"] in ("HP:2", "MONDO:1", "MONDO:3")
    if b["concept"] == "HP:2": assert b["via"] == "name"                     # no organs of its own: the organ output on the text


def test_rows_enter_the_app_as_mondo_links_or_ai_judgments():
    import recommend as RC
    lk = RC._scratch_link(dict(concept="MONDO:1", name="tuberculosis", organs=["pulmonary"], via="record", valid=0.99, ok=True, sim=0.97))
    assert lk["mondo"] == "MONDO:1" and lk["axes"] == ["pulmonary"] and lk["gate"] and lk["judge_via"] == "record"
    lk = RC._scratch_link(dict(concept="HP:2", name="Glaucoma", organs=["ocular"], via="name", valid=0.99, ok=True, sim=0.9))
    assert lk["axes"] == [] and lk["judged"] == ["ocular"] and lk["sim"] == 0.0
    lk = RC._scratch_link(dict(concept=None, name="", organs=[], via=None, valid=0.1, ok=False, sim=0.2))
    assert lk["gate"] is False and not lk["axes"] and not lk.get("judged")
