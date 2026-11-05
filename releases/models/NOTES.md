ADCTOX 모델 0.8: 판정 모델과 MONDO 이름 색인만 (앱 0.6.11 이상, 305 MB).

- 판정 모델(x2te, `ScratchJudge/`)은 모델 0.7과 같은 파일이다. 새로 받는 파일은 `mondo_index.npz`(3.2 MB, 임베딩 없이 MONDO와 HPO 이름, 장기, 한국어 KCD 이름)뿐이다.
- BioLORD-2023, SapBERT, `vuln_biolord.pt`가 빠졌다. 모델 0.7은 1.4 GB였다.
- 앱 0.6.10 이하는 이 묶음을 받지 않고 모델 0.7에 머문다.

```bash
adctox --update-app
adctox --update-models
```
