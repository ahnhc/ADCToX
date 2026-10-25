# 재현 결과: s6e

- 단계: S6 E4B English first, lr 1e-4, clip 1.0
- 메모: E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss, lr 1e-4 and gradient clipping 1.0 (seeds 9-11 under-trained without it)
- 분할: dev
- seed: 11
- 뺀 데이터: gen_ko,ko2,kotypo,ko3,mondo_ko,kcd,umls
- 만든 시각: 2026-10-22 01:07

## 튜닝 안 한 Gemma와 비교

| 시스템 | 영어 장기 F1 | 한국어 장기 F1 | 영어 개념 | 한국어 개념 | 무효 수락 | 영어 Δ vs base [95%] | 한국어 Δ vs base [95%] |
|---|---|---|---|---|---|---|---|
| base_e4b | 0.852 | 0.796 | 0.604 | 0.543 | 0.000 | – | – |
| single_s6es11 | 0.653 | 0.484 | – | – | 0.067 | -0.199 [-0.310, -0.107] | -0.312 [-0.435, -0.212] |

## 장기별 F1 (목표: 모든 장기 0.95 이상)

seed 평균. ✓는 목표 이상.

| 장기 | base 영어 | base 한국어 | 튜닝 영어 | 튜닝 한국어 |
|---|---|---|---|---|
| haematologic | 0.93 | 0.85 | 0.53 | 0.59 |
| hepatic | 0.96 | 0.95 | 0.70 | 0.34 |
| cardiovascular | 0.95 | 0.90 | 0.67 | 0.46 |
| pulmonary | 0.76 | 0.69 | 0.58 | 0.46 |
| renal | 0.96 | 0.89 | 0.71 | 0.19 |
| gastrointestinal | 0.90 | 0.93 | 0.59 | 0.46 |
| neurologic | 0.80 | 0.76 | 0.68 | 0.53 |
| ocular | 0.86 | 0.74 | 0.84 | 0.84 |
| dermatologic | 0.87 | 0.79 | 0.72 | 0.45 |
| metabolic_endocrine | 0.79 | 0.75 | 0.60 | 0.47 |
| musculoskeletal | 0.83 | 0.76 | 0.80 | 0.61 |
| infectious_immune | 0.73 | 0.72 | 0.65 | 0.52 |
| otologic | 0.71 | 0.62 | 0.43 | 0.36 |

목표를 넘은 장기: 영어 0/13, 한국어 0/13.

장기별 dev 양성 수가 9~85개라 한두 개 차이로 F1이 0.05씩 움직인다. 목표 판정은 seed 평균과 test 한 번으로 한다.

