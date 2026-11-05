"""The Windows kit script (for building the package on a PC) checks everything it downloads against a pinned hash."""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import build_windows_release as B


def test_kit_script_verifies_get_pip_against_a_pinned_commit():
    text = B.BUILD_PS1.format(embed_sha=B.EMBED[1], get_pip=B.GET_PIP[0], get_pip_sha=B.GET_PIP[1], release="0.0.0-x", torch="2.11.0")
    assert "bootstrap.pypa.io" not in text and B.GET_PIP[1] in text
    assert "/get-pip/" + B.GET_PIP[0].split("/get-pip/")[1].split("/")[0] in B.GET_PIP[0]
    assert len(B.GET_PIP[0].split("/get-pip/")[1].split("/")[0]) == 40
    assert text.index("get-pip.py checksum mismatch") < text.index("& ADCTOX\\python\\python.exe get-pip.py")
