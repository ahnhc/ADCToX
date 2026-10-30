# Gemma judge 학습 기록

`ml/tuning_ledger.py`가 `ml/results/tuning/*.json`에서 만든다. 손으로 고치지 않는다.
각 실행의 데이터 파일(행 수, sha256), 설정, 결과는 카드에 있다. 아래는 단계별 요약이다.

## S0 기준: models 0.6

### v3 — models 0.6 (검토 전 데이터)

- 시작 2026-10-15, 커밋 `61faa4d`, seed 7
- 데이터: organ_labels 52,801, train_queries 36,209, profiles 790, gen_ko 4,983, gen_sym 7,900, gen_junk 2,498
- 학습 항목: total 104,493, train 95,795
- 내부 dev: en_pipeline 0.889, en_single 0.878, ko_pipeline 0.746, ko_single 0.743, align_top1 0.48, sym_top3 0.898, valid_threshold 0.995
- 벤치마크 app A4 (dev): en 0.89, ko 0.746, en_lay 0.837, invalid_accept 0.0
- 벤치마크 single (dev): en 0.875, ko 0.763, concept_en 0.335, concept_ko 0.235, invalid_accept 0.0, ambiguous_accept 0.765, symptom_top3 0.83

### v3s8 — 검토 전 데이터, seed 8 (seed 차이 측정)

- 시작 2026-10-17 12:45, 커밋 `61faa4d`, seed 8
- 데이터: organ_labels 52,801, train_queries 36,209, profiles 790, gen_ko 4,983, gen_sym 7,900, gen_junk 2,498
- 학습 항목: total 104,444, train 95,993
- v3 대비 바뀐 것: seed 7 → 8
- 내부 dev: en_pipeline 0.887, en_single 0.887, ko_pipeline 0.737, ko_single 0.732, align_top1 0.482, sym_top3 0.886, valid_threshold 0.995
- 벤치마크 app A4 (dev): en 0.886, ko 0.766, en_lay 0.837, invalid_accept 0.0

## S0a 검토 데이터 (반영 오류)

### v4 — Opus 검토 데이터. 증상·한국어 표현·무효 입력이 두 번 반영된 상태

- 시작 2026-10-17 11:00, 커밋 `d42b740`, seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,711, gen_sym 7,880, gen_junk 2,329
- 학습 항목: total 103,605, train 95,262
- v3 대비 바뀐 것: gen_junk 2,498 → 2,329행; gen_ko 4,983 → 4,711행; gen_sym 7,900 → 7,880행; organ_labels 52,801 → 53,479행; profiles 행 수 같음, 내용 바뀐 파일 7개
- 내부 dev: en_pipeline 0.871, en_single 0.875, ko_pipeline 0.737, ko_single 0.742, align_top1 0.472, sym_top3 0.898, valid_threshold 0.99
- 벤치마크 app A4 (dev): en 0.876, ko 0.759, en_lay 0.78, invalid_accept 0.0

### v4s8 — 같은 데이터, seed 8

- 시작 2026-10-17 12:45, 커밋 `d42b740`, seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,711, gen_sym 7,880, gen_junk 2,329
- 학습 항목: total 103,556, train 94,932
- v3s8 대비 바뀐 것: gen_junk 2,498 → 2,329행; gen_ko 4,983 → 4,711행; gen_sym 7,900 → 7,880행; organ_labels 52,801 → 53,479행; profiles 행 수 같음, 내용 바뀐 파일 7개
- 내부 dev: en_pipeline 0.881, en_single 0.867, ko_pipeline 0.732, ko_single 0.736, align_top1 0.471, sym_top3 0.92, valid_threshold 0.99
- 벤치마크 app A4 (dev): en 0.88, ko 0.739, en_lay 0.805, invalid_accept 0.0

## S0b 검토 데이터 (수정)

### v5s7 — ml/dataset_review_gen.py로 다시 만든 데이터

- 시작 2026-10-17 14:00, 커밋 `d42b740+`, seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344
- 학습 항목: total 103,870, train 95,187
- v3 대비 바뀐 것: gen_junk 2,498 → 2,344행; gen_ko 4,983 → 4,849행; gen_sym 7,900 → 7,890행; organ_labels 52,801 → 53,479행; profiles 행 수 같음, 내용 바뀐 파일 7개
- 내부 dev: en_pipeline 0.887, en_single 0.89, ko_pipeline 0.751, ko_single 0.748, align_top1 0.504, sym_top3 0.943, valid_threshold 0.98
- 벤치마크 app A4 (dev): en 0.888, ko 0.747, en_lay 0.827, invalid_accept 0.0
- 벤치마크 single (dev): en 0.877, ko 0.764, concept_en 0.361, concept_ko 0.183, invalid_accept 0.0, ambiguous_accept 0.765, symptom_top3 0.92
- 벤치마크 app (dev): en 0.888, ko 0.747, concept_en None, concept_ko None, invalid_accept 0.0, ambiguous_accept 0.794, symptom_top3 None

### v5s8 — 같은 데이터, seed 8

- 시작 2026-10-17 14:00, 커밋 `d42b740+`, seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344
- 학습 항목: total 103,821, train 94,895
- v3s8 대비 바뀐 것: gen_junk 2,498 → 2,344행; gen_ko 4,983 → 4,849행; gen_sym 7,900 → 7,890행; organ_labels 52,801 → 53,479행; profiles 행 수 같음, 내용 바뀐 파일 7개
- 내부 dev: en_pipeline 0.888, en_single 0.888, ko_pipeline 0.748, ko_single 0.757, align_top1 0.466, sym_top3 0.92, valid_threshold 0.995
- 벤치마크 app A4 (dev): en 0.893, ko 0.751, en_lay 0.85, invalid_accept 0.0
- 벤치마크 single (dev): en 0.888, ko 0.777, concept_en 0.352, concept_ko 0.191, invalid_accept 0.0, ambiguous_accept 0.765, symptom_top3 0.875

## S1 한국어 이름·표현 추가

### s1s7 — 검토한 MONDO 한국어 이름 20,810개 + Haiku 한국어 일상어·구어·약어·오타 11,261개

- 시작 2026-10-17 23:45, 커밋 `d42b740` (커밋 안 된 변경 245개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261
- 학습 항목: total 143,662, train 130,941, val 12,721, korean 71,016, kcd 16,275, gen_ko 4,849, gen_sym 7,890, junk 2,344, mondo_ko 30,731, ko2 11,261, dropped_eval_text 265, out_organ 105,098, out_align 119,207, out_valid 130,941, out_sym 14,501
- 출처별 학습 항목: mondo_names 52,728, mondo_ko 27,531, kcd 16,275, ko2 10,112, gen_sym 7,041, profiles 6,932, gen_ko 3,030, train_queries 2,690, external 2,492, junk 2,110
- v5s7 대비 바뀐 것: gen_ko2 0 → 11,261행; mondo_index 바뀜; mondo_ko 0 → 23,258행; mondo_obo 바뀜; compare_to None → v5s7; drop None → 
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 122, "align": 44, "valid": 327, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.886, en_single 0.882, ko_pipeline 0.749, ko_single 0.742, align_top1 0.457, sym_top3 0.92, valid_threshold 0.99
- 벤치마크 single (dev): en 0.873, ko 0.777, concept_en 0.365, invalid_accept 0.0, symptom_top3 0.852

### s1s8 — 검토한 MONDO 한국어 이름 20,810개 + Haiku 한국어 일상어·구어·약어·오타 11,261개

- 시작 2026-10-17 23:45, 커밋 `d42b740` (커밋 안 된 변경 245개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261
- 학습 항목: total 143,613, train 130,939, val 12,674, korean 70,949, kcd 16,226, gen_ko 4,849, gen_sym 7,890, junk 2,344, mondo_ko 30,731, ko2 11,261, dropped_eval_text 265, out_organ 105,149, out_align 119,209, out_valid 130,939, out_sym 14,574
- 출처별 학습 항목: mondo_names 52,826, mondo_ko 27,528, kcd 16,226, ko2 10,117, gen_sym 7,053, profiles 6,939, gen_ko 3,032, train_queries 2,650, external 2,458, junk 2,110
- v5s7 대비 바뀐 것: gen_ko2 0 → 11,261행; mondo_index 바뀜; mondo_ko 0 → 23,258행; mondo_obo 바뀜; compare_to None → v5s7; drop None → ; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 122, "align": 43, "valid": 329, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 0}
- 내부 dev: en_pipeline 0.887, en_single 0.884, ko_pipeline 0.777, ko_single 0.768, align_top1 0.44, sym_top3 0.943, valid_threshold 0.995
- 벤치마크 single (dev): en 0.898, ko 0.803, concept_en 0.374, invalid_accept 0.0, symptom_top3 0.92

### s1s9 — 검토한 MONDO 한국어 이름 20,810개 + Haiku 한국어 일상어·구어·약어·오타 11,261개

- 시작 2026-10-18 00:20, 커밋 `d42b740` (커밋 안 된 변경 246개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261
- 학습 항목: total 143,660, train 131,007, val 12,653, korean 70,999, kcd 16,273, gen_ko 4,849, gen_sym 7,890, junk 2,344, mondo_ko 30,731, ko2 11,261, dropped_eval_text 265, out_organ 105,090, out_align 119,237, out_valid 131,007, out_sym 14,473
- 출처별 학습 항목: mondo_names 52,799, mondo_ko 27,578, kcd 16,273, ko2 10,108, gen_sym 7,021, profiles 6,935, gen_ko 3,033, train_queries 2,640, external 2,510, junk 2,110
- v5s7 대비 바뀐 것: gen_ko2 0 → 11,261행; mondo_index 바뀜; mondo_ko 0 → 23,258행; mondo_obo 바뀜; compare_to None → v5s7; drop None → ; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 122, "align": 44, "valid": 330, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.882, en_single 0.866, ko_pipeline 0.761, ko_single 0.754, align_top1 0.445, sym_top3 0.92, valid_threshold 0.995
- 벤치마크 single (dev): en 0.865, ko 0.788, concept_en 0.339, invalid_accept 0.0, symptom_top3 0.875

## S2a junk oversampling fix

### s2as7 — JUNK_COPIES=4 applied after the dedupe; Korean eval reviewed (21 questions); no new Korean data (kotypo, ko3 left out)

- 시작 2026-10-18 10:18, 커밋 `d42b740` (커밋 안 된 변경 430개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423
- 학습 항목: total 149,996, train 137,569, val 12,427, korean 75,961, kcd 16,275, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 0, ko3 0, dropped_eval_text 261, out_organ 105,427, out_align 119,480, out_valid 137,569, out_sym 14,737
- 출처별 학습 항목: mondo_names 52,763, mondo_ko 27,529, kcd 16,275, ko2 10,160, junk 8,440, gen_sym 7,130, profiles 7,010, gen_ko 3,057, train_queries 2,690, external 2,515
- 뺀 출처: ko3, kotypo
- s1s7 대비 바뀐 것: gen_ko3 0 → 0행; gen_kotypo 0 → 26,423행; compare_to v5s7 → s1s7; drop  → kotypo,ko3
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 121, "align": 43, "valid": 408, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.877, en_single 0.857, ko_pipeline 0.789, ko_single 0.785, align_top1 0.462, sym_top3 0.955, valid_threshold 0.995
- 벤치마크 single (dev): en 0.86, ko 0.806, concept_en 0.387, invalid_accept 0.067, symptom_top3 0.886

### s2as8 — JUNK_COPIES=4 applied after the dedupe; Korean eval reviewed (21 questions); no new Korean data (kotypo, ko3 left out)

- 시작 2026-10-18 10:18, 커밋 `d42b740` (커밋 안 된 변경 430개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423
- 학습 항목: total 149,947, train 137,294, val 12,653, korean 75,834, kcd 16,226, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 0, ko3 0, dropped_eval_text 261, out_organ 105,254, out_align 119,297, out_valid 137,294, out_sym 14,585
- 출처별 학습 항목: mondo_names 52,885, mondo_ko 27,564, kcd 16,226, ko2 10,092, junk 8,440, gen_sym 7,034, profiles 6,917, gen_ko 3,016, train_queries 2,625, external 2,495
- 뺀 출처: ko3, kotypo
- s1s7 대비 바뀐 것: gen_ko3 0 → 0행; gen_kotypo 0 → 26,423행; compare_to v5s7 → s1s7; drop  → kotypo,ko3; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 121, "align": 42, "valid": 419, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 0}
- 내부 dev: en_pipeline 0.881, en_single 0.882, ko_pipeline 0.759, ko_single 0.761, align_top1 0.447, sym_top3 0.92, valid_threshold 0.995
- 벤치마크 single (dev): en 0.881, ko 0.797, concept_en 0.37, invalid_accept 0.0, symptom_top3 0.841

### s2as9 — JUNK_COPIES=4 applied after the dedupe; Korean eval reviewed (21 questions); no new Korean data (kotypo, ko3 left out)

- 시작 2026-10-18 11:21, 커밋 `d42b740` (커밋 안 된 변경 479개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 149,994, train 137,422, val 12,572, korean 75,893, kcd 16,273, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 0, ko3 0, dropped_eval_text 261, out_organ 105,194, out_align 119,326, out_valid 137,422, out_sym 14,569
- 출처별 학습 항목: mondo_names 52,737, mondo_ko 27,568, kcd 16,273, ko2 10,117, junk 8,440, gen_sym 7,050, profiles 6,973, gen_ko 3,073, train_queries 2,684, external 2,507
- 뺀 출처: ko3, kotypo
- s1s7 대비 바뀐 것: gen_ko3 0 → 6,160행; gen_kotypo 0 → 26,423행; compare_to v5s7 → s1s7; drop  → kotypo,ko3; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 121, "align": 43, "valid": 420, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.882, en_single 0.874, ko_pipeline 0.77, ko_single 0.761, align_top1 0.456, sym_top3 0.932, valid_threshold 0.995
- 벤치마크 single (dev): en 0.88, ko 0.785, concept_en 0.413, invalid_accept 0.0, symptom_top3 0.852

## S2b rule-based Korean typos

### s2bs7 — S2a + kotypo (26,423 jamo typos, ml/ko_typos.py)

- 시작 2026-10-18 10:30, 커밋 `d42b740` (커밋 안 된 변경 476개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 176,419, train 161,305, val 15,114, korean 102,384, kcd 16,275, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 0, dropped_eval_text 261, out_organ 129,163, out_align 143,216, out_valid 161,305, out_sym 15,465
- 출처별 학습 항목: mondo_names 52,763, mondo_ko 27,529, kotypo 23,736, kcd 16,275, ko2 10,160, junk 8,440, gen_sym 7,130, profiles 7,010, gen_ko 3,057, train_queries 2,690, external 2,515
- 뺀 출처: ko3
- s2as7 대비 바뀐 것: gen_ko3 0 → 6,160행; compare_to s1s7 → s2as7; drop kotypo,ko3 → ko3
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 121, "align": 43, "valid": 408, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.877, en_single 0.871, ko_pipeline 0.78, ko_single 0.769, align_top1 0.44, sym_top3 0.943, valid_threshold 0.995
- 벤치마크 single (dev): en 0.879, ko 0.776, concept_en 0.391, invalid_accept 0.0, symptom_top3 0.92

### s2bs8 — S2a + kotypo (26,423 jamo typos, ml/ko_typos.py)

- 시작 2026-10-18 10:30, 커밋 `d42b740` (커밋 안 된 변경 476개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 176,370, train 161,077, val 15,293, korean 102,257, kcd 16,226, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 0, dropped_eval_text 261, out_organ 129,037, out_align 143,080, out_valid 161,077, out_sym 15,304
- 출처별 학습 항목: mondo_names 52,885, mondo_ko 27,564, kotypo 23,783, kcd 16,226, ko2 10,092, junk 8,440, gen_sym 7,034, profiles 6,917, gen_ko 3,016, train_queries 2,625, external 2,495
- 뺀 출처: ko3
- s2as7 대비 바뀐 것: gen_ko3 0 → 6,160행; compare_to s1s7 → s2as7; drop kotypo,ko3 → ko3; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 121, "align": 42, "valid": 419, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 0}
- 내부 dev: en_pipeline 0.894, en_single 0.887, ko_pipeline 0.767, ko_single 0.765, align_top1 0.448, sym_top3 0.92, valid_threshold 0.995
- 벤치마크 single (dev): en 0.88, ko 0.788, concept_en 0.357, invalid_accept 0.0, symptom_top3 0.852

### s2bs9 — S2a + kotypo (26,423 jamo typos, ml/ko_typos.py)

- 시작 2026-10-18 11:41, 커밋 `d42b740` (커밋 안 된 변경 483개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 176,417, train 161,210, val 15,207, korean 102,316, kcd 16,273, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 0, dropped_eval_text 261, out_organ 128,982, out_align 143,114, out_valid 161,210, out_sym 15,285
- 출처별 학습 항목: mondo_names 52,737, mondo_ko 27,568, kotypo 23,788, kcd 16,273, ko2 10,117, junk 8,440, gen_sym 7,050, profiles 6,973, gen_ko 3,073, train_queries 2,684, external 2,507
- 뺀 출처: ko3
- s2as7 대비 바뀐 것: gen_ko3 0 → 6,160행; compare_to s1s7 → s2as7; drop kotypo,ko3 → ko3; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 121, "align": 43, "valid": 420, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.882, en_single 0.862, ko_pipeline 0.782, ko_single 0.78, align_top1 0.446, sym_top3 0.932, valid_threshold 0.995
- 벤치마크 single (dev): en 0.869, ko 0.79, concept_en 0.348, invalid_accept 0.0, symptom_top3 0.875

## S2c Korean short words, abbreviations, Korean-English mixes

### s2cs7 — S2b + ko3 (6,160: mixed 3,108, everyday 1,581, spoken 819, abbrev 477, short 175)

- 시작 2026-10-18 12:25, 커밋 `d42b740` (커밋 안 된 변경 486개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 182,197, train 166,457, val 15,740, korean 108,047, kcd 16,275, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, dropped_eval_text 261, out_organ 134,315, out_align 148,368, out_valid 166,457, out_sym 15,803
- 출처별 학습 항목: mondo_names 52,677, mondo_ko 27,529, kotypo 23,736, kcd 16,275, ko2 9,962, junk 8,440, gen_sym 7,130, profiles 6,993, ko3 5,503, gen_ko 3,013, train_queries 2,689, external 2,510
- s2bs7 대비 바뀐 것: compare_to s2as7 → s2bs7; drop ko3 → 
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 45, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.88, en_single 0.87, ko_pipeline 0.76, ko_single 0.775, align_top1 0.434, sym_top3 0.909, valid_threshold 0.995
- 벤치마크 single (dev): en 0.867, ko 0.788, concept_en 0.365, invalid_accept 0.0, symptom_top3 0.852

### s2cs8 — S2b + ko3 (6,160: mixed 3,108, everyday 1,581, spoken 819, abbrev 477, short 175)

- 시작 2026-10-18 12:25, 커밋 `d42b740` (커밋 안 된 변경 486개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 182,148, train 166,257, val 15,891, korean 107,920, kcd 16,226, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, dropped_eval_text 261, out_organ 134,217, out_align 148,260, out_valid 166,257, out_sym 15,641
- 출처별 학습 항목: mondo_names 52,800, mondo_ko 27,564, kotypo 23,783, kcd 16,226, ko2 9,899, junk 8,440, gen_sym 7,034, profiles 6,901, ko3 5,524, gen_ko 2,973, train_queries 2,624, external 2,489
- s2bs7 대비 바뀐 것: compare_to s2as7 → s2bs7; drop ko3 → ; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 44, "valid": 421, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 0}
- 내부 dev: en_pipeline 0.88, en_single 0.868, ko_pipeline 0.771, ko_single 0.775, align_top1 0.443, sym_top3 0.955, valid_threshold 0.995
- 벤치마크 single (dev): en 0.87, ko 0.8, concept_en 0.378, invalid_accept 0.0, symptom_top3 0.875

### s2cs9 — S2b + ko3 (6,160: mixed 3,108, everyday 1,581, spoken 819, abbrev 477, short 175)

- 시작 2026-10-18 13:48, 커밋 `d42b740` (커밋 안 된 변경 491개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 182,195, train 166,419, val 15,776, korean 107,979, kcd 16,273, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, dropped_eval_text 261, out_organ 134,191, out_align 148,323, out_valid 166,419, out_sym 15,613
- 출처별 학습 항목: mondo_names 52,654, mondo_ko 27,568, kotypo 23,788, kcd 16,273, ko2 9,927, junk 8,440, gen_sym 7,050, profiles 6,956, ko3 5,553, gen_ko 3,026, train_queries 2,683, external 2,501
- s2bs7 대비 바뀐 것: compare_to s2as7 → s2bs7; consist None → 0.0; drop ko3 → ; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 45, "valid": 422, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.888, en_single 0.874, ko_pipeline 0.779, ko_single 0.783, align_top1 0.447, sym_top3 0.932, valid_threshold 0.995
- 벤치마크 single (dev): en 0.878, ko 0.786, concept_en 0.365, invalid_accept 0.0, symptom_top3 0.807

## S2d Korean-English consistency loss

### s2ds7 — S2c data + --consist 1.0: every Korean training text paired with its concept's English MONDO name; Korean outputs pulled to the English ones

- 시작 2026-10-18 13:04, 커밋 `d42b740` (커밋 안 된 변경 488개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 182,197, train 166,457, val 15,740, korean 108,047, kcd 16,275, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, dropped_eval_text 261, out_organ 134,315, out_align 148,368, out_valid 166,457, out_sym 15,803
- 출처별 학습 항목: mondo_names 52,677, mondo_ko 27,529, kotypo 23,736, kcd 16,275, ko2 9,962, junk 8,440, gen_sym 7,130, profiles 6,993, ko3 5,503, gen_ko 3,013, train_queries 2,689, external 2,510
- s2cs7 대비 바뀐 것: compare_to s2bs7 → s2cs7; consist None → 1.0
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 45, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.865, en_single 0.853, ko_pipeline 0.771, ko_single 0.759, align_top1 0.407, sym_top3 0.932, valid_threshold 0.995
- 벤치마크 single (dev): en 0.855, ko 0.787, concept_en 0.391, invalid_accept 0.0, symptom_top3 0.898

### s2ds8 — S2c data + --consist 1.0: every Korean training text paired with its concept's English MONDO name; Korean outputs pulled to the English ones

- 시작 2026-10-18 13:04, 커밋 `d42b740` (커밋 안 된 변경 488개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 182,148, train 166,257, val 15,891, korean 107,920, kcd 16,226, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, dropped_eval_text 261, out_organ 134,217, out_align 148,260, out_valid 166,257, out_sym 15,641
- 출처별 학습 항목: mondo_names 52,800, mondo_ko 27,564, kotypo 23,783, kcd 16,226, ko2 9,899, junk 8,440, gen_sym 7,034, profiles 6,901, ko3 5,524, gen_ko 2,973, train_queries 2,624, external 2,489
- s2cs7 대비 바뀐 것: compare_to s2bs7 → s2cs7; consist None → 1.0; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 44, "valid": 421, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 0}
- 내부 dev: en_pipeline 0.872, en_single 0.86, ko_pipeline 0.793, ko_single 0.78, align_top1 0.413, sym_top3 0.966, valid_threshold 0.995
- 벤치마크 single (dev): en 0.854, ko 0.812, concept_en 0.448, invalid_accept 0.0, symptom_top3 0.886

### s2ds9 — S2c data + --consist 1.0: every Korean training text paired with its concept's English MONDO name; Korean outputs pulled to the English ones

- 시작 2026-10-18 15:05, 커밋 `d42b740` (커밋 안 된 변경 496개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 182,195, train 166,419, val 15,776, korean 107,979, kcd 16,273, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, dropped_eval_text 261, out_organ 134,191, out_align 148,323, out_valid 166,419, out_sym 15,613
- 출처별 학습 항목: mondo_names 52,654, mondo_ko 27,568, kotypo 23,788, kcd 16,273, ko2 9,927, junk 8,440, gen_sym 7,050, profiles 6,956, ko3 5,553, gen_ko 3,026, train_queries 2,683, external 2,501
- s2cs7 대비 바뀐 것: compare_to s2bs7 → s2cs7; consist None → 1.0; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 45, "valid": 422, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.878, en_single 0.867, ko_pipeline 0.78, ko_single 0.784, align_top1 0.425, sym_top3 0.943, valid_threshold 0.995
- 벤치마크 single (dev): en 0.875, ko 0.809, concept_en 0.426, invalid_accept 0.0, symptom_top3 0.83

## X0 from-scratch encoder, no UMLS

### x0s7 — random init, NFD+BPE, 6 layers 384 wide; MONDO, KCD, mondo_ko pairs + the S2c items

- 시작 2026-10-18 18:02, 커밋 `d42b740` (커밋 안 된 변경 502개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 181,229, train 166,219, val 15,010, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 196,495
- 출처별 학습 항목: mondo_names 52,729, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,897, junk 8,440, gen_sym 7,340, ko3 5,561, profiles_sym 3,679, gen_ko 2,967, train_queries 2,656, profiles 2,605, external 2,498
- s2ds7 대비 바뀐 것: bs None → 256; compare_to s2cs7 → s2ds7; consist 1.0 → None; epochs 2 → 6; kcd 20000 → None; layers 18 → None; lr 0.0002 → 0.0005; pre_epochs None → 6; rank 16 → None
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1472, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8616365704406271, '0.55': 0.8635917218890581, '0.6': 0.86783429762738, '0.65': 0.8692615135334635, '0.7': 0.8656657943184709, '0.75': 0.8622062696670607, '0.8': 0.8555319536828343, '0.85': 0.8505476961113255, '0.9': 0.8457818128131003, '0.95': 0.8419054774458588, '1.0': 0.7832144233853533}, real_accepted 0.9861425716189207, minutes 13.2
- 벤치마크 scratch (dev): en 0.458, ko 0.605, concept_en 0.27, invalid_accept 0.067, symptom_top3 None

### x0s8 — random init, NFD+BPE, 6 layers 384 wide; MONDO, KCD, mondo_ko pairs + the S2c items

- 시작 2026-10-18 18:02, 커밋 `d42b740` (커밋 안 된 변경 502개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 181,182, train 165,833, val 15,349, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 196,143
- 출처별 학습 항목: mondo_names 52,635, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,897, junk 8,440, gen_sym 7,323, ko3 5,563, profiles_sym 3,668, gen_ko 2,932, train_queries 2,615, profiles 2,606, external 2,458
- s2ds8 대비 바뀐 것: bs None → 256; compare_to s2cs7 → s2ds8; consist 1.0 → None; epochs 2 → 6; kcd 20000 → None; layers 18 → None; lr 0.0002 → 0.0005; pre_epochs None → 6; rank 16 → None
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1567, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8567909893278685, '0.55': 0.8578290009051605, '0.6': 0.8621816821261858, '0.65': 0.8632171798100002, '0.7': 0.8615602705909369, '0.75': 0.8557395384696599, '0.8': 0.8480331638599593, '0.85': 0.8423915021168582, '0.9': 0.8379739810151339, '0.95': 0.8347355732307975, '1.0': 0.7704487682590049}, real_accepted 0.9837122939605186, minutes 12.9
- 벤치마크 scratch (dev): en 0.476, ko 0.579, concept_en 0.261, invalid_accept 0.067, symptom_top3 None

### x0s9 — random init, NFD+BPE, 6 layers 384 wide; MONDO, KCD, mondo_ko pairs + the S2c items

- 시작 2026-10-18 18:02, 커밋 `d42b740` (커밋 안 된 변경 502개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160
- 학습 항목: total 181,228, train 166,268, val 14,960, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 196,706
- 출처별 학습 항목: mondo_names 52,702, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,865, junk 8,440, gen_sym 7,351, ko3 5,527, profiles_sym 3,688, gen_ko 2,999, train_queries 2,686, profiles 2,641, external 2,512
- s2ds9 대비 바뀐 것: bs None → 256; compare_to s2cs7 → s2ds9; consist 1.0 → None; epochs 2 → 6; kcd 20000 → None; layers 18 → None; lr 0.0002 → 0.0005; pre_epochs None → 6; rank 16 → None
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1516, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8656916424459387, '0.55': 0.8658919559799517, '0.6': 0.8717685628203498, '0.65': 0.8738152109225058, '0.7': 0.8686637036515207, '0.75': 0.8624069024132689, '0.8': 0.8552470550688936, '0.85': 0.848832912542086, '0.9': 0.8440685773736593, '0.95': 0.8397966943477624, '1.0': 0.7716966061526485}, real_accepted 0.990909090909091, minutes 13.8
- 벤치마크 scratch (dev): en 0.454, ko 0.547, concept_en 0.3, invalid_accept 0.067, symptom_top3 None

## X1 from-scratch encoder + UMLS

### x1s7 — X0 + UMLS 2026AA (SRL 0, ENG/KOR, Disorders) pairs and MONDO-linked names

- 시작 2026-10-20 05:43, 커밋 `8839663` (커밋 안 된 변경 1개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- x0s7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2ds7 → x0s7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1488, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8553193361188289, '0.55': 0.856856146282944, '0.6': 0.8589750300276544, '0.65': 0.8597413395693565, '0.7': 0.8561657855313203, '0.75': 0.8484615135539363, '0.8': 0.8401909036832695, '0.85': 0.8288974659611194, '0.9': 0.8175994010216928, '0.95': 0.8074575881226297, '1.0': 0.7654139513376482}, real_accepted 0.986784140969163, minutes 22.7
- 벤치마크 scratch (dev): en 0.63, ko 0.625, concept_en 0.352, invalid_accept 0.133, symptom_top3 None

### x1s8 — X0 + UMLS 2026AA (SRL 0, ENG/KOR, Disorders) pairs and MONDO-linked names

- 시작 2026-10-20 05:43, 커밋 `8839663` (커밋 안 된 변경 1개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 466,129
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- x0s8 대비 바뀐 것: umls 0 → 307,932행; compare_to s2ds8 → x0s8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1572, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8436624104396144, '0.55': 0.8449616544494271, '0.6': 0.8475378703171473, '0.65': 0.8482666058513372, '0.7': 0.8433256564894072, '0.75': 0.834424080242009, '0.8': 0.8222835462182648, '0.85': 0.8095831370575955, '0.9': 0.7973204176502515, '0.95': 0.7855265358904288, '1.0': 0.7401448367231046}, real_accepted 0.9862569487337863, minutes 23.1
- 벤치마크 scratch (dev): en 0.571, ko 0.598, concept_en 0.33, invalid_accept 0.133, symptom_top3 None

### x1s9 — X0 + UMLS 2026AA (SRL 0, ENG/KOR, Disorders) pairs and MONDO-linked names

- 시작 2026-10-20 05:43, 커밋 `8839663` (커밋 안 된 변경 1개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,631
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- x0s9 대비 바뀐 것: umls 0 → 307,932행; compare_to s2ds9 → x0s9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1563, valid_threshold 0.995, theta 0.6, theta_val_f1 {'0.5': 0.8459890027407325, '0.55': 0.846657192355701, '0.6': 0.8494139029019296, '0.65': 0.8490463970267328, '0.7': 0.8450627283051364, '0.75': 0.8359693640561473, '0.8': 0.8218262099367059, '0.85': 0.8081287547078359, '0.9': 0.7961783262307269, '0.95': 0.783932642252264, '1.0': 0.7369227573033754}, real_accepted 0.9822324170910929, minutes 23.6
- 벤치마크 scratch (dev): en 0.579, ko 0.55, concept_en 0.343, invalid_accept 0.133, symptom_top3 None

## E BAAI/bge-m3

### ebs7 — pretrained BAAI/bge-m3 fine-tuned with the judge data, stages and calibration of the scratch judge; UMLS included

- 시작 2026-10-20 06:22, 커밋 `8839663` (커밋 안 된 변경 14개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; backbone None → BAAI/bge-m3; bs None → 64; compare_to s2cs7 → s2ds7; consist 1.0 → None; epochs 2 → 3; head_lr None → 0.001; kcd 20000 → None; layers 18 → None; lr 0.0002 → 2e-05; pre_epochs None → 2; rank 16 → None
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1285, valid_threshold 0.995, theta 0.6, theta_val_f1 {'0.5': 0.9143511188292643, '0.55': 0.9144986476912822, '0.6': 0.9149296654753597, '0.65': 0.9146041068537175, '0.7': 0.9144497785130699, '0.75': 0.9097827316789171, '0.8': 0.9004717255728804, '0.85': 0.8856559352080894, '0.9': 0.8699660719751172, '0.95': 0.8476026311626265, '1.0': 0.7870482189328813}, real_accepted 0.9983873505349277, minutes 143.6
- 벤치마크 scratch (dev): en 0.712, ko 0.64, concept_en 0.578, invalid_accept 0.0, symptom_top3 None

## E intfloat/multilingual-e5-large

### ees7 — pretrained intfloat/multilingual-e5-large fine-tuned with the judge data, stages and calibration of the scratch judge; UMLS included

- 시작 2026-10-20 06:25, 커밋 `8839663` (커밋 안 된 변경 15개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; backbone None → intfloat/multilingual-e5-large; bs None → 64; compare_to s2cs7 → s2ds7; consist 1.0 → None; epochs 2 → 3; head_lr None → 0.001; kcd 20000 → None; layers 18 → None; lr 0.0002 → 2e-05; pre_epochs None → 2; rank 16 → None
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1253, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.9121796790694721, '0.55': 0.9122718579090547, '0.6': 0.9121703104744389, '0.65': 0.9130905155246553, '0.7': 0.9116029898689283, '0.75': 0.9082421314130612, '0.8': 0.9008191054938558, '0.85': 0.8893788443761543, '0.9': 0.8735575444286645, '0.95': 0.8501694632608169, '1.0': 0.792398733811843}, real_accepted 0.9982300188797986, minutes 144.5
- 벤치마크 scratch (dev): en 0.748, ko 0.667, concept_en 0.613, invalid_accept 0.0, symptom_top3 None

### ees8 — pretrained intfloat/multilingual-e5-large fine-tuned with the judge data, stages and calibration of the scratch judge; UMLS included

- 시작 2026-10-20 16:28, 커밋 `8839663` (커밋 안 된 변경 54개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 466,129
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- s2ds8 대비 바뀐 것: umls 0 → 307,932행; backbone None → intfloat/multilingual-e5-large; bs None → 64; compare_to s2cs7 → s2ds8; consist 1.0 → None; epochs 2 → 3; head_lr None → 0.001; kcd 20000 → None; layers 18 → None; lr 0.0002 → 2e-05; pre_epochs None → 2; rank 16 → None
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1383, valid_threshold 0.995, theta 0.5, theta_val_f1 {'0.5': 0.9092889368073394, '0.55': 0.9092827860365595, '0.6': 0.9091498293274208, '0.65': 0.9089902830186373, '0.7': 0.9083054920855608, '0.75': 0.9030973033336394, '0.8': 0.8940453752684702, '0.85': 0.8819155079129606, '0.9': 0.8647334030538762, '0.95': 0.8377357947870915, '1.0': 0.7726531999334079}, real_accepted 0.998340024706609, minutes 151.3
- 벤치마크 scratch (dev): en 0.742, ko 0.662, concept_en 0.6, invalid_accept 0.0, symptom_top3 None

### ees9 — pretrained intfloat/multilingual-e5-large fine-tuned with the judge data, stages and calibration of the scratch judge; UMLS included

- 시작 2026-10-20 18:15, 커밋 `8839663` (커밋 안 된 변경 61개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,631
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- s2ds9 대비 바뀐 것: umls 0 → 307,932행; backbone None → intfloat/multilingual-e5-large; bs None → 64; compare_to s2cs7 → s2ds9; consist 1.0 → None; epochs 2 → 3; head_lr None → 0.001; kcd 20000 → None; layers 18 → None; lr 0.0002 → 2e-05; pre_epochs None → 2; rank 16 → None
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 1, val_organ_loss 0.1399, valid_threshold 0.97, theta 0.7, theta_val_f1 {'0.5': 0.9039709809789463, '0.55': 0.9039709809789463, '0.6': 0.9040311570154683, '0.65': 0.9042022373407821, '0.7': 0.904475861800734, '0.75': 0.900512746762595, '0.8': 0.8926296714224673, '0.85': 0.878372044006286, '0.9': 0.8588127851240561, '0.95': 0.8284498886572235, '1.0': 0.7576190335072118}, real_accepted 0.9961121262781385, minutes 152.2
- 벤치마크 scratch (dev): en 0.772, ko 0.699, concept_en 0.578, invalid_accept 0.0, symptom_top3 None

## E FacebookAI/xlm-roberta-large

### exs7 — pretrained FacebookAI/xlm-roberta-large fine-tuned with the judge data, stages and calibration of the scratch judge; UMLS included

- 시작 2026-10-20 06:26, 커밋 `8839663` (커밋 안 된 변경 16개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; backbone None → FacebookAI/xlm-roberta-large; bs None → 64; compare_to s2cs7 → s2ds7; consist 1.0 → None; epochs 2 → 3; head_lr None → 0.001; kcd 20000 → None; layers 18 → None; lr 0.0002 → 2e-05; pre_epochs None → 2; rank 16 → None
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1314, valid_threshold 0.995, theta 0.7, theta_val_f1 {'0.5': 0.9091165643471733, '0.55': 0.9091330298396763, '0.6': 0.9091851974021683, '0.65': 0.9092069979315907, '0.7': 0.9097730010576339, '0.75': 0.9072699653642824, '0.8': 0.8991447674011717, '0.85': 0.8853941572602901, '0.9': 0.8690695368207398, '0.95': 0.8471991896342369, '1.0': 0.7858143508613479}, real_accepted 0.9979940213971051, minutes 143.2
- 벤치마크 scratch (dev): en 0.724, ko 0.665, concept_en 0.574, invalid_accept 0.0, symptom_top3 None

## S3 Gemma + UMLS names

### s3s7 — S2d (consist 1.0) + UMLS 2026AA SRL0 names of MONDO-linked concepts

- 시작 2026-10-20 08:50, 커밋 `8839663` (커밋 안 된 변경 21개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 286,271, train 260,151, val 26,120, korean 108,047, kcd 16,275, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, umls 113,978, dropped_eval_text 261, out_organ 228,009, out_align 242,062, out_valid 260,151, out_sym 22,580
- 출처별 학습 항목: umls 102,434, mondo_names 45,692, mondo_ko 27,529, kotypo 23,736, kcd 16,275, ko2 9,936, junk 8,440, gen_sym 7,130, profiles 6,528, ko3 5,503, gen_ko 2,914, train_queries 2,403, external 1,631
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 45, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.875, en_single 0.873, ko_pipeline 0.76, ko_single 0.771, align_top1 0.46, sym_top3 0.932, valid_threshold 0.995
- 벤치마크 single (dev): en 0.861, ko 0.778, concept_en 0.452, invalid_accept 0.0, symptom_top3 0.92

### s3s8 — S2d (consist 1.0) + UMLS 2026AA SRL0 names of MONDO-linked concepts

- 시작 2026-10-20 11:43, 커밋 `8839663` (커밋 안 된 변경 26개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 286,222, train 259,600, val 26,622, korean 107,920, kcd 16,226, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, umls 113,978, dropped_eval_text 261, out_organ 227,560, out_align 241,603, out_valid 259,600, out_sym 22,296
- 출처별 학습 항목: umls 102,024, mondo_names 45,841, mondo_ko 27,564, kotypo 23,783, kcd 16,226, ko2 9,877, junk 8,440, gen_sym 7,034, profiles 6,441, ko3 5,524, gen_ko 2,874, train_queries 2,353, external 1,619
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 44, "valid": 421, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 0}
- 내부 dev: en_pipeline 0.873, en_single 0.864, ko_pipeline 0.768, ko_single 0.767, align_top1 0.451, sym_top3 0.943, valid_threshold 0.995
- 벤치마크 single (dev): en 0.862, ko 0.786, concept_en 0.483, invalid_accept 0.0, symptom_top3 0.886

### s3s9 — S2d (consist 1.0) + UMLS 2026AA SRL0 names of MONDO-linked concepts

- 시작 2026-10-20 14:53, 커밋 `8839663` (커밋 안 된 변경 49개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 286,269, train 260,356, val 25,913, korean 107,979, kcd 16,273, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, umls 113,978, dropped_eval_text 261, out_organ 228,128, out_align 242,260, out_valid 260,356, out_sym 22,287
- 출처별 학습 항목: umls 102,704, mondo_names 45,663, mondo_ko 27,568, kotypo 23,788, kcd 16,273, ko2 9,903, junk 8,440, gen_sym 7,050, profiles 6,494, ko3 5,553, gen_ko 2,923, train_queries 2,396, external 1,601
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 45, "valid": 422, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.87, en_single 0.865, ko_pipeline 0.782, ko_single 0.808, align_top1 0.458, sym_top3 0.864, valid_threshold 0.995
- 벤치마크 single (dev): en 0.862, ko 0.814, concept_en 0.452, invalid_accept 0.0, symptom_top3 0.807

## E Qwen/Qwen3-Embedding-0.6B

### eqs7 — pretrained Qwen/Qwen3-Embedding-0.6B fine-tuned with the judge data, stages and calibration of the scratch judge; UMLS included

- 시작 2026-10-20 08:51, 커밋 `8839663` (커밋 안 된 변경 23개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; backbone None → Qwen/Qwen3-Embedding-0.6B; bs None → 64; compare_to s2cs7 → s2ds7; consist 1.0 → None; epochs 2 → 3; head_lr None → 0.001; kcd 20000 → None; layers 18 → None; lr 0.0002 → 2e-05; pre_epochs None → 2; rank 16 → None
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1427, valid_threshold 0.995, theta 0.6, theta_val_f1 {'0.5': 0.8748927862286465, '0.55': 0.8757128581657743, '0.6': 0.8763574346042101, '0.65': 0.8744350715025474, '0.7': 0.8673881563221238, '0.75': 0.8581372014073724, '0.8': 0.8468576390754925, '0.85': 0.8322719632831108, '0.9': 0.8155789982313869, '0.95': 0.8000165684474003, '1.0': 0.7354742483765909}, real_accepted 0.9947293895531781, minutes 254.9
- 벤치마크 scratch (dev): en 0.76, ko 0.602, concept_en 0.609, invalid_accept 0.0, symptom_top3 None

## S4 Gemma 4 E4B (S2d setup)

### s4s7 — E4B, first 24 of 42 layers (the layers with their own key/value), LoRA r16, S2d data and --consist 1.0, UMLS left out

- 시작 2026-10-20 13:17, 커밋 `8839663` (커밋 안 된 변경 46개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 182,197, train 166,457, val 15,740, korean 108,047, kcd 16,275, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, umls 0, dropped_eval_text 261, out_organ 134,315, out_align 148,368, out_valid 166,457, out_sym 15,803
- 출처별 학습 항목: mondo_names 52,677, mondo_ko 27,529, kotypo 23,736, kcd 16,275, ko2 9,962, junk 8,440, gen_sym 7,130, profiles 6,993, ko3 5,503, gen_ko 3,013, train_queries 2,689, external 2,510
- 뺀 출처: umls
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; drop  → umls; layers 18 → 24
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 45, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.885, en_single 0.851, ko_pipeline 0.796, ko_single 0.79, align_top1 0.32, sym_top3 0.898, valid_threshold 0.995
- 벤치마크 single (dev): en 0.844, ko 0.819, concept_en 0.287, invalid_accept 0.0, symptom_top3 0.875

## S2 consistency weight 2.0

### s2es7 — S2d setup (S2c data, UMLS left out) with --consist 2.0 instead of 1.0

- 시작 2026-10-20 19:01, 커밋 `8839663` (커밋 안 된 변경 65개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 182,197, train 166,457, val 15,740, korean 108,047, kcd 16,275, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, umls 0, dropped_eval_text 261, out_organ 134,315, out_align 148,368, out_valid 166,457, out_sym 15,803
- 출처별 학습 항목: mondo_names 52,677, mondo_ko 27,529, kotypo 23,736, kcd 16,275, ko2 9,962, junk 8,440, gen_sym 7,130, profiles 6,993, ko3 5,503, gen_ko 3,013, train_queries 2,689, external 2,510
- 뺀 출처: umls
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 2.0; drop  → umls
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 45, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.872, en_single 0.845, ko_pipeline 0.777, ko_single 0.778, align_top1 0.388, sym_top3 0.932, valid_threshold 0.995
- 벤치마크 single (dev): en 0.841, ko 0.802, concept_en 0.404, invalid_accept 0.0, symptom_top3 0.898

### s2es8 — S2d setup (S2c data, UMLS left out) with --consist 2.0 instead of 1.0

- 시작 2026-10-20 20:41, 커밋 `8839663` (커밋 안 된 변경 68개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 182,148, train 166,257, val 15,891, korean 107,920, kcd 16,226, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, umls 0, dropped_eval_text 261, out_organ 134,217, out_align 148,260, out_valid 166,257, out_sym 15,641
- 출처별 학습 항목: mondo_names 52,800, mondo_ko 27,564, kotypo 23,783, kcd 16,226, ko2 9,899, junk 8,440, gen_sym 7,034, profiles 6,901, ko3 5,524, gen_ko 2,973, train_queries 2,624, external 2,489
- 뺀 출처: umls
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 2.0; drop  → umls; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 44, "valid": 421, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 0}
- 내부 dev: en_pipeline 0.881, en_single 0.869, ko_pipeline 0.771, ko_single 0.763, align_top1 0.396, sym_top3 0.966, valid_threshold 0.995
- 벤치마크 single (dev): en 0.856, ko 0.79, concept_en 0.422, invalid_accept 0.0, symptom_top3 0.898

### s2es9 — S2d setup (S2c data, UMLS left out) with --consist 2.0 instead of 1.0

- 시작 2026-10-20 22:21, 커밋 `8839663` (커밋 안 된 변경 74개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 182,195, train 166,419, val 15,776, korean 107,979, kcd 16,273, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, umls 0, dropped_eval_text 261, out_organ 134,191, out_align 148,323, out_valid 166,419, out_sym 15,613
- 출처별 학습 항목: mondo_names 52,654, mondo_ko 27,568, kotypo 23,788, kcd 16,273, ko2 9,927, junk 8,440, gen_sym 7,050, profiles 6,956, ko3 5,553, gen_ko 3,026, train_queries 2,683, external 2,501
- 뺀 출처: umls
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 2.0; drop  → umls; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 45, "valid": 422, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.875, en_single 0.85, ko_pipeline 0.774, ko_single 0.771, align_top1 0.398, sym_top3 0.92, valid_threshold 0.995
- 벤치마크 single (dev): en 0.839, ko 0.789, concept_en 0.413, invalid_accept 0.0, symptom_top3 0.852

## S2 consistency weight 0.5

### s2fs7 — S2d setup (S2c data, UMLS left out) with --consist 0.5 instead of 1.0

- 시작 2026-10-20 20:50, 커밋 `8839663` (커밋 안 된 변경 71개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 182,197, train 166,457, val 15,740, korean 108,047, kcd 16,275, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, umls 0, dropped_eval_text 261, out_organ 134,315, out_align 148,368, out_valid 166,457, out_sym 15,803
- 출처별 학습 항목: mondo_names 52,677, mondo_ko 27,529, kotypo 23,736, kcd 16,275, ko2 9,962, junk 8,440, gen_sym 7,130, profiles 6,993, ko3 5,503, gen_ko 3,013, train_queries 2,689, external 2,510
- 뺀 출처: umls
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 0.5; drop  → umls
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 45, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.879, en_single 0.872, ko_pipeline 0.767, ko_single 0.772, align_top1 0.429, sym_top3 0.943, valid_threshold 0.995
- 벤치마크 single (dev): en 0.859, ko 0.792, concept_en 0.413, invalid_accept 0.0, symptom_top3 0.909

### s2fs8 — S2d setup (S2c data, UMLS left out) with --consist 0.5 instead of 1.0

- 시작 2026-10-20 22:36, 커밋 `8839663` (커밋 안 된 변경 77개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 182,148, train 166,257, val 15,891, korean 107,920, kcd 16,226, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, umls 0, dropped_eval_text 261, out_organ 134,217, out_align 148,260, out_valid 166,257, out_sym 15,641
- 출처별 학습 항목: mondo_names 52,800, mondo_ko 27,564, kotypo 23,783, kcd 16,226, ko2 9,899, junk 8,440, gen_sym 7,034, profiles 6,901, ko3 5,524, gen_ko 2,973, train_queries 2,624, external 2,489
- 뺀 출처: umls
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 0.5; drop  → umls; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 44, "valid": 421, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 0}
- 내부 dev: en_pipeline 0.881, en_single 0.871, ko_pipeline 0.777, ko_single 0.76, align_top1 0.431, sym_top3 0.955, valid_threshold 0.995
- 벤치마크 single (dev): en 0.865, ko 0.806, concept_en 0.43, invalid_accept 0.0, symptom_top3 0.898

### s2fs9 — S2d setup (S2c data, UMLS left out) with --consist 0.5 instead of 1.0

- 시작 2026-10-21 00:46, 커밋 `8839663` (커밋 안 된 변경 93개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 182,195, train 166,419, val 15,776, korean 107,979, kcd 16,273, gen_ko 4,849, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 30,731, ko2 11,261, kotypo 26,423, ko3 6,160, umls 0, dropped_eval_text 261, out_organ 134,191, out_align 148,323, out_valid 166,419, out_sym 15,613
- 출처별 학습 항목: mondo_names 52,654, mondo_ko 27,568, kotypo 23,788, kcd 16,273, ko2 9,927, junk 8,440, gen_sym 7,050, profiles 6,956, ko3 5,553, gen_ko 3,026, train_queries 2,683, external 2,501
- 뺀 출처: umls
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 0.5; drop  → umls; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 123, "align": 45, "valid": 422, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.883, en_single 0.866, ko_pipeline 0.787, ko_single 0.786, align_top1 0.426, sym_top3 0.909, valid_threshold 0.995
- 벤치마크 single (dev): en 0.869, ko 0.798, concept_en 0.4, invalid_accept 0.0, symptom_top3 0.818

## S5 English first

### s5as7 — English only: every Korean source left out, no consistency loss, no UMLS

- 시작 2026-10-21 00:39, 커밋 `8839663` (커밋 안 된 변경 91개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,430, val 8,132, korean 15,646, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,243, out_align 65,406, out_valid 81,430, out_sym 12,193
- 출처별 학습 항목: mondo_names 52,880, junk 8,440, profiles 7,660, gen_sym 7,080, train_queries 2,761, external 2,609
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 0.0; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd,umls
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.877, en_single 0.862, ko_pipeline 0.757, ko_single 0.757, align_top1 0.473, sym_top3 0.92, valid_threshold 0.99
- 벤치마크 single (dev): en 0.859, ko 0.757, concept_en 0.283, invalid_accept 0.0, symptom_top3 0.886

### s5as8 — English only: every Korean source left out, no consistency loss, no UMLS

- 시작 2026-10-21 01:14, 커밋 `8839663` (커밋 안 된 변경 96개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,213, val 8,349, korean 15,662, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,049, out_align 65,212, out_valid 81,213, out_sym 12,170
- 출처별 학습 항목: mondo_names 52,795, junk 8,440, profiles 7,638, gen_sym 7,060, train_queries 2,709, external 2,571
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 0.0; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd,umls; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.886, en_single 0.879, ko_pipeline 0.765, ko_single 0.771, align_top1 0.469, sym_top3 0.852, valid_threshold 0.9500000000000001
- 벤치마크 single (dev): en 0.879, ko 0.772, concept_en 0.274, invalid_accept 0.0, symptom_top3 0.818

### s5as9 — English only: every Korean source left out, no consistency loss, no UMLS

- 시작 2026-10-21 01:44, 커밋 `8839663` (커밋 안 된 변경 99개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,419, val 8,143, korean 15,658, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,370, out_align 65,473, out_valid 81,419, out_sym 12,287
- 출처별 학습 항목: mondo_names 52,857, junk 8,440, profiles 7,695, gen_sym 7,111, train_queries 2,719, external 2,597
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 0.0; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd,umls; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.875, en_single 0.863, ko_pipeline 0.761, ko_single 0.761, align_top1 0.467, sym_top3 0.966, valid_threshold 0.99
- 벤치마크 single (dev): en 0.847, ko 0.773, concept_en 0.304, invalid_accept 0.0, symptom_top3 0.955

### s5bs7 — English only plus UMLS names

- 시작 2026-10-21 03:34, 커밋 `8839663` (커밋 안 된 변경 117개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 193,712, train 174,855, val 18,857, korean 15,646, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 113,978, dropped_eval_text 210, out_organ 161,668, out_align 158,831, out_valid 174,855, out_sym 18,691
- 출처별 학습 항목: umls 102,242, mondo_names 45,808, junk 8,440, profiles 7,184, gen_sym 7,080, train_queries 2,433, external 1,668
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 0.0; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.87, en_single 0.861, ko_pipeline 0.733, ko_single 0.725, align_top1 0.495, sym_top3 0.898, valid_threshold 0.995
- 벤치마크 single (dev): en 0.855, ko 0.77, concept_en 0.343, invalid_accept 0.0, symptom_top3 0.875

### s5bs8 — English only plus UMLS names

- 시작 2026-10-21 04:29, 커밋 `8839663` (커밋 안 된 변경 122개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 193,712, train 174,532, val 19,180, korean 15,662, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 113,978, dropped_eval_text 210, out_organ 161,368, out_align 158,531, out_valid 174,532, out_sym 18,756
- 출처별 학습 항목: umls 102,159, mondo_names 45,683, junk 8,440, profiles 7,155, gen_sym 7,060, train_queries 2,388, external 1,647
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 0.0; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.874, en_single 0.866, ko_pipeline 0.737, ko_single 0.739, align_top1 0.529, sym_top3 0.886, valid_threshold 0.995
- 벤치마크 single (dev): en 0.873, ko 0.756, concept_en 0.352, invalid_accept 0.0, symptom_top3 0.818

### s5bs9 — English only plus UMLS names

- 시작 2026-10-21 05:26, 커밋 `8839663` (커밋 안 된 변경 128개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 193,712, train 175,159, val 18,553, korean 15,658, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 113,978, dropped_eval_text 210, out_organ 162,110, out_align 159,213, out_valid 175,159, out_sym 19,002
- 출처별 학습 항목: umls 102,597, mondo_names 45,759, junk 8,440, profiles 7,201, gen_sym 7,111, train_queries 2,403, external 1,648
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- s2ds7 대비 바뀐 것: umls 0 → 307,932행; compare_to s2cs7 → s2ds7; consist 1.0 → 0.0; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.879, en_single 0.872, ko_pipeline 0.777, ko_single 0.769, align_top1 0.502, sym_top3 0.966, valid_threshold 0.8500000000000001
- 벤치마크 single (dev): en 0.854, ko 0.757, concept_en 0.435, invalid_accept 0.067, symptom_top3 0.966

## E-en cambridgeltl/SapBERT-from-PubMedBERT-fulltext

### esap7 — English biomedical encoder cambridgeltl/SapBERT-from-PubMedBERT-fulltext, Korean sources left out

- 시작 2026-10-21 02:28, 커밋 `8839663` (커밋 안 된 변경 106개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,426, val 17,356, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,796
- 출처별 학습 항목: umls 103,167, mondo_names 45,768, junk 8,440, gen_sym 7,401, profiles_sym 3,710, profiles 2,884, train_queries 2,376, external 1,680
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ees7 대비 바뀐 것: backbone intfloat/multilingual-e5-large → cambridgeltl/SapBERT-from-PubMedBERT-fulltext; compare_to s2ds7 → ees7; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1256, valid_threshold 0.995, theta 0.8, theta_val_f1 {'0.5': 0.9236908064723989, '0.55': 0.9236908064723989, '0.6': 0.9238090624168513, '0.65': 0.9239513588283986, '0.7': 0.9240509044044232, '0.75': 0.9259333262977645, '0.8': 0.9320172308973547, '0.85': 0.9276050880278599, '0.9': 0.9197021653985161, '0.95': 0.9095489696189346, '1.0': 0.7806054525992958}, real_accepted 0.9765498962894676, minutes 65.0
- 벤치마크 scratch (dev): en 0.774, ko 0.114, concept_en 0.535, invalid_accept 0.067, symptom_top3 None

## E-en microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext

### ebmb7 — English biomedical encoder microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext, Korean sources left out

- 시작 2026-10-21 03:08, 커밋 `8839663` (커밋 안 된 변경 114개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,426, val 17,356, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,796
- 출처별 학습 항목: umls 103,167, mondo_names 45,768, junk 8,440, gen_sym 7,401, profiles_sym 3,710, profiles 2,884, train_queries 2,376, external 1,680
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ees7 대비 바뀐 것: backbone intfloat/multilingual-e5-large → microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext; compare_to s2ds7 → ees7; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1285, valid_threshold 0.995, theta 0.75, theta_val_f1 {'0.5': 0.9174337460986774, '0.55': 0.9174337460986774, '0.6': 0.9175160455639991, '0.65': 0.9177632227286616, '0.7': 0.9196598465043148, '0.75': 0.9301204864849986, '0.8': 0.9275757980199497, '0.85': 0.9223046662230068, '0.9': 0.9172390110130049, '0.95': 0.9070116243418975, '1.0': 0.7783702313799122}, real_accepted 0.9734385803180456, minutes 53.2
- 벤치마크 scratch (dev): en 0.78, ko 0.134, concept_en 0.522, invalid_accept 0.067, symptom_top3 None

### ebmb8 — English biomedical encoder microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext, Korean sources left out

- 시작 2026-10-21 04:41, 커밋 `8839663` (커밋 안 된 변경 125개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,405, val 17,377, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,834
- 출처별 학습 항목: umls 102,922, mondo_names 45,835, junk 8,440, gen_sym 7,400, profiles_sym 3,717, profiles 2,902, train_queries 2,475, external 1,714
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ees7 대비 바뀐 것: backbone intfloat/multilingual-e5-large → microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext; compare_to s2ds7 → ees7; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1219, valid_threshold 0.995, theta 0.7, theta_val_f1 {'0.5': 0.9265879873614685, '0.55': 0.9266338359437717, '0.6': 0.9267030430721124, '0.65': 0.9268689693593283, '0.7': 0.9273337464069663, '0.75': 0.9271519252459604, '0.8': 0.9266245955402984, '0.85': 0.9240548257929897, '0.9': 0.9190011397118198, '0.95': 0.910547263853487, '1.0': 0.7868484688359524}, real_accepted 0.9724923749784198, minutes 57.2
- 벤치마크 scratch (dev): en 0.77, ko 0.143, concept_en 0.557, invalid_accept 0.067, symptom_top3 None

### ebmb9 — English biomedical encoder microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext, Korean sources left out

- 시작 2026-10-21 05:39, 커밋 `8839663` (커밋 안 된 변경 131개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 174,591, val 18,191, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 331,784
- 출처별 학습 항목: umls 102,588, mondo_names 45,757, junk 8,440, gen_sym 7,220, profiles_sym 3,607, profiles 2,826, train_queries 2,430, external 1,723
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ees7 대비 바뀐 것: backbone intfloat/multilingual-e5-large → microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext; compare_to s2ds7 → ees7; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1218, valid_threshold 0.995, theta 0.8, theta_val_f1 {'0.5': 0.9246522877603012, '0.55': 0.9246522877603012, '0.6': 0.9248542784230609, '0.65': 0.9252239860008784, '0.7': 0.926525379788841, '0.75': 0.9277825611826178, '0.8': 0.9280657486588836, '0.85': 0.9252263565366683, '0.9': 0.918967293171497, '0.95': 0.9072105384483974, '1.0': 0.7838923029708529}, real_accepted 0.9699301852564455, minutes 65.7
- 벤치마크 scratch (dev): en 0.79, ko 0.128, concept_en 0.526, invalid_accept 0.0, symptom_top3 None

### ebmx7 — English biomedical encoder microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext, Korean sources left out, twice the epochs

- 시작 2026-10-21 06:46, 커밋 `8839663` (커밋 안 된 변경 141개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,426, val 17,356, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,796
- 출처별 학습 항목: umls 103,167, mondo_names 45,768, junk 8,440, gen_sym 7,401, profiles_sym 3,710, profiles 2,884, train_queries 2,376, external 1,680
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ees7 대비 바뀐 것: backbone intfloat/multilingual-e5-large → microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext; compare_to s2ds7 → ees7; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd; epochs 3 → 6; pre_epochs 2 → 3
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1302, valid_threshold 0.995, theta 0.8, theta_val_f1 {'0.5': 0.926474172484013, '0.55': 0.926474172484013, '0.6': 0.9265110309594259, '0.65': 0.9267689778423046, '0.7': 0.9267018149186262, '0.75': 0.9272562934787084, '0.8': 0.9273771926249227, '0.85': 0.9247770126845741, '0.9': 0.9190927296657273, '0.95': 0.9079384579891105, '1.0': 0.7827251419601097}, real_accepted 0.9760313436275639, minutes 90.6
- 벤치마크 scratch (dev): en 0.766, ko 0.135, concept_en 0.5, invalid_accept 0.067, symptom_top3 None

## E-en FremyCompany/BioLORD-2023

### ebio7 — English biomedical encoder FremyCompany/BioLORD-2023, Korean sources left out

- 시작 2026-10-21 04:02, 커밋 `8839663` (커밋 안 된 변경 120개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,426, val 17,356, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,796
- 출처별 학습 항목: umls 103,167, mondo_names 45,768, junk 8,440, gen_sym 7,401, profiles_sym 3,710, profiles 2,884, train_queries 2,376, external 1,680
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ees7 대비 바뀐 것: backbone intfloat/multilingual-e5-large → FremyCompany/BioLORD-2023; compare_to s2ds7 → ees7; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1249, valid_threshold 0.995, theta 0.75, theta_val_f1 {'0.5': 0.9250467387883167, '0.55': 0.9250735839336767, '0.6': 0.9250735839336767, '0.65': 0.9249789384369131, '0.7': 0.9258932693191864, '0.75': 0.930516742514319, '0.8': 0.9297929894883897, '0.85': 0.9261653421305268, '0.9': 0.921778227317491, '0.95': 0.9102821784675883, '1.0': 0.7836841742190489}, real_accepted 0.9900898824613966, minutes 38.1
- 벤치마크 scratch (dev): en 0.768, ko 0.1, concept_en 0.548, invalid_accept 0.0, symptom_top3 None

## E-en microsoft/BiomedNLP-BiomedBERT-large-uncased-abstract

### ebml7 — English biomedical encoder (large) microsoft/BiomedNLP-BiomedBERT-large-uncased-abstract, Korean sources left out

- 시작 2026-10-21 06:42, 커밋 `8839663` (커밋 안 된 변경 138개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,426, val 17,356, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,796
- 출처별 학습 항목: umls 103,167, mondo_names 45,768, junk 8,440, gen_sym 7,401, profiles_sym 3,710, profiles 2,884, train_queries 2,376, external 1,680
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ees7 대비 바뀐 것: backbone intfloat/multilingual-e5-large → microsoft/BiomedNLP-BiomedBERT-large-uncased-abstract; bs 64 → 32; compare_to s2ds7 → ees7; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd; lr 2e-05 → 1e-05
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1221, valid_threshold 0.995, theta 0.8, theta_val_f1 {'0.5': 0.9193163063001991, '0.55': 0.919323376418883, '0.6': 0.9193027818876435, '0.65': 0.9193065219407048, '0.7': 0.9196027696022833, '0.75': 0.921117596512098, '0.8': 0.9318775141329957, '0.85': 0.9299142491079377, '0.9': 0.9259155449123939, '0.95': 0.9161277164054107, '1.0': 0.8012251404310036}, real_accepted 0.9835791657063839, minutes 170.5
- 벤치마크 scratch (dev): en 0.791, ko 0.158, concept_en 0.552, invalid_accept 0.067, symptom_top3 None

### ebml8 — English biomedical encoder (large) microsoft/BiomedNLP-BiomedBERT-large-uncased-abstract, Korean sources left out

- 시작 2026-10-21 09:36, 커밋 `8839663` (커밋 안 된 변경 147개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,405, val 17,377, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,834
- 출처별 학습 항목: umls 102,922, mondo_names 45,835, junk 8,440, gen_sym 7,400, profiles_sym 3,717, profiles 2,902, train_queries 2,475, external 1,714
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ees7 대비 바뀐 것: backbone intfloat/multilingual-e5-large → microsoft/BiomedNLP-BiomedBERT-large-uncased-abstract; bs 64 → 32; compare_to s2ds7 → ees7; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd; lr 2e-05 → 1e-05; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 1, val_organ_loss 0.1186, valid_threshold 0.995, theta 0.85, theta_val_f1 {'0.5': 0.9265175483924636, '0.55': 0.9265175483924636, '0.6': 0.9265540718527123, '0.65': 0.9265540718527123, '0.7': 0.9268015307047512, '0.75': 0.9270614437748019, '0.8': 0.9277207540216644, '0.85': 0.9282048776649543, '0.9': 0.9252350789270193, '0.95': 0.9197161872406632, '1.0': 0.8053640188619956}, real_accepted 0.9636300857455257, minutes 209.3
- 벤치마크 scratch (dev): en 0.803, ko 0.151, concept_en 0.522, invalid_accept 0.0, symptom_top3 None

### ebml9 — English biomedical encoder (large) microsoft/BiomedNLP-BiomedBERT-large-uncased-abstract, Korean sources left out

- 시작 2026-10-21 10:33, 커밋 `8839663` (커밋 안 된 변경 152개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 174,591, val 18,191, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 331,784
- 출처별 학습 항목: umls 102,588, mondo_names 45,757, junk 8,440, gen_sym 7,220, profiles_sym 3,607, profiles 2,826, train_queries 2,430, external 1,723
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ees7 대비 바뀐 것: backbone intfloat/multilingual-e5-large → microsoft/BiomedNLP-BiomedBERT-large-uncased-abstract; bs 64 → 32; compare_to s2ds7 → ees7; drop  → gen_ko,ko2,kotypo,ko3,mondo_ko,kcd; lr 2e-05 → 1e-05; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 1, val_organ_loss 0.1167, valid_threshold 0.995, theta 0.75, theta_val_f1 {'0.5': 0.9278134195045804, '0.55': 0.9278134195045804, '0.6': 0.9278056211327246, '0.65': 0.9278659228448607, '0.7': 0.9282134730629561, '0.75': 0.9283647917175928, '0.8': 0.9279948832096874, '0.85': 0.9282257849758554, '0.9': 0.9263056702277278, '0.95': 0.9164284848299779, '1.0': 0.7967598192833998}, real_accepted 0.9627288219449178, minutes 188.7
- 벤치마크 scratch (dev): en 0.765, ko 0.139, concept_en 0.552, invalid_accept 0.0, symptom_top3 None

## S6 E4B English first

### s6as7 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss

- 시작 2026-10-21 09:25, 커밋 `8839663` (커밋 안 된 변경 144개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,430, val 8,132, korean 15,646, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,243, out_align 65,406, out_valid 81,430, out_sym 12,193
- 출처별 학습 항목: mondo_names 52,880, junk 8,440, profiles 7,660, gen_sym 7,080, train_queries 2,761, external 2,609
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: compare_to s2ds7 → s5as7; layers 18 → 24
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.872, en_single 0.863, ko_pipeline 0.705, ko_single 0.706, align_top1 0.489, sym_top3 0.955, valid_threshold 0.995
- 벤치마크 single (dev): en 0.862, ko 0.762, concept_en 0.196, invalid_accept 0.0, symptom_top3 0.909

### s6as8 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss

- 시작 2026-10-21 13:06, 커밋 `8839663` (커밋 안 된 변경 155개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,213, val 8,349, korean 15,662, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,049, out_align 65,212, out_valid 81,213, out_sym 12,170
- 출처별 학습 항목: mondo_names 52,795, junk 8,440, profiles 7,638, gen_sym 7,060, train_queries 2,709, external 2,571
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: compare_to s2ds7 → s5as7; layers 18 → 24; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.802, en_single 0.794, ko_pipeline 0.462, ko_single 0.462, align_top1 0.344, sym_top3 0.58, valid_threshold 0.99
- 벤치마크 single (dev): en 0.562, ko 0.342, concept_en 0.0, invalid_accept 0.0, symptom_top3 0.557

### s6as9 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss

- 시작 2026-10-21 14:01, 커밋 `8839663` (커밋 안 된 변경 161개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,419, val 8,143, korean 15,658, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,370, out_align 65,473, out_valid 81,419, out_sym 12,287
- 출처별 학습 항목: mondo_names 52,857, junk 8,440, profiles 7,695, gen_sym 7,111, train_queries 2,719, external 2,597
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: compare_to s2ds7 → s5as7; layers 18 → 24; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.89, en_single 0.881, ko_pipeline 0.795, ko_single 0.788, align_top1 0.424, sym_top3 0.977, valid_threshold 0.6500000000000001
- 벤치마크 single (dev): en 0.877, ko 0.793, concept_en 0.274, invalid_accept 0.0, symptom_top3 0.966

## S6 E4B English first, rank 32

### s6bs7 — E4B, first 24 of 42 layers, LoRA r32, S5a data: every Korean source and UMLS left out, no consistency loss

- 시작 2026-10-21 13:45, 커밋 `8839663` (커밋 안 된 변경 159개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,430, val 8,132, korean 15,646, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,243, out_align 65,406, out_valid 81,430, out_sym 12,193
- 출처별 학습 항목: mondo_names 52,880, junk 8,440, profiles 7,660, gen_sym 7,080, train_queries 2,761, external 2,609
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: compare_to s2ds7 → s5as7; layers 18 → 24; rank 16 → 32
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.791, en_single 0.791, ko_pipeline 0.397, ko_single 0.397, align_top1 0.325, sym_top3 0.477, valid_threshold 0.98
- 벤치마크 single (dev): en 0.504, ko 0.154, concept_en 0.004, invalid_accept 0.0, symptom_top3 0.5

## S6 E4B English first, 3 epochs

### s6cs7 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss, 3 epochs instead of 2

- 시작 2026-10-21 15:47, 커밋 `8839663` (커밋 안 된 변경 169개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,430, val 8,132, korean 15,646, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,243, out_align 65,406, out_valid 81,430, out_sym 12,193
- 출처별 학습 항목: mondo_names 52,880, junk 8,440, profiles 7,660, gen_sym 7,080, train_queries 2,761, external 2,609
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: compare_to s2ds7 → s5as7; epochs 2 → 3; layers 18 → 24
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.846, en_single 0.853, ko_pipeline 0.543, ko_single 0.542, align_top1 0.472, sym_top3 0.841, valid_threshold 0.995
- 벤치마크 single (dev): en 0.721, ko 0.556, concept_en 0.057, invalid_accept 0.067, symptom_top3 0.83

## S6 E4B English first, lr 1e-4

### s6ds8 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss, lr 1e-4 instead of 2e-4 (seed 8 collapsed at 2e-4)

- 시작 2026-10-21 16:07, 커밋 `8839663` (커밋 안 된 변경 171개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,213, val 8,349, korean 15,662, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,049, out_align 65,212, out_valid 81,213, out_sym 12,170
- 출처별 학습 항목: mondo_names 52,795, junk 8,440, profiles 7,638, gen_sym 7,060, train_queries 2,709, external 2,571
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: compare_to s2ds7 → s5as7; layers 18 → 24; lr 0.0002 → 0.0001; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.879, en_single 0.873, ko_pipeline 0.77, ko_single 0.775, align_top1 0.461, sym_top3 0.898, valid_threshold 0.97
- 벤치마크 single (dev): en 0.871, ko 0.802, concept_en 0.126, invalid_accept 0.0, symptom_top3 0.852

### s6ds7 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss, lr 1e-4 instead of 2e-4 (seed 8 collapsed at 2e-4)

- 시작 2026-10-21 17:37, 커밋 `8839663` (커밋 안 된 변경 177개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,430, val 8,132, korean 15,646, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,243, out_align 65,406, out_valid 81,430, out_sym 12,193
- 출처별 학습 항목: mondo_names 52,880, junk 8,440, profiles 7,660, gen_sym 7,080, train_queries 2,761, external 2,609
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: compare_to s2ds7 → s5as7; layers 18 → 24; lr 0.0002 → 0.0001
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.895, en_single 0.895, ko_pipeline 0.774, ko_single 0.774, align_top1 0.412, sym_top3 0.966, valid_threshold 0.995
- 벤치마크 single (dev): en 0.924, ko 0.847, concept_en 0.126, invalid_accept 0.0, symptom_top3 0.932

### s6ds9 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss, lr 1e-4 instead of 2e-4 (seed 8 collapsed at 2e-4)

- 시작 2026-10-21 19:09, 커밋 `8839663` (커밋 안 된 변경 185개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,419, val 8,143, korean 15,658, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,370, out_align 65,473, out_valid 81,419, out_sym 12,287
- 출처별 학습 항목: mondo_names 52,857, junk 8,440, profiles 7,695, gen_sym 7,111, train_queries 2,719, external 2,597
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: compare_to s2ds7 → s5as7; layers 18 → 24; lr 0.0002 → 0.0001; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.788, en_single 0.788, ko_pipeline 0.44, ko_single 0.44, align_top1 0.185, sym_top3 0.466, valid_threshold 0.9500000000000001
- 벤치마크 single (dev): en 0.468, ko 0.269, concept_en None, invalid_accept 0.0, symptom_top3 0.432

### s6ds10 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss, lr 1e-4 instead of 2e-4 (seed 8 collapsed at 2e-4)

- 시작 2026-10-21 20:22, 커밋 `8839663` (커밋 안 된 변경 188개), seed 10
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,442, val 8,120, korean 15,690, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,367, out_align 65,524, out_valid 81,442, out_sym 12,154
- 출처별 학습 항목: mondo_names 52,931, junk 8,440, profiles 7,611, gen_sym 7,042, train_queries 2,748, external 2,670
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: compare_to s2ds7 → s5as7; layers 18 → 24; lr 0.0002 → 0.0001; seed 7 → 10
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 398, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.863, en_single 0.863, ko_pipeline 0.657, ko_single 0.657, align_top1 0.15, sym_top3 0.739, valid_threshold 0.995
- 벤치마크 single (dev): en 0.801, ko 0.715, concept_en 0.0, invalid_accept 0.0, symptom_top3 0.693

### s6ds11 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss, lr 1e-4 instead of 2e-4 (seed 8 collapsed at 2e-4)

- 시작 2026-10-21 20:22, 커밋 `8839663` (커밋 안 된 변경 188개), seed 11
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,611, val 7,951, korean 15,682, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,356, out_align 65,493, out_valid 81,611, out_sym 12,334
- 출처별 학습 항목: mondo_names 52,918, junk 8,440, profiles 7,738, gen_sym 7,151, train_queries 2,753, external 2,611
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: compare_to s2ds7 → s5as7; layers 18 → 24; lr 0.0002 → 0.0001; seed 7 → 11
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 406, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.87, en_single 0.87, ko_pipeline 0.677, ko_single 0.677, align_top1 0.195, sym_top3 0.682, valid_threshold 0.97
- 벤치마크 single (dev): en 0.745, ko 0.655, concept_en None, invalid_accept 0.0, symptom_top3 0.659

## S6 E4B English first, lr 1e-4, clip 1.0

### s6es10 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss, lr 1e-4 and gradient clipping 1.0 (seeds 9-11 under-trained without it)

- 시작 2026-10-21 22:19, 커밋 `8839663` (커밋 안 된 변경 196개), seed 10
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,442, val 8,120, korean 15,690, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,367, out_align 65,524, out_valid 81,442, out_sym 12,154
- 출처별 학습 항목: mondo_names 52,931, junk 8,440, profiles 7,611, gen_sym 7,042, train_queries 2,748, external 2,670
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: clip None → 1.0; compare_to s2ds7 → s5as7; layers 18 → 24; lr 0.0002 → 0.0001; seed 7 → 10
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 398, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.884, en_single 0.884, ko_pipeline 0.773, ko_single 0.773, align_top1 0.364, sym_top3 0.807, valid_threshold 0.9000000000000001
- 벤치마크 single (dev): en 0.853, ko 0.773, concept_en 0.009, invalid_accept 0.0, symptom_top3 0.852

### s6es9 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss, lr 1e-4 and gradient clipping 1.0 (seeds 9-11 under-trained without it)

- 시작 2026-10-21 22:19, 커밋 `8839663` (커밋 안 된 변경 196개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,419, val 8,143, korean 15,658, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,370, out_align 65,473, out_valid 81,419, out_sym 12,287
- 출처별 학습 항목: mondo_names 52,857, junk 8,440, profiles 7,695, gen_sym 7,111, train_queries 2,719, external 2,597
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: clip None → 1.0; compare_to s2ds7 → s5as7; layers 18 → 24; lr 0.0002 → 0.0001; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.884, en_single 0.884, ko_pipeline 0.754, ko_single 0.77, align_top1 0.453, sym_top3 1.0, valid_threshold 0.995
- 벤치마크 single (dev): en 0.883, ko 0.822, concept_en 0.243, invalid_accept 0.0, symptom_top3 0.989

### s6es11 — E4B, first 24 of 42 layers, LoRA r16, S5a data: every Korean source and UMLS left out, no consistency loss, lr 1e-4 and gradient clipping 1.0 (seeds 9-11 under-trained without it)

- 시작 2026-10-22 00:13, 커밋 `8839663` (커밋 안 된 변경 204개), seed 11
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,611, val 7,951, korean 15,682, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,356, out_align 65,493, out_valid 81,611, out_sym 12,334
- 출처별 학습 항목: mondo_names 52,918, junk 8,440, profiles 7,738, gen_sym 7,151, train_queries 2,753, external 2,611
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: clip None → 1.0; compare_to s2ds7 → s5as7; layers 18 → 24; lr 0.0002 → 0.0001; seed 7 → 11
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 406, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["DM", "MONDO:0016367"], ["SCD", "MONDO:0007374"], ["HEP", "MONDO:0019799"], ["CED", "MONDO:0009032"], ["RA", "MONDO:0005272"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["RAD", "MONDO:0007483"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.819, en_single 0.819, ko_pipeline 0.596, ko_single 0.596, align_top1 0.184, sym_top3 0.625, valid_threshold 0.995
- 벤치마크 single (dev): en 0.653, ko 0.484, concept_en None, invalid_accept 0.067, symptom_top3 0.648

## XP2 BERT from random weights, our own pretraining

### xp2s7 — bert-medium pretrained 30h (training time) by masked LM on UMLS level-0 definitions and names, MONDO, Korean names, local medical documents, 300 PubMed baseline files; then the judge stages. p1 was stopped: its lr schedule counted corpus building time and reached 0 after ~4k steps

- 시작 2026-10-22 01:32, 커밋 `8839663` (커밋 안 된 변경 209개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- x1s7 대비 바뀐 것: backbone None → /data/hyeongchanahn/adctox/work/pretrain_p2; bs 256 → 128; compare_to x0s7 → x1s7; epochs 6 → 4; head_lr None → 0.001; lr 0.0005 → 0.0001; pre_epochs 6 → 3
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.146, valid_threshold 0.995, theta 0.7, theta_val_f1 {'0.5': 0.8527884032762097, '0.55': 0.8528429920531082, '0.6': 0.8538353259041606, '0.65': 0.8555732604281157, '0.7': 0.8555916126702188, '0.75': 0.8491234251270617, '0.8': 0.8370893851479251, '0.85': 0.8245120851687562, '0.9': 0.8122421463542797, '0.95': 0.795034656681036, '1.0': 0.7285051424528978}, real_accepted 0.9905994336060415, minutes 42.4
- 벤치마크 scratch (dev): en 0.695, ko 0.577, concept_en 0.422, invalid_accept 0.067, symptom_top3 None

## V5 labels

### v5as7 — S5a recipe (English only) on v5 labels, ADCTOX_LABELS=v5

- 시작 2026-10-22 15:37, 커밋 `8839663` (커밋 안 된 변경 214개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,430, val 8,132, korean 15,646, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,243, out_align 65,406, out_valid 81,430, out_sym 12,193
- 출처별 학습 항목: mondo_names 52,880, junk 8,440, profiles 7,660, gen_sym 7,080, train_queries 2,761, external 2,609
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: mondo_index 바뀜; clip None → 0.0; compare_to s2ds7 → s5as7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["RA", "MONDO:0005272"], ["SCD", "MONDO:0007374"], ["RAD", "MONDO:0007483"], ["CED", "MONDO:0009032"], ["DM", "MONDO:0016367"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["HEP", "MONDO:0019799"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.866, en_single 0.851, ko_pipeline 0.757, ko_single 0.741, align_top1 0.467, sym_top3 0.92, valid_threshold 0.9500000000000001
- 벤치마크 single (dev): en 0.844, ko 0.742, concept_en 0.291, invalid_accept 0.0, symptom_top3 0.886

### v5as8 — S5a recipe (English only) on v5 labels, ADCTOX_LABELS=v5

- 시작 2026-10-22 15:37, 커밋 `8839663` (커밋 안 된 변경 214개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,213, val 8,349, korean 15,662, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,049, out_align 65,212, out_valid 81,213, out_sym 12,170
- 출처별 학습 항목: mondo_names 52,795, junk 8,440, profiles 7,638, gen_sym 7,060, train_queries 2,709, external 2,571
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as8 대비 바뀐 것: mondo_index 바뀜; clip None → 0.0; compare_to s2ds7 → s5as8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["RA", "MONDO:0005272"], ["SCD", "MONDO:0007374"], ["RAD", "MONDO:0007483"], ["CED", "MONDO:0009032"], ["DM", "MONDO:0016367"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["HEP", "MONDO:0019799"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.867, en_single 0.855, ko_pipeline 0.73, ko_single 0.711, align_top1 0.466, sym_top3 0.852, valid_threshold 0.9000000000000001
- 벤치마크 single (dev): en 0.843, ko 0.72, concept_en 0.257, invalid_accept 0.0, symptom_top3 0.83

### v5as9 — S5a recipe (English only) on v5 labels, ADCTOX_LABELS=v5

- 시작 2026-10-22 15:37, 커밋 `8839663` (커밋 안 된 변경 213개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,419, val 8,143, korean 15,658, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,370, out_align 65,473, out_valid 81,419, out_sym 12,287
- 출처별 학습 항목: mondo_names 52,857, junk 8,440, profiles 7,695, gen_sym 7,111, train_queries 2,719, external 2,597
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as9 대비 바뀐 것: mondo_index 바뀜; clip None → 0.0; compare_to s2ds7 → s5as9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["RA", "MONDO:0005272"], ["SCD", "MONDO:0007374"], ["RAD", "MONDO:0007483"], ["CED", "MONDO:0009032"], ["DM", "MONDO:0016367"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["HEP", "MONDO:0019799"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.861, en_single 0.835, ko_pipeline 0.752, ko_single 0.725, align_top1 0.464, sym_top3 0.955, valid_threshold 0.9500000000000001
- 벤치마크 single (dev): en 0.843, ko 0.737, concept_en 0.317, invalid_accept 0.0, symptom_top3 0.955

### v5bs7 — S5a recipe (English only) on v5 labels, ADCTOX_LABELS=v5p

- 시작 2026-10-22 16:16, 커밋 `8839663` (커밋 안 된 변경 223개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,430, val 8,132, korean 15,646, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,243, out_align 65,406, out_valid 81,430, out_sym 12,193
- 출처별 학습 항목: mondo_names 52,880, junk 8,440, profiles 7,660, gen_sym 7,080, train_queries 2,761, external 2,609
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as7 대비 바뀐 것: mondo_index 바뀜; clip None → 0.0; compare_to s2ds7 → s5as7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["RA", "MONDO:0005272"], ["SCD", "MONDO:0007374"], ["RAD", "MONDO:0007483"], ["CED", "MONDO:0009032"], ["DM", "MONDO:0016367"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["HEP", "MONDO:0019799"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.866, en_single 0.838, ko_pipeline 0.744, ko_single 0.726, align_top1 0.468, sym_top3 0.943, valid_threshold 0.995
- 벤치마크 single (dev): en 0.832, ko 0.768, concept_en 0.283, invalid_accept 0.0, symptom_top3 0.92

### v5bs8 — S5a recipe (English only) on v5 labels, ADCTOX_LABELS=v5p

- 시작 2026-10-22 16:50, 커밋 `8839663` (커밋 안 된 변경 230개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,213, val 8,349, korean 15,662, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,049, out_align 65,212, out_valid 81,213, out_sym 12,170
- 출처별 학습 항목: mondo_names 52,795, junk 8,440, profiles 7,638, gen_sym 7,060, train_queries 2,709, external 2,571
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as8 대비 바뀐 것: mondo_index 바뀜; clip None → 0.0; compare_to s2ds7 → s5as8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["RA", "MONDO:0005272"], ["SCD", "MONDO:0007374"], ["RAD", "MONDO:0007483"], ["CED", "MONDO:0009032"], ["DM", "MONDO:0016367"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["HEP", "MONDO:0019799"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.876, en_single 0.855, ko_pipeline 0.701, ko_single 0.685, align_top1 0.465, sym_top3 0.875, valid_threshold 0.995
- 벤치마크 single (dev): en 0.865, ko 0.728, concept_en 0.27, invalid_accept 0.0, symptom_top3 0.818

### v5bs9 — S5a recipe (English only) on v5 labels, ADCTOX_LABELS=v5p

- 시작 2026-10-22 16:50, 커밋 `8839663` (커밋 안 된 변경 230개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,419, val 8,143, korean 15,658, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,370, out_align 65,473, out_valid 81,419, out_sym 12,287
- 출처별 학습 항목: mondo_names 52,857, junk 8,440, profiles 7,695, gen_sym 7,111, train_queries 2,719, external 2,597
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- s5as9 대비 바뀐 것: mondo_index 바뀜; clip None → 0.0; compare_to s2ds7 → s5as9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["RA", "MONDO:0005272"], ["SCD", "MONDO:0007374"], ["RAD", "MONDO:0007483"], ["CED", "MONDO:0009032"], ["DM", "MONDO:0016367"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["HEP", "MONDO:0019799"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.869, en_single 0.849, ko_pipeline 0.748, ko_single 0.734, align_top1 0.466, sym_top3 0.989, valid_threshold 0.9000000000000001
- 벤치마크 single (dev): en 0.83, ko 0.735, concept_en 0.317, invalid_accept 0.0, symptom_top3 0.955

## V5 labels encoder

### ebl5u7 — BiomedBERT-large on v5 labels, ADCTOX_LABELS=v5

- 시작 2026-10-22 17:21, 커밋 `8839663` (커밋 안 된 변경 236개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,426, val 17,356, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,796
- 출처별 학습 항목: umls 103,167, mondo_names 45,768, junk 8,440, gen_sym 7,401, profiles_sym 3,710, profiles 2,884, train_queries 2,376, external 1,680
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ebml7 대비 바뀐 것: mondo_index 바뀜; compare_to ees7 → ebml7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 1, val_organ_loss 0.1739, valid_threshold 0.995, theta 0.85, theta_val_f1 {'0.5': 0.9104667870268215, '0.55': 0.9104667870268215, '0.6': 0.910518326812215, '0.65': 0.9104819650741239, '0.7': 0.910754566077607, '0.75': 0.9111659519959441, '0.8': 0.9128706782594104, '0.85': 0.9218949459260298, '0.9': 0.9181839001423311, '0.95': 0.9062836322038, '1.0': 0.7318821266229372}, real_accepted 0.9778750864254436, minutes 209.7
- 벤치마크 scratch (dev): en 0.787, ko 0.156, concept_en 0.543, invalid_accept 0.0, symptom_top3 None

### ebl5u8 — BiomedBERT-large on v5 labels, ADCTOX_LABELS=v5

- 시작 2026-10-22 18:08, 커밋 `8839663` (커밋 안 된 변경 243개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,405, val 17,377, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,834
- 출처별 학습 항목: umls 102,922, mondo_names 45,835, junk 8,440, gen_sym 7,400, profiles_sym 3,717, profiles 2,902, train_queries 2,475, external 1,714
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ebml8 대비 바뀐 것: mondo_index 바뀜; compare_to ees7 → ebml8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 1, val_organ_loss 0.1583, valid_threshold 0.995, theta 0.8, theta_val_f1 {'0.5': 0.9195616005458945, '0.55': 0.9195616005458945, '0.6': 0.9195616005458945, '0.65': 0.9195616005458945, '0.7': 0.9198231992465913, '0.75': 0.9201949740518265, '0.8': 0.9206207108940799, '0.85': 0.9194751933837693, '0.9': 0.915940037187776, '0.95': 0.9086188349879237, '1.0': 0.7489214530219281}, real_accepted 0.9709385969960292, minutes 240.6
- 벤치마크 scratch (dev): en 0.775, ko 0.145, concept_en 0.539, invalid_accept 0.0, symptom_top3 None

### ebl5u9 — BiomedBERT-large on v5 labels, ADCTOX_LABELS=v5

- 시작 2026-10-22 18:09, 커밋 `8839663` (커밋 안 된 변경 245개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 174,591, val 18,191, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 331,784
- 출처별 학습 항목: umls 102,588, mondo_names 45,757, junk 8,440, gen_sym 7,220, profiles_sym 3,607, profiles 2,826, train_queries 2,430, external 1,723
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ebml9 대비 바뀐 것: mondo_index 바뀜; compare_to ees7 → ebml9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1558, valid_threshold 0.995, theta 0.8, theta_val_f1 {'0.5': 0.9106741421147451, '0.55': 0.9106741421147451, '0.6': 0.9106741421147451, '0.65': 0.9108104085543658, '0.7': 0.9113044231179188, '0.75': 0.9136682509084308, '0.8': 0.9269603162029438, '0.85': 0.9266514620439847, '0.9': 0.9222755875550412, '0.95': 0.9125341083348157, '1.0': 0.7542974852625286}, real_accepted 0.9888956077181024, minutes 241.4
- 벤치마크 scratch (dev): en 0.761, ko 0.142, concept_en 0.517, invalid_accept 0.067, symptom_top3 None

### ebl5p7 — BiomedBERT-large on v5 labels, ADCTOX_LABELS=v5p

- 시작 2026-10-22 22:10, 커밋 `8839663` (커밋 안 된 변경 261개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,426, val 17,356, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,796
- 출처별 학습 항목: umls 103,167, mondo_names 45,768, junk 8,440, gen_sym 7,401, profiles_sym 3,710, profiles 2,884, train_queries 2,376, external 1,680
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ebml7 대비 바뀐 것: mondo_index 바뀜; compare_to ees7 → ebml7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.117, valid_threshold 0.995, theta 0.8, theta_val_f1 {'0.5': 0.9274033149555307, '0.55': 0.9274033149555307, '0.6': 0.9274176984696537, '0.65': 0.9274466865658145, '0.7': 0.9282305480985665, '0.75': 0.9299520552999032, '0.8': 0.934579455514384, '0.85': 0.9322574387252529, '0.9': 0.9282100347330293, '0.95': 0.9197585038658437, '1.0': 0.810988750020581}, real_accepted 0.9795459783360221, minutes 196.1
- 벤치마크 scratch (dev): en 0.807, ko 0.131, concept_en 0.513, invalid_accept 0.067, symptom_top3 None

### ebl5p8 — BiomedBERT-large on v5 labels, ADCTOX_LABELS=v5p

- 시작 2026-10-22 22:11, 커밋 `8839663` (커밋 안 된 변경 264개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,405, val 17,377, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,834
- 출처별 학습 항목: umls 102,922, mondo_names 45,835, junk 8,440, gen_sym 7,400, profiles_sym 3,717, profiles 2,902, train_queries 2,475, external 1,714
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ebml8 대비 바뀐 것: mondo_index 바뀜; compare_to ees7 → ebml8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 1, val_organ_loss 0.1081, valid_threshold 0.995, theta 0.8, theta_val_f1 {'0.5': 0.9247731621954268, '0.55': 0.9247731621954268, '0.6': 0.9247731621954268, '0.65': 0.9247480714239829, '0.7': 0.9249961645998556, '0.75': 0.9256024504063357, '0.8': 0.926971397624744, '0.85': 0.9264263474576888, '0.9': 0.9249444395672727, '0.95': 0.9198948583965054, '1.0': 0.8155627020248939}, real_accepted 0.9726650169764631, minutes 199.6
- 벤치마크 scratch (dev): en 0.787, ko 0.123, concept_en 0.517, invalid_accept 0.067, symptom_top3 None

## V5.1 labels

### v51as7 — S5a recipe (English only) on v5.1 labels (malformation-only and 1-2-patient involved organs dropped), ADCTOX_LABELS=v51

- 시작 2026-10-22 20:52, 커밋 `8839663` (커밋 안 된 변경 249개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,430, val 8,132, korean 15,646, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,243, out_align 65,406, out_valid 81,430, out_sym 12,193
- 출처별 학습 항목: mondo_names 52,880, junk 8,440, profiles 7,660, gen_sym 7,080, train_queries 2,761, external 2,609
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- v5as7 대비 바뀐 것: mondo_index 바뀜; compare_to s5as7 → v5as7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["RA", "MONDO:0005272"], ["SCD", "MONDO:0007374"], ["RAD", "MONDO:0007483"], ["CED", "MONDO:0009032"], ["DM", "MONDO:0016367"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["HEP", "MONDO:0019799"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.865, en_single 0.861, ko_pipeline 0.757, ko_single 0.742, align_top1 0.474, sym_top3 0.92, valid_threshold 0.97
- 벤치마크 single (dev): en 0.859, ko 0.758, concept_en 0.326, invalid_accept 0.0, symptom_top3 0.886

### v51as8 — S5a recipe (English only) on v5.1 labels (malformation-only and 1-2-patient involved organs dropped), ADCTOX_LABELS=v51

- 시작 2026-10-22 21:27, 커밋 `8839663` (커밋 안 된 변경 254개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,213, val 8,349, korean 15,662, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,049, out_align 65,212, out_valid 81,213, out_sym 12,170
- 출처별 학습 항목: mondo_names 52,795, junk 8,440, profiles 7,638, gen_sym 7,060, train_queries 2,709, external 2,571
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- v5as8 대비 바뀐 것: mondo_index 바뀜; compare_to s5as8 → v5as8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["RA", "MONDO:0005272"], ["SCD", "MONDO:0007374"], ["RAD", "MONDO:0007483"], ["CED", "MONDO:0009032"], ["DM", "MONDO:0016367"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["HEP", "MONDO:0019799"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.872, en_single 0.859, ko_pipeline 0.759, ko_single 0.734, align_top1 0.465, sym_top3 0.864, valid_threshold 0.8
- 벤치마크 single (dev): en 0.863, ko 0.734, concept_en 0.27, invalid_accept 0.0, symptom_top3 0.83

### v51as9 — S5a recipe (English only) on v5.1 labels (malformation-only and 1-2-patient involved organs dropped), ADCTOX_LABELS=v51

- 시작 2026-10-22 22:01, 커밋 `8839663` (커밋 안 된 변경 258개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 89,562, train 81,419, val 8,143, korean 15,658, kcd 0, gen_ko 0, gen_sym 7,890, junk 2,344, junk_copies 4, mondo_ko 0, ko2 0, kotypo 0, ko3 0, umls 0, dropped_eval_text 210, out_organ 68,370, out_align 65,473, out_valid 81,419, out_sym 12,287
- 출처별 학습 항목: mondo_names 52,857, junk 8,440, profiles 7,695, gen_sym 7,111, train_queries 2,719, external 2,597
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko, umls
- v5as9 대비 바뀐 것: mondo_index 바뀜; compare_to s5as9 → v5as9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"organ": 120, "align": 40, "valid": 410, "sym": 101}, "eval_text_conflict_examples": [["LN", "MONDO:0002486"], ["RA", "MONDO:0005272"], ["SCD", "MONDO:0007374"], ["RAD", "MONDO:0007483"], ["CED", "MONDO:0009032"], ["DM", "MONDO:0016367"], ["RLS", "MONDO:0017413"], ["HS", "MONDO:0019395"], ["HEP", "MONDO:0019799"], ["CHB", "MONDO:0000468"], ["DM", "MONDO:0016107"], ["CP", "MONDO:0016064"], ["L-N", "MONDO:0010298"], ["AS", "MONDO:0007113"], ["fits", "MONDO:0001386"], ["UC", "MONDO:0040679"], ["PE", "MONDO:0001780"], ["HD", "MONDO:0018309"], ["CP", "MONDO:0006497"], ["PD", "MONDO:0002635"], ["HH", "MONDO:0002404"], ["nerve problem", "MONDO:0005244"], ["fatigue", "MONDO:0005154"], ["fatigue", "MONDO:0005300"], ["fatigue", "MONDO:0015925"], ["fatigue", "MONDO:0018881"], ["fatigue", "MONDO:0005420"], ["홍채섬모체염", "MONDO:0017634"], ["iridocyclitis", "MONDO:0017634"], ["anterior uveitis", "MONDO:0017634"]], "valid_conflicts": 1}
- 내부 dev: en_pipeline 0.864, en_single 0.848, ko_pipeline 0.717, ko_single 0.71, align_top1 0.475, sym_top3 0.966, valid_threshold 0.98
- 벤치마크 single (dev): en 0.845, ko 0.747, concept_en 0.304, invalid_accept 0.0, symptom_top3 0.955

## V5.1 labels encoder

### ebl519 — BiomedBERT-large on v5.1 labels, ADCTOX_LABELS=v51

- 시작 2026-10-22 22:37, 커밋 `8839663` (커밋 안 된 변경 268개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 174,591, val 18,191, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 331,784
- 출처별 학습 항목: umls 102,588, mondo_names 45,757, junk 8,440, gen_sym 7,220, profiles_sym 3,607, profiles 2,826, train_queries 2,430, external 1,723
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ebml9 대비 바뀐 것: mondo_index 바뀜; compare_to ees7 → ebml9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1487, valid_threshold 0.995, theta 0.8, theta_val_f1 {'0.5': 0.9049981933164624, '0.55': 0.9049981933164624, '0.6': 0.9051447713211913, '0.65': 0.9051567037700725, '0.7': 0.9063611110841894, '0.75': 0.9095640414177458, '0.8': 0.927795068683473, '0.85': 0.9273913971860746, '0.9': 0.9229961625308061, '0.95': 0.9128148843457832, '1.0': 0.7637726762156435}, real_accepted 0.9877411906986971, minutes 204.0
- 벤치마크 scratch (dev): en 0.769, ko 0.161, concept_en 0.543, invalid_accept 0.067, symptom_top3 None

### ebl517 — BiomedBERT-large on v5.1 labels, ADCTOX_LABELS=v51

- 시작 2026-10-22 23:23, 커밋 `8839663` (커밋 안 된 변경 271개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,426, val 17,356, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,796
- 출처별 학습 항목: umls 103,167, mondo_names 45,768, junk 8,440, gen_sym 7,401, profiles_sym 3,710, profiles 2,884, train_queries 2,376, external 1,680
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ebml7 대비 바뀐 것: mondo_index 바뀜; compare_to ees7 → ebml7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 1, val_organ_loss 0.1656, valid_threshold 0.995, theta 0.85, theta_val_f1 {'0.5': 0.9118704660195532, '0.55': 0.9118704660195532, '0.6': 0.9119249450458902, '0.65': 0.9119776459025262, '0.7': 0.9123149108041205, '0.75': 0.9127114691624636, '0.8': 0.913783178660773, '0.85': 0.9231633799858158, '0.9': 0.9192013425655661, '0.95': 0.9080172469008753, '1.0': 0.7403445923312728}, real_accepted 0.9757432588153953, minutes 197.6
- 벤치마크 scratch (dev): en 0.778, ko 0.153, concept_en 0.509, invalid_accept 0.0, symptom_top3 None

### ebl518 — BiomedBERT-large on v5.1 labels, ADCTOX_LABELS=v51

- 시작 2026-10-23 01:27, 커밋 `8839663` (커밋 안 된 변경 277개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 192,782, train 175,405, val 17,377, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 376, pairs 332,834
- 출처별 학습 항목: umls 102,922, mondo_names 45,835, junk 8,440, gen_sym 7,400, profiles_sym 3,717, profiles 2,902, train_queries 2,475, external 1,714
- 뺀 출처: gen_ko, kcd, ko2, ko3, kotypo, mondo_ko
- ebml8 대비 바뀐 것: mondo_index 바뀜; compare_to ees7 → ebml8; distill_w None → 1.0
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 1, val_organ_loss 0.1497, valid_threshold 0.995, theta 0.8, theta_val_f1 {'0.5': 0.9176390024867077, '0.55': 0.9176390024867077, '0.6': 0.9176390024867077, '0.65': 0.9176314222938379, '0.7': 0.9176870034562264, '0.75': 0.9187459188222683, '0.8': 0.9204332003290526, '0.85': 0.9194467793568115, '0.9': 0.9170001944197396, '0.95': 0.9092968974828912, '1.0': 0.7586881335925564}, real_accepted 0.9752546469471141, minutes 173.4
- 벤치마크 scratch (dev): en 0.776, ko 0.15, concept_en 0.535, invalid_accept 0.067, symptom_top3 None

## X2 distillation

### x2bs7 — XP2 backbone (p2), v5.1 labels, no distillation (control for x2a)

- 시작 2026-10-23 00:14, 커밋 `8839663` (커밋 안 된 변경 272개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- xp2s7 대비 바뀐 것: mondo_index 바뀜; compare_to x1s7 → xp2s7; distill_w None → 1.0
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1804, valid_threshold 0.995, theta 0.7, theta_val_f1 {'0.5': 0.8450592628798077, '0.55': 0.8450735725337003, '0.6': 0.8456015459187088, '0.65': 0.8475249732112692, '0.7': 0.8480256941354326, '0.75': 0.8400809108373981, '0.8': 0.8263433639747219, '0.85': 0.8110115700257636, '0.9': 0.7947384963876529, '0.95': 0.7720623083203868, '1.0': 0.6903400590648601}, real_accepted 0.9912287602265576, minutes 43.4
- 벤치마크 scratch (dev): en 0.661, ko 0.534, concept_en 0.43, invalid_accept 0.067, symptom_top3 None

### x2as7 — XP2 backbone (p2), v5.1 labels, Gemma v51a x3 distillation (weight 1)

- 시작 2026-10-23 04:24, 커밋 `8839663` (커밋 안 된 변경 287개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- xp2s7 대비 바뀐 것: mondo_index 바뀜; compare_to x1s7 → xp2s7; distill None → /data/hyeongchanahn/adctox/work/distill/teacher_v51.npz; distill_w None → 1.0
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1708, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8472846494732481, '0.55': 0.8473062197114406, '0.6': 0.8479319056642548, '0.65': 0.8489645677727148, '0.7': 0.8484676741153337, '0.75': 0.8406762089651327, '0.8': 0.8273794801615959, '0.85': 0.8127948941832306, '0.9': 0.7969634024564988, '0.95': 0.7756696205644764, '1.0': 0.699423837557274}, real_accepted 0.9826541850220264, minutes 45.9
- 벤치마크 scratch (dev): en 0.683, ko 0.55, concept_en 0.43, invalid_accept 0.0, symptom_top3 None

### x2as8 — XP2 backbone (p2), v5.1 labels, Gemma v51a x3 distillation (weight 1)

- 시작 2026-10-23 04:24, 커밋 `8839663` (커밋 안 된 변경 287개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 466,129
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- xp2s7 대비 바뀐 것: mondo_index 바뀜; compare_to x1s7 → xp2s7; distill None → /data/hyeongchanahn/adctox/work/distill/teacher_v51.npz; distill_w None → 1.0; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1765, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8408622453130234, '0.55': 0.8408968377761368, '0.6': 0.8414524509507301, '0.65': 0.8419467602178107, '0.7': 0.840894458148803, '0.75': 0.8324376701670371, '0.8': 0.8188438397696712, '0.85': 0.8006269263834824, '0.9': 0.7823635944232372, '0.95': 0.7618078068751549, '1.0': 0.6850987071683386}, real_accepted 0.9771849907350216, minutes 48.3
- 벤치마크 scratch (dev): en 0.66, ko 0.531, concept_en 0.439, invalid_accept 0.0, symptom_top3 None

### x2bs8 — XP2 backbone (p2), v5.1 labels, no distillation (control for x2a)

- 시작 2026-10-23 05:11, 커밋 `8839663` (커밋 안 된 변경 290개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 466,129
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- xp2s7 대비 바뀐 것: mondo_index 바뀜; compare_to x1s7 → xp2s7; distill_w None → 1.0; seed 7 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1884, valid_threshold 0.995, theta 0.7, theta_val_f1 {'0.5': 0.8326259853989247, '0.55': 0.8326696912734561, '0.6': 0.8331417589546753, '0.65': 0.8334012738116334, '0.7': 0.8338545098146865, '0.75': 0.8271229578247379, '0.8': 0.812897065817208, '0.85': 0.7947716155023469, '0.9': 0.7744716133609659, '0.95': 0.7544887874209745, '1.0': 0.6721378732236987}, real_accepted 0.9856778875849289, minutes 43.9
- 벤치마크 scratch (dev): en 0.66, ko 0.555, concept_en 0.413, invalid_accept 0.0, symptom_top3 None

### x2as9 — XP2 backbone (p2), v5.1 labels, Gemma v51a x3 distillation (weight 1)

- 시작 2026-10-23 05:14, 커밋 `8839663` (커밋 안 된 변경 293개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,631
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- xp2s7 대비 바뀐 것: mondo_index 바뀜; compare_to x1s7 → xp2s7; distill None → /data/hyeongchanahn/adctox/work/distill/teacher_v51.npz; distill_w None → 1.0; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1795, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8468216546087706, '0.55': 0.8468445932502415, '0.6': 0.846930021888478, '0.65': 0.8477167956908478, '0.7': 0.8460980420071065, '0.75': 0.838557610299361, '0.8': 0.8235024846288878, '0.85': 0.8050166286485292, '0.9': 0.7863507127599821, '0.95': 0.764915030932067, '1.0': 0.6878738436630024}, real_accepted 0.9846817775358656, minutes 54.6
- 벤치마크 scratch (dev): en 0.656, ko 0.55, concept_en 0.435, invalid_accept 0.0, symptom_top3 None

### x2bs9 — XP2 backbone (p2), v5.1 labels, no distillation (control for x2a)

- 시작 2026-10-23 05:56, 커밋 `8839663` (커밋 안 된 변경 296개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,631
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- xp2s7 대비 바뀐 것: mondo_index 바뀜; compare_to x1s7 → xp2s7; distill_w None → 1.0; seed 7 → 9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.19, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8446730100386299, '0.55': 0.8447427454847017, '0.6': 0.8449869972513491, '0.65': 0.8456973996853799, '0.7': 0.8425500302123319, '0.75': 0.8326677708349559, '0.8': 0.8170725648053911, '0.85': 0.7975746724957783, '0.9': 0.7778107471739513, '0.95': 0.7544640417081309, '1.0': 0.6738104788637073}, real_accepted 0.9909801329652813, minutes 41.9
- 벤치마크 scratch (dev): en 0.627, ko 0.532, concept_en 0.426, invalid_accept 0.067, symptom_top3 None

### x2cs7 — XP2 backbone, v5.1 labels, distillation on the big teacher set (470k texts incl. UMLS Disorders names), weight 1

- 시작 2026-10-23 06:42, 커밋 `8839663` (커밋 안 된 변경 301개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- x2as7 대비 바뀐 것: compare_to xp2s7 → x2as7; distill /data/hyeongchanahn/adctox/work/distill/teacher_v51.npz → /data/hyeongchanahn/adctox/work/distill/teacher_v51_big.npz
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1719, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8480490894345927, '0.55': 0.848023709913035, '0.6': 0.8484644089864435, '0.65': 0.8501873748462082, '0.7': 0.8497021470042898, '0.75': 0.8417272048077523, '0.8': 0.8283189994255966, '0.85': 0.8148568405676156, '0.9': 0.7983504768965647, '0.95': 0.7766906901060129, '1.0': 0.7003549531654372}, real_accepted 0.9814348646947766, minutes 50.1
- 벤치마크 scratch (dev): en 0.686, ko 0.525, concept_en 0.439, invalid_accept 0.067, symptom_top3 None

### x2ds7 — XP2 backbone, v5.1 labels, distillation on the big teacher set, weight 0.5

- 시작 2026-10-23 06:42, 커밋 `8839663` (커밋 안 된 변경 301개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- x2as7 대비 바뀐 것: compare_to xp2s7 → x2as7; distill /data/hyeongchanahn/adctox/work/distill/teacher_v51.npz → /data/hyeongchanahn/adctox/work/distill/teacher_v51_big.npz; distill_w 1.0 → 0.5
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1741, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8467436078053399, '0.55': 0.8467436078053399, '0.6': 0.8470404522511886, '0.65': 0.8488808123871863, '0.7': 0.8482274658776817, '0.75': 0.8403183086238951, '0.8': 0.8268362065300736, '0.85': 0.8128528420139044, '0.9': 0.796573881267461, '0.95': 0.7744397860887057, '1.0': 0.6956508672277979}, real_accepted 0.9827328508495909, minutes 50.4
- 벤치마크 scratch (dev): en 0.69, ko 0.545, concept_en 0.439, invalid_accept 0.067, symptom_top3 None

### x2cs8 — XP2 backbone, v5.1 labels, distillation on the big teacher set (470k texts incl. UMLS Disorders names), weight 1

- 시작 2026-10-23 07:33, 커밋 `8839663` (커밋 안 된 변경 307개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 466,129
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- x2as8 대비 바뀐 것: compare_to xp2s7 → x2as8; distill /data/hyeongchanahn/adctox/work/distill/teacher_v51.npz → /data/hyeongchanahn/adctox/work/distill/teacher_v51_big.npz
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1783, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8391990213827086, '0.55': 0.8392219320748631, '0.6': 0.8397889384261167, '0.65': 0.8402110061903182, '0.7': 0.8392524111812294, '0.75': 0.8313122093558845, '0.8': 0.8172322962687791, '0.85': 0.7987573519231815, '0.9': 0.7813354098184282, '0.95': 0.7608058306772799, '1.0': 0.6826063411648489}, real_accepted 0.9776482396541075, minutes 46.4
- 벤치마크 scratch (dev): en 0.666, ko 0.532, concept_en 0.43, invalid_accept 0.0, symptom_top3 None

### x2ds8 — XP2 backbone, v5.1 labels, distillation on the big teacher set, weight 0.5

- 시작 2026-10-23 07:33, 커밋 `8839663` (커밋 안 된 변경 307개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 466,129
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- x2as8 대비 바뀐 것: compare_to xp2s7 → x2as8; distill /data/hyeongchanahn/adctox/work/distill/teacher_v51.npz → /data/hyeongchanahn/adctox/work/distill/teacher_v51_big.npz; distill_w 1.0 → 0.5
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1796, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8408544142342745, '0.55': 0.8409335274106744, '0.6': 0.8411598889195748, '0.65': 0.8419635467980437, '0.7': 0.8402512168992325, '0.75': 0.8301544043284463, '0.8': 0.8154658235367122, '0.85': 0.7976989149881497, '0.9': 0.7791280817780695, '0.95': 0.7593897156693983, '1.0': 0.6806625237174018}, real_accepted 0.9780342804200124, minutes 47.2
- 벤치마크 scratch (dev): en 0.661, ko 0.542, concept_en 0.452, invalid_accept 0.0, symptom_top3 None

### x2cs9 — XP2 backbone, v5.1 labels, distillation on the big teacher set (470k texts incl. UMLS Disorders names), weight 1

- 시작 2026-10-23 08:21, 커밋 `8839663` (커밋 안 된 변경 311개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,631
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- x2as9 대비 바뀐 것: compare_to xp2s7 → x2as9; distill /data/hyeongchanahn/adctox/work/distill/teacher_v51.npz → /data/hyeongchanahn/adctox/work/distill/teacher_v51_big.npz
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1811, valid_threshold 0.995, theta 0.55, theta_val_f1 {'0.5': 0.8505575083325956, '0.55': 0.850596655768244, '0.6': 0.8504395218621533, '0.65': 0.8501752382321794, '0.7': 0.8490119068803591, '0.75': 0.8390776496865541, '0.8': 0.824007420537459, '0.85': 0.8043173756335451, '0.9': 0.7861340622956502, '0.95': 0.7631578360171183, '1.0': 0.6838198732047341}, real_accepted 0.982621204463279, minutes 49.0
- 벤치마크 scratch (dev): en 0.682, ko 0.532, concept_en 0.443, invalid_accept 0.067, symptom_top3 None

### x2ds9 — XP2 backbone, v5.1 labels, distillation on the big teacher set, weight 0.5

- 시작 2026-10-23 08:22, 커밋 `8839663` (커밋 안 된 변경 314개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,631
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- x2as9 대비 바뀐 것: compare_to xp2s7 → x2as9; distill /data/hyeongchanahn/adctox/work/distill/teacher_v51.npz → /data/hyeongchanahn/adctox/work/distill/teacher_v51_big.npz; distill_w 1.0 → 0.5
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1835, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8481318834404653, '0.55': 0.848178637973574, '0.6': 0.8482409544285253, '0.65': 0.8484821902980142, '0.7': 0.8472408094995953, '0.75': 0.8376783665256355, '0.8': 0.8213572032209107, '0.85': 0.8021219360336882, '0.9': 0.7833835479914174, '0.95': 0.7606845743561913, '1.0': 0.6801826658795898}, real_accepted 0.9848761712219587, minutes 48.4
- 벤치마크 scratch (dev): en 0.65, ko 0.55, concept_en 0.457, invalid_accept 0.067, symptom_top3 None

### x2es7 — XP2 backbone, v5.1 labels, big teacher set, distillation weight 2

- 시작 2026-10-24 08:54, 커밋 `8839663` (커밋 안 된 변경 319개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- x2cs7 대비 바뀐 것: compare_to x2as7 → x2cs7; distill_w 1.0 → 2.0
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1703, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8461127682526932, '0.55': 0.8461127682526932, '0.6': 0.8461480614208734, '0.65': 0.8479783058802463, '0.7': 0.8472283016899523, '0.75': 0.8400454775739501, '0.8': 0.827993497241952, '0.85': 0.8150564858327056, '0.9': 0.7979808671273037, '0.95': 0.776328602735208, '1.0': 0.7011813852628715}, real_accepted 0.9784455632473253, minutes 49.8
- 벤치마크 scratch (dev): en 0.681, ko 0.545, concept_en 0.448, invalid_accept 0.067, symptom_top3 None

### x2fs7 — XP2 backbone, v5.1 labels, big teacher set, weight 1, 8 judge epochs

- 시작 2026-10-24 08:54, 커밋 `8839663` (커밋 안 된 변경 319개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- x2cs7 대비 바뀐 것: compare_to x2as7 → x2cs7; epochs 4 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 8, val_organ_loss 0.1621, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8557183508829801, '0.55': 0.8557704849227358, '0.6': 0.8561750719564869, '0.65': 0.8582061775936084, '0.7': 0.8581551749872293, '0.75': 0.8526243193473082, '0.8': 0.8416288139609372, '0.85': 0.8296121800631944, '0.9': 0.8136124581988446, '0.95': 0.7912625007658227, '1.0': 0.7179107310348676}, real_accepted 0.9861548143486469, minutes 78.6
- 벤치마크 scratch (dev): en 0.695, ko 0.584, concept_en 0.404, invalid_accept 0.067, symptom_top3 None

### x2es8 — XP2 backbone, v5.1 labels, big teacher set, distillation weight 2

- 시작 2026-10-24 09:45, 커밋 `8839663` (커밋 안 된 변경 323개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 466,129
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- x2cs8 대비 바뀐 것: compare_to x2as8 → x2cs8; distill_w 1.0 → 2.0
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1757, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8388654325084004, '0.55': 0.8388969878574591, '0.6': 0.8393712072635326, '0.65': 0.8406886710023099, '0.7': 0.8399755414702312, '0.75': 0.8311026606004333, '0.8': 0.817382906564698, '0.85': 0.7996202169338493, '0.9': 0.7824459604124792, '0.95': 0.7627503453270008, '1.0': 0.6851694246774963}, real_accepted 0.9741352686843731, minutes 46.5
- 벤치마크 scratch (dev): en 0.691, ko 0.55, concept_en 0.443, invalid_accept 0.0, symptom_top3 None

### x2fs8 — XP2 backbone, v5.1 labels, big teacher set, weight 1, 8 judge epochs

- 시작 2026-10-24 10:14, 커밋 `8839663` (커밋 안 된 변경 326개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 466,129
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- x2cs8 대비 바뀐 것: compare_to x2as8 → x2cs8; epochs 4 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 7, val_organ_loss 0.1684, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8519048278335538, '0.55': 0.8519106902817027, '0.6': 0.8524849116603908, '0.65': 0.854043555520806, '0.7': 0.8521217932312994, '0.75': 0.8441741531170008, '0.8': 0.8327349110612292, '0.85': 0.816687185968518, '0.9': 0.7977752146685797, '0.95': 0.7796037343264353, '1.0': 0.7063391108733567}, real_accepted 0.9815858554663373, minutes 73.5
- 벤치마크 scratch (dev): en 0.661, ko 0.584, concept_en 0.43, invalid_accept 0.133, symptom_top3 None

### x2es9 — XP2 backbone, v5.1 labels, big teacher set, distillation weight 2

- 시작 2026-10-24 10:33, 커밋 `8839663` (커밋 안 된 변경 329개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,631
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- x2cs9 대비 바뀐 것: compare_to x2as9 → x2cs9; distill_w 1.0 → 2.0
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.179, valid_threshold 0.995, theta 0.6, theta_val_f1 {'0.5': 0.8488613673250447, '0.55': 0.8488490297610054, '0.6': 0.8492016302259913, '0.65': 0.8489837151093463, '0.7': 0.8486411799135427, '0.75': 0.8387239335816611, '0.8': 0.8237283816783878, '0.85': 0.8048946202602123, '0.9': 0.7860469744661086, '0.95': 0.7650101621089855, '1.0': 0.685029209064154}, real_accepted 0.9797441779091015, minutes 47.4
- 벤치마크 scratch (dev): en 0.681, ko 0.547, concept_en 0.461, invalid_accept 0.067, symptom_top3 None

### x2fs9 — XP2 backbone, v5.1 labels, big teacher set, weight 1, 8 judge epochs

- 시작 2026-10-24 11:22, 커밋 `8839663` (커밋 안 된 변경 332개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,631
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- x2cs9 대비 바뀐 것: compare_to x2as9 → x2cs9; epochs 4 → 8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 8, val_organ_loss 0.1706, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8579893436284638, '0.55': 0.8580187566930904, '0.6': 0.8583608471313907, '0.65': 0.8593623497752512, '0.7': 0.8591684675292123, '0.75': 0.8492311814082344, '0.8': 0.8350187497348046, '0.85': 0.8178744403092862, '0.9': 0.7990604440348275, '0.95': 0.7777032976096253, '1.0': 0.7050668922715668}, real_accepted 0.9868589868201081, minutes 70.8
- 벤치마크 scratch (dev): en 0.689, ko 0.588, concept_en 0.439, invalid_accept 0.067, symptom_top3 None

## X2 p3 preview

### x2p24s7 — p3 bert-base wwm 24h checkpoint, x2c distillation setting (big teacher, weight 1), v5.1 labels

- 시작 2026-10-24 12:37, 커밋 `8839663` (커밋 안 된 변경 337개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- x2cs7 대비 바뀐 것: backbone /data/hyeongchanahn/adctox/work/pretrain_p2 → /data/hyeongchanahn/adctox/work/pretrain_p3_24h; compare_to x2as7 → x2cs7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1523, valid_threshold 0.995, theta 0.7, theta_val_f1 {'0.5': 0.8799157979518646, '0.55': 0.8799064388403847, '0.6': 0.8804800087357667, '0.65': 0.8828472794308446, '0.7': 0.8828601328637734, '0.75': 0.8765291470434277, '0.8': 0.8669645556403858, '0.85': 0.8531911179324354, '0.9': 0.8350715762999024, '0.95': 0.8108586161109166, '1.0': 0.7388380249512677}, real_accepted 0.989104782882316, minutes 62.7
- 벤치마크 scratch (dev): en 0.708, ko 0.639, concept_en 0.5, invalid_accept 0.0, symptom_top3 None

### x2p24s8 — p3 bert-base wwm 24h checkpoint, x2c distillation setting (big teacher, weight 1), v5.1 labels

- 시작 2026-10-24 12:37, 커밋 `8839663` (커밋 안 된 변경 337개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 466,129
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- x2cs8 대비 바뀐 것: backbone /data/hyeongchanahn/adctox/work/pretrain_p2 → /data/hyeongchanahn/adctox/work/pretrain_p3_24h; compare_to x2as8 → x2cs8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1604, valid_threshold 0.995, theta 0.7, theta_val_f1 {'0.5': 0.874308159434441, '0.55': 0.8742261832766041, '0.6': 0.8742001052425569, '0.65': 0.8757361041059346, '0.7': 0.8763425300295165, '0.75': 0.8696773925883186, '0.8': 0.8600800789248935, '0.85': 0.8440969142557978, '0.9': 0.8213133803235901, '0.95': 0.7973767587632634, '1.0': 0.7295460150196434}, real_accepted 0.9857164916615194, minutes 66.8
- 벤치마크 scratch (dev): en 0.717, ko 0.636, concept_en 0.461, invalid_accept 0.0, symptom_top3 None

### x2p24s9 — p3 bert-base wwm 24h checkpoint, x2c distillation setting (big teacher, weight 1), v5.1 labels

- 시작 2026-10-24 13:41, 커밋 `8839663` (커밋 안 된 변경 341개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,631
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- x2cs9 대비 바뀐 것: backbone /data/hyeongchanahn/adctox/work/pretrain_p2 → /data/hyeongchanahn/adctox/work/pretrain_p3_24h; compare_to x2as9 → x2cs9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1616, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8799521925579806, '0.55': 0.8800946540894874, '0.6': 0.8806769347280905, '0.65': 0.8820786263191079, '0.7': 0.8813012704364833, '0.75': 0.8738861468956903, '0.8': 0.8624586099431691, '0.85': 0.8459887261665991, '0.9': 0.8221070025820147, '0.95': 0.7972230188829332, '1.0': 0.7251467695247158}, real_accepted 0.9890750748415691, minutes 63.2
- 벤치마크 scratch (dev): en 0.692, ko 0.63, concept_en 0.487, invalid_accept 0.0, symptom_top3 None

## X2 final

### x2s7 — X2: p3 bert-base wwm, UMLS/MONDO/HPO x10, batch 1024, final weights (cosine schedule ended at ~47h; 48h checkpoint), x2c distillation (big teacher, weight 1), v5.1 labels

- 시작 2026-10-25 00:05, 커밋 `8839663` (커밋 안 된 변경 346개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- x2p24s7 대비 바뀐 것: backbone /data/hyeongchanahn/adctox/work/pretrain_p3_24h → /data/hyeongchanahn/adctox/work/pretrain_p3_48h; compare_to x2cs7 → x2p24s7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1502, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8846959077509005, '0.55': 0.8847420093254913, '0.6': 0.8854933240645633, '0.65': 0.8868154225459693, '0.7': 0.885277475466299, '0.75': 0.8785660151865842, '0.8': 0.8688435401650365, '0.85': 0.8547408503302175, '0.9': 0.836749707657166, '0.95': 0.8124243046334136, '1.0': 0.7422841058319114}, real_accepted 0.9881607929515418, minutes 66.4
- 벤치마크 scratch (dev): en 0.697, ko 0.645, concept_en 0.478, invalid_accept 0.0, symptom_top3 None

### x2s8 — X2: p3 bert-base wwm, UMLS/MONDO/HPO x10, batch 1024, final weights (cosine schedule ended at ~47h; 48h checkpoint), x2c distillation (big teacher, weight 1), v5.1 labels

- 시작 2026-10-25 00:05, 커밋 `8839663` (커밋 안 된 변경 346개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 466,129
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- x2p24s8 대비 바뀐 것: backbone /data/hyeongchanahn/adctox/work/pretrain_p3_24h → /data/hyeongchanahn/adctox/work/pretrain_p3_48h; compare_to x2cs8 → x2p24s8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1611, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.871065956467137, '0.55': 0.871071226639464, '0.6': 0.8715525306092984, '0.65': 0.8732403311245326, '0.7': 0.8731285054270349, '0.75': 0.8672336288430825, '0.8': 0.8575699528518618, '0.85': 0.8432455910647675, '0.9': 0.820931900217491, '0.95': 0.7954311962973674, '1.0': 0.725520037558382}, real_accepted 0.982666769610871, minutes 68.4
- 벤치마크 scratch (dev): en 0.702, ko 0.616, concept_en 0.478, invalid_accept 0.067, symptom_top3 None

### x2s9 — X2: p3 bert-base wwm, UMLS/MONDO/HPO x10, batch 1024, final weights (cosine schedule ended at ~47h; 48h checkpoint), x2c distillation (big teacher, weight 1), v5.1 labels

- 시작 2026-10-25 00:05, 커밋 `8839663` (커밋 안 된 변경 346개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,631
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- x2p24s9 대비 바뀐 것: backbone /data/hyeongchanahn/adctox/work/pretrain_p3_24h → /data/hyeongchanahn/adctox/work/pretrain_p3_48h; compare_to x2cs9 → x2p24s9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1602, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8829233602550445, '0.55': 0.8828902989562667, '0.6': 0.8833622721524897, '0.65': 0.8842848578599196, '0.7': 0.8820838109366177, '0.75': 0.8752777083419582, '0.8': 0.8638026830289312, '0.85': 0.8478375366562886, '0.9': 0.8246105089593342, '0.95': 0.8004667534153552, '1.0': 0.729696206927473}, real_accepted 0.9889584386299133, minutes 68.8
- 벤치마크 scratch (dev): en 0.707, ko 0.622, concept_en 0.474, invalid_accept 0.0, symptom_top3 None

## X2 evidence reader

### evsmoke — 

- 시작 2026-10-25 20:16, 커밋 `1f4c6fb` (커밋 안 된 변경 2개), seed 7
- 데이터: 
- 내부 dev: val_f1 0.20219241054578863, thr [0.40000000000000013, 0.40000000000000013, 0.3500000000000001, 0.40000000000000013, 0.45000000000000007, 0.40000000000000013, 0.45000000000000007, 0.5000000000000001, 0.1, 0.40000000000000013, 0.3500000000000001, 0.40000000000000013, 0.5000000000000001]

### ev2s7 — evidence reader on the p3 48h backbone (X2's), v5.1 labels, CPU, maxlen 192

- 시작 2026-10-25 20:38, 커밋 `1f4c6fb` (커밋 안 된 변경 3개), seed 7
- 데이터: 
- evsmoke 대비 바뀐 것: epochs 3 → 2; smoke True → False
- 내부 dev: val_f1 0.8684352118248084, thr [0.6000000000000002, 0.30000000000000004, 0.6500000000000001, 0.5500000000000002, 0.3500000000000001, 0.3500000000000001, 0.5000000000000001, 0.6000000000000002, 0.7000000000000002, 0.5000000000000001, 0.40000000000000013, 0.6000000000000002, 0.20000000000000004]

### ev3s7 — evidence reader on the X3 backbone (pretrain_p4), v5.1 labels, GPU, maxlen 256

- 시작 2026-10-26 22:13, 커밋 `62e25d1` (커밋 안 된 변경 4개), seed 7
- 데이터: 
- ev2s7 대비 바뀐 것: backbone /data/hyeongchanahn/adctox/work/pretrain_p3_48h → /data/hyeongchanahn/adctox/work/pretrain_p4; epochs 2 → 3
- 내부 dev: val_f1 0.8768261347803783, thr [0.5500000000000002, 0.45000000000000007, 0.5500000000000002, 0.5000000000000001, 0.9000000000000002, 0.3500000000000001, 0.7500000000000002, 0.3500000000000001, 0.5500000000000002, 0.6500000000000001, 0.7000000000000002, 0.5500000000000002, 0.40000000000000013]

### ev2s8 — evidence reader on the X2 backbone (pretrain_p3_48h), v5.1 labels, GPU, maxlen 256

- 시작 2026-10-26 22:15, 커밋 `62e25d1` (커밋 안 된 변경 5개), seed 8
- 데이터: 
- ev3s7 대비 바뀐 것: backbone /data/hyeongchanahn/adctox/work/pretrain_p4 → /data/hyeongchanahn/adctox/work/pretrain_p3_48h; seed 7 → 8
- 내부 dev: val_f1 0.8813667170970182, thr [0.3500000000000001, 0.3500000000000001, 0.40000000000000013, 0.6000000000000002, 0.45000000000000007, 0.40000000000000013, 0.7000000000000002, 0.40000000000000013, 0.7000000000000002, 0.40000000000000013, 0.40000000000000013, 0.30000000000000004, 0.25000000000000006]

### ev2s9 — evidence reader on the X2 backbone (pretrain_p3_48h), v5.1 labels, GPU, maxlen 256

- 시작 2026-10-26 22:15, 커밋 `62e25d1` (커밋 안 된 변경 6개), seed 9
- 데이터: 
- ev2s8 대비 바뀐 것: seed 8 → 9
- 내부 dev: val_f1 0.8834790884723872, thr [0.25000000000000006, 0.40000000000000013, 0.30000000000000004, 0.3500000000000001, 0.5500000000000002, 0.6500000000000001, 0.7000000000000002, 0.45000000000000007, 0.6000000000000002, 0.40000000000000013, 0.45000000000000007, 0.30000000000000004, 0.5000000000000001]

### ev3s8 — evidence reader on the X3 backbone (pretrain_p4), v5.1 labels, GPU, maxlen 256, seed 8

- 시작 2026-10-31 02:58, 커밋 `007ecd4` (커밋 안 된 변경 16개), seed 8
- 데이터: 
- ev2s9 대비 바뀐 것: backbone /data/hyeongchanahn/adctox/work/pretrain_p3_48h → /data/hyeongchanahn/adctox/work/pretrain_p4; seed 9 → 8
- 내부 dev: val_f1 0.8861690228583016, thr [0.45000000000000007, 0.5500000000000002, 0.40000000000000013, 0.5000000000000001, 0.8000000000000002, 0.7500000000000002, 0.40000000000000013, 0.45000000000000007, 0.6500000000000001, 0.30000000000000004, 0.30000000000000004, 0.5500000000000002, 0.30000000000000004]

### ev3s9 — evidence reader on the X3 backbone (pretrain_p4), v5.1 labels, GPU, maxlen 256, seed 9

- 시작 2026-10-31 05:35, 커밋 `95fcb49` (커밋 안 된 변경 13개), seed 9
- 데이터: 
- ev3s8 대비 바뀐 것: seed 8 → 9
- 내부 dev: val_f1 0.8772211428207165, thr [0.45000000000000007, 0.25000000000000006, 0.6500000000000001, 0.3500000000000001, 0.8000000000000002, 0.5000000000000001, 0.5500000000000002, 0.40000000000000013, 0.6000000000000002, 0.40000000000000013, 0.5000000000000001, 0.7000000000000002, 0.30000000000000004]

## X3 bert-large

### x3s7 — X3: p4 bert-large (335M) from scratch, 3 GPUs, 32h, wwm, UMLS/MONDO/HPO x10, batch 1152, lr 2e-4; judge lr 5e-5; x2c distillation (big teacher, weight 1), v5.1 labels

- 시작 2026-10-26 19:51, 커밋 `62e25d1` (커밋 안 된 변경 1개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,769
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- x2s7 대비 바뀐 것: add_pairs None → ; backbone /data/hyeongchanahn/adctox/work/pretrain_p3_48h → /data/hyeongchanahn/adctox/work/pretrain_p4; compare_to x2p24s7 → x2s7; lr 0.0001 → 5e-05
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1508, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8891960303002603, '0.55': 0.8892810396699394, '0.6': 0.8897347825024723, '0.65': 0.8904089737323411, '0.7': 0.8899491514971755, '0.75': 0.8868542105035533, '0.8': 0.8788202120932419, '0.85': 0.8656109460200556, '0.9': 0.8475141567750923, '0.95': 0.8200608340578566, '1.0': 0.7498328934505663}, real_accepted 0.9905994336060415, minutes 143.3
- 벤치마크 scratch (dev): en 0.72, ko 0.642, concept_en 0.496, invalid_accept 0.0, symptom_top3 None

### x3s8 — X3: p4 bert-large (335M) from scratch, 3 GPUs, 32h, wwm, UMLS/MONDO/HPO x10, batch 1152, lr 2e-4; judge lr 5e-5; x2c distillation (big teacher, weight 1), v5.1 labels

- 시작 2026-10-26 19:51, 커밋 `62e25d1` (커밋 안 된 변경 1개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 466,129
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- x2s8 대비 바뀐 것: add_pairs None → ; backbone /data/hyeongchanahn/adctox/work/pretrain_p3_48h → /data/hyeongchanahn/adctox/work/pretrain_p4; compare_to x2p24s8 → x2s8; lr 0.0001 → 5e-05
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1593, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.884614961409164, '0.55': 0.8846328442270217, '0.6': 0.8853209982007415, '0.65': 0.8856354825240478, '0.7': 0.8844014928638846, '0.75': 0.8805145693246643, '0.8': 0.8706871141677456, '0.85': 0.8565630899127678, '0.9': 0.8350118402745506, '0.95': 0.8041598907336183, '1.0': 0.7346992254787518}, real_accepted 0.9873378628783199, minutes 143.0
- 벤치마크 scratch (dev): en 0.711, ko 0.612, concept_en 0.504, invalid_accept 0.0, symptom_top3 None

### x3s9 — X3: p4 bert-large (335M) from scratch, 3 GPUs, 32h, wwm, UMLS/MONDO/HPO x10, batch 1152, lr 2e-4; judge lr 5e-5; x2c distillation (big teacher, weight 1), v5.1 labels

- 시작 2026-10-26 19:51, 커밋 `62e25d1` (커밋 안 된 변경 1개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 466,631
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- x2s9 대비 바뀐 것: add_pairs None → ; backbone /data/hyeongchanahn/adctox/work/pretrain_p3_48h → /data/hyeongchanahn/adctox/work/pretrain_p4; compare_to x2p24s9 → x2s9; lr 0.0001 → 5e-05
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1602, valid_threshold 0.995, theta 0.7, theta_val_f1 {'0.5': 0.8871868586267363, '0.55': 0.8872309497951641, '0.6': 0.8877148577287071, '0.65': 0.888774336328457, '0.7': 0.8896296787229633, '0.75': 0.8850158100045318, '0.8': 0.8766426652914651, '0.85': 0.8607999964092345, '0.9': 0.8367032205225432, '0.95': 0.8067282074990241, '1.0': 0.7327907677384532}, real_accepted 0.9913689203374675, minutes 141.0
- 벤치마크 scratch (dev): en 0.717, ko 0.618, concept_en 0.478, invalid_accept 0.0, symptom_top3 None

## X2 typo and abbreviation pairs

### x2ts7 — X2 + opt-in name pairs: English misspellings of MONDO names (entypo) and SPECIALIST LRABR abbreviations (lrabr)

- 시작 2026-10-26 22:20, 커밋 `62e25d1` (커밋 안 된 변경 7개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 522,763
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- x2s7 대비 바뀐 것: add_pairs None → entypo,lrabr; compare_to x2p24s7 → x2s7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1515, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8842054361384097, '0.55': 0.8842245967190857, '0.6': 0.8848776323156595, '0.65': 0.8852788446303704, '0.7': 0.8846614528729533, '0.75': 0.8785860299705847, '0.8': 0.8668967708321773, '0.85': 0.8543979983868206, '0.9': 0.8351677164349355, '0.95': 0.810540849803176, '1.0': 0.7411521592119261}, real_accepted 0.9900094398993078, minutes 66.9
- 벤치마크 scratch (dev): en 0.698, ko 0.613, concept_en 0.491, invalid_accept 0.0, symptom_top3 None

### x2ts8 — X2 + opt-in name pairs: English misspellings of MONDO names (entypo) and SPECIALIST LRABR abbreviations (lrabr)

- 시작 2026-10-26 22:20, 커밋 `62e25d1` (커밋 안 된 변경 7개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 522,083
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- x2s8 대비 바뀐 것: add_pairs None → entypo,lrabr; compare_to x2p24s8 → x2s8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1595, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8811278804174203, '0.55': 0.881239985568338, '0.6': 0.8816093961651694, '0.65': 0.8817714068711493, '0.7': 0.8797313106405464, '0.75': 0.8732367718652878, '0.8': 0.864225851797117, '0.85': 0.8473197738925268, '0.9': 0.8218277895304585, '0.95': 0.7968076530187136, '1.0': 0.729315386495101}, real_accepted 0.9862183446571958, minutes 66.4
- 벤치마크 scratch (dev): en 0.711, ko 0.628, concept_en 0.522, invalid_accept 0.0, symptom_top3 None

### x2ts9 — X2 + opt-in name pairs: English misspellings of MONDO names (entypo) and SPECIALIST LRABR abbreviations (lrabr)

- 시작 2026-10-26 22:23, 커밋 `62e25d1` (커밋 안 된 변경 9개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 522,591
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- x2s9 대비 바뀐 것: add_pairs None → entypo,lrabr; compare_to x2p24s9 → x2s9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 4, val_organ_loss 0.1593, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8846689211597235, '0.55': 0.8847241939662831, '0.6': 0.8859912338148668, '0.65': 0.8868056896304295, '0.7': 0.8853979941411632, '0.75': 0.8792260148662095, '0.8': 0.8659824516996822, '0.85': 0.849671503094015, '0.9': 0.8284802618421507, '0.95': 0.8014650702444434, '1.0': 0.7302653871157142}, real_accepted 0.989697134637067, minutes 65.5
- 벤치마크 scratch (dev): en 0.661, ko 0.66, concept_en 0.487, invalid_accept 0.0, symptom_top3 None

## X3 typo and abbreviation pairs

### x3ts7 — X3 (p4 bert-large, judge lr 5e-5, x2c distillation) + opt-in name pairs: English misspellings of MONDO names (entypo) and SPECIALIST LRABR abbreviations (lrabr). The X3 + pairs cell the 10-26 table left out for lack of GPU time

- 시작 2026-10-31 00:28, 커밋 `007ecd4` (커밋 안 된 변경 3개), seed 7
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,303, train 259,879, val 25,424, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 522,763
- 출처별 학습 항목: umls 102,602, mondo_names 45,705, mondo_ko 27,794, kotypo 23,781, kcd 16,272, ko2 9,872, junk 8,440, gen_sym 7,340, ko3 5,390, profiles_sym 3,679, gen_ko 2,864, train_queries 2,376, profiles 2,146, external 1,618
- x3s7 대비 바뀐 것: add_pairs  → entypo,lrabr; compare_to x2s7 → x3s7
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1497, valid_threshold 0.995, theta 0.65, theta_val_f1 {'0.5': 0.8896253407696, '0.55': 0.8897705501524964, '0.6': 0.8904397322563948, '0.65': 0.8917494712446281, '0.7': 0.8904390984075057, '0.75': 0.8864678684122809, '0.8': 0.8791298380780089, '0.85': 0.8679777931649431, '0.9': 0.8481005841170605, '0.95': 0.8184460415843074, '1.0': 0.7506133301567477}, real_accepted 0.9898521082441787, minutes 147.0
- 벤치마크 scratch (dev): en 0.697, ko 0.653, concept_en 0.5, invalid_accept 0.0, symptom_top3 None

### x3ts8 — X3 (p4 bert-large, judge lr 5e-5, x2c distillation) + opt-in name pairs: English misspellings of MONDO names (entypo) and SPECIALIST LRABR abbreviations (lrabr). The X3 + pairs cell the 10-26 table left out for lack of GPU time

- 시작 2026-10-31 03:08, 커밋 `007ecd4` (커밋 안 된 변경 17개), seed 8
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,256, train 259,352, val 25,904, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 420, pairs 522,083
- 출처별 학습 항목: umls 102,393, mondo_names 45,674, mondo_ko 27,748, kotypo 23,723, kcd 16,225, ko2 9,872, junk 8,440, gen_sym 7,323, ko3 5,392, profiles_sym 3,668, gen_ko 2,830, train_queries 2,337, profiles 2,155, external 1,572
- x3s8 대비 바뀐 것: add_pairs  → entypo,lrabr; compare_to x2s8 → x3s8
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 2, val_organ_loss 0.1603, valid_threshold 0.995, theta 0.7, theta_val_f1 {'0.5': 0.8805695733217883, '0.55': 0.8806414056437161, '0.6': 0.8809991363558093, '0.65': 0.8820220571790001, '0.7': 0.8822814384651557, '0.75': 0.8784294844946055, '0.8': 0.8694725007030512, '0.85': 0.8556522389111911, '0.9': 0.8340228524117328, '0.95': 0.8048717305440334, '1.0': 0.7304385874619405}, real_accepted 0.987415071031501, minutes 145.9
- 벤치마크 scratch (dev): en 0.714, ko 0.628, concept_en 0.491, invalid_accept 0.0, symptom_top3 None

### x3ts9 — X3 (p4 bert-large, judge lr 5e-5, x2c distillation) + opt-in name pairs: English misspellings of MONDO names (entypo) and SPECIALIST LRABR abbreviations (lrabr). The X3 + pairs cell the 10-26 table left out for lack of GPU time

- 시작 2026-10-31 05:44, 커밋 `95fcb49` (커밋 안 된 변경 14개), seed 9
- 데이터: organ_labels 53,479, train_queries 36,209, profiles 790, gen_ko 4,849, gen_sym 7,890, gen_junk 2,344, mondo_ko 23,258, gen_ko2 11,261, gen_kotypo 26,423, gen_ko3 6,160, umls 307,932
- 학습 항목: total 285,302, train 259,581, val 25,721, junk_copies 4, dropped_eval_text_gold 0, dropped_eval_text_other 421, pairs 522,591
- 출처별 학습 항목: umls 102,196, mondo_names 45,720, mondo_ko 27,812, kotypo 23,774, kcd 16,271, ko2 9,843, junk 8,440, gen_sym 7,351, ko3 5,377, profiles_sym 3,688, gen_ko 2,904, train_queries 2,405, profiles 2,176, external 1,624
- x3s9 대비 바뀐 것: add_pairs  → entypo,lrabr; compare_to x2s9 → x3s9
- 학습 전 검사: {"sym_language_mismatch": 0, "eval_text_leak": {}, "eval_text_conflict": {"valid": 120}, "eval_text_conflict_examples": [], "valid_conflicts": 1}
- 내부 dev: epochs_best 3, val_organ_loss 0.1591, valid_threshold 0.995, theta 0.7, theta_val_f1 {'0.5': 0.890903034919314, '0.55': 0.8908791353423552, '0.6': 0.8910088625940331, '0.65': 0.892334269090479, '0.7': 0.8924126379595639, '0.75': 0.8885330281686655, '0.8': 0.8805736235264998, '0.85': 0.8648129009306462, '0.9': 0.8419609031252236, '0.95': 0.8108652225345845, '1.0': 0.7367332850004635}, real_accepted 0.9910967691769371, minutes 146.6
- 벤치마크 scratch (dev): en 0.686, ko 0.651, concept_en 0.487, invalid_accept 0.0, symptom_top3 None

