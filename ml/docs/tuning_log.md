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

