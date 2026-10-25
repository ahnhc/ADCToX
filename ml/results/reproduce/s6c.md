# 재현 결과: s6c

- 단계: S6 E4B English first, 3 epochs
- 메모: E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss, 3 epochs instead of 2
- 분할: dev
- seed: 7
- 뺀 데이터: gen_ko,ko2,kotypo,ko3,mondo_ko,kcd,umls
- 만든 시각: 2026-10-21 17:45

## 튜닝 안 한 Gemma와 비교

| 시스템 | 영어 장기 F1 | 한국어 장기 F1 | 영어 개념 | 한국어 개념 | 무효 수락 | 영어 Δ vs base [95%] | 한국어 Δ vs base [95%] |
|---|---|---|---|---|---|---|---|
| base_e4b | 0.852 | 0.796 | 0.604 | 0.543 | 0.000 | – | – |
| single_s6cs7 | 0.721 | 0.556 | 0.057 | 0.004 | 0.067 | -0.131 [-0.221, -0.051] | -0.240 [-0.352, -0.132] |

## 장기별 F1 (목표: 모든 장기 0.95 이상)

seed 평균. ✓는 목표 이상.

| 장기 | base 영어 | base 한국어 | 튜닝 영어 | 튜닝 한국어 |
|---|---|---|---|---|
| haematologic | 0.93 | 0.85 | 0.69 | 0.44 |
| hepatic | 0.96 | 0.95 | 0.86 | 0.74 |
| cardiovascular | 0.95 | 0.90 | 0.76 | 0.69 |
| pulmonary | 0.76 | 0.69 | 0.68 | 0.62 |
| renal | 0.96 | 0.89 | 0.70 | 0.33 |
| gastrointestinal | 0.90 | 0.93 | 0.86 | 0.65 |
| neurologic | 0.80 | 0.76 | 0.71 | 0.44 |
| ocular | 0.86 | 0.74 | 0.81 | 0.67 |
| dermatologic | 0.87 | 0.79 | 0.67 | 0.42 |
| metabolic_endocrine | 0.79 | 0.75 | 0.81 | 0.62 |
| musculoskeletal | 0.83 | 0.76 | 0.70 | 0.62 |
| infectious_immune | 0.73 | 0.72 | 0.62 | 0.48 |
| otologic | 0.71 | 0.62 | 0.50 | 0.50 |

목표를 넘은 장기: 영어 0/13, 한국어 0/13.

장기별 dev 양성 수가 9~85개라 한두 개 차이로 F1이 0.05씩 움직인다. 목표 판정은 seed 평균과 test 한 번으로 한다.

