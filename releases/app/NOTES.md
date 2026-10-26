ADCTOX 0.5.0: 처음부터 학습한 판정 모델.

- 모델 0.7(`ScratchJudge/`)이 있으면 기저질환 이름의 질환 연결과 장기 판정을 이 프로젝트가 처음부터 학습한 모델이 한다. 자세한 수치는 모델 0.7 노트에 있다.
- AI 장기 분석 화면: 단계 줄이 `BioLORD ── Organ judge ── MLP`가 된다. Read as 칸 끝에 장기를 정한 근거가 붙는다: `label`(장기 라벨표), `record`(MONDO 기록을 읽은 판정), `name`(입력 이름만 본 판정).
- 앱 0.5는 `stable3.json` 모델 채널을 읽는다. 업데이트 후 `adctox --update-models`로 모델 0.7을 받는다.

```bash
adctox --update-app
adctox --update-models
```
