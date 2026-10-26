ADCTOX 모델 0.7: 처음부터 학습한 판정 모델 (앱 0.5.0 이상).

- **질환 판정 모델이 Gemma에서 이 프로젝트가 처음부터 학습한 모델(x2te)로 바뀐다.** 사전학습 가중치 없이 PubMed 초록, UMLS(제한 등급 0 출처), MONDO, HPO 텍스트로 학습한 BERT-base다.
- 처음 보는 질환은 연결된 MONDO 기록(정의, 상위 개념, 증상)을 읽어 판정한 장기를 쓴다. 이 결과는 `ScratchJudge/concepts.json`에 미리 계산되어 있다.
- **test, 영어 장기 macro-F1** (처음 보는 질환 gold_v0과 아는 질환 known의 평균): 0.723. 튜닝한 Gemma 판정 모델 0.711, 튜닝 안 한 Gemma 0.586. Gemma와의 차이는 95% 구간 안이다.
- 내려받는 새 파일은 `ScratchJudge/`(약 300 MB)뿐이다. 나머지는 모델 0.6 파일을 그대로 쓴다. `GemmaJudge/`는 이 묶음에 없다.
- 빠진 기능: 한국어 MONDO 이름에 없는 한국어 입력의 연결, 증상 → 질환 검색, 여러 뜻 고르기.

앱 0.4.x 이하는 이 묶음을 받지 않고 모델 0.6에 머문다.

```bash
adctox --update-app
adctox --update-models
```
