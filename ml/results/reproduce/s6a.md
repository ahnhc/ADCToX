# 재현 결과: s6a

- 단계: S6 E4B English first
- 메모: E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss
- 분할: dev
- seed: 8,9
- 뺀 데이터: gen_ko,ko2,kotypo,ko3,mondo_ko,kcd,umls
- 만든 시각: 2026-10-21 15:33

## 튜닝 안 한 Gemma와 비교

| 시스템 | 영어 장기 F1 | 한국어 장기 F1 | 영어 개념 | 한국어 개념 | 무효 수락 | 영어 Δ vs base [95%] | 한국어 Δ vs base [95%] |
|---|---|---|---|---|---|---|---|
| base_e4b | 0.852 | 0.796 | 0.604 | 0.543 | 0.000 | – | – |
| single_s6as8 | 0.562 | 0.342 | 0.000 | – | 0.000 | -0.290 [-0.384, -0.204] | -0.454 [-0.556, -0.346] |
| single_s6as9 | 0.877 | 0.793 | 0.274 | 0.126 | 0.000 | +0.025 [-0.040, +0.109] | -0.003 [-0.094, +0.083] |

## 장기별 F1 (목표: 모든 장기 0.95 이상)

seed 평균. ✓는 목표 이상.

| 장기 | base 영어 | base 한국어 | 튜닝 영어 | 튜닝 한국어 |
|---|---|---|---|---|
| haematologic | 0.93 | 0.85 | 0.62 | 0.45 |
| hepatic | 0.96 | 0.95 | 0.87 | 0.68 |
| cardiovascular | 0.95 | 0.90 | 0.84 | 0.67 |
| pulmonary | 0.76 | 0.69 | 0.65 | 0.65 |
| renal | 0.96 | 0.89 | 0.82 | 0.62 |
| gastrointestinal | 0.90 | 0.93 | 0.72 | 0.55 |
| neurologic | 0.80 | 0.76 | 0.63 | 0.49 |
| ocular | 0.86 | 0.74 | 0.74 | 0.60 |
| dermatologic | 0.87 | 0.79 | 0.61 | 0.46 |
| metabolic_endocrine | 0.79 | 0.75 | 0.80 | 0.56 |
| musculoskeletal | 0.83 | 0.76 | 0.81 | 0.72 |
| infectious_immune | 0.73 | 0.72 | 0.66 | 0.56 |
| otologic | 0.71 | 0.62 | 0.58 | 0.36 |

목표를 넘은 장기: 영어 0/13, 한국어 0/13.

장기별 dev 양성 수가 9~85개라 한두 개 차이로 F1이 0.05씩 움직인다. 목표 판정은 seed 평균과 test 한 번으로 한다.

