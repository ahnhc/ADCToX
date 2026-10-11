# 추천기 개정 내역 — 검토 의견 반영 (2026-10-11)

`ml/docs/recommender_technical_report.md`(이전 구현, 커밋 `2dfcf7f`)에 대한 외부 검토 의견을 단계별로 반영한 기록입니다.
각 항목마다 변경 내용, 위치, 확인 방법을 적었습니다. 이전 보고서는 비교용으로 남겨 둡니다.

## 단계 1 — 투여 제한을 점수와 분리

| 검토 의견 | 변경 | 위치 | 확인 |
|---|---|---|---|
| 8.6/8.7, 4장, 용량 조절이 빠짐 | 14개 라벨의 4장, 8.6, 8.7, 2장(용량 조절)과, 8장이 침묵할 때는 12.3을 읽어 86개 규칙으로 정리 | `conf/label_restrictions.yaml` | 인용문 86/86이 라벨 원문과 글자 그대로 일치(`test_every_restriction_quote_is_verbatim_in_its_label`) |
| Contraindicated / Avoid / Insufficient data / Monitor를 구분해야 함 | 다섯 범주(+ no_adjustment)와 "no label statement"를 둠. 침묵은 insufficient data와 같은 등급으로 처리 | `ml/restrictions.py` `CATS`, `TIER` | `test_label_silence_is_reported_not_read_as_safe` |
| CKD 3이라는 진단만으로 CrCl < 60이라고 확정할 수 없음 | 입력하지 않은 수치는 구간 전체로 두고 가능한 범주를 모두 보여 줌("Avoid?"). 결정에 필요한 검사를 표시 | `restrictions._grid`, `judge` | `test_missing_lab_is_not_guessed_from_the_diagnosis` |
| 심각한 제한이 다른 장기의 낮은 점수로 상쇄되면 안 됨 | 정렬의 첫 번째 키가 제한 등급(입력하지 않은 수치는 최악의 경우로 가정). 그다음이 확정 여부, 그다음이 장기 근거 | `recommend.recommend` | `test_restriction_outranks_any_organ_burden` |
| 실제 수치 입력 | CLcr, 빌리루빈·AST(×ULN), Child-Pugh, LVEF, UGT1A1*28 입력(CLI 옵션과 메뉴) | `recommend.parse_args`, `_ask_labs` | – |
| HBV, ITP, LVEF, QT 등 임상 확인 항목 | 질환별 체크리스트. 라벨 근거 항목은 해당 ADC 이름을 함께 표시. HBV는 ASCO PCO를 인용 | `conf/patient_checks.yaml`, `recommend.checks` | – |

검토에서 지적한 네 사례의 현재 판정은 다음과 같습니다.
- Pivekimab: CLcr < 60이면 renal Avoid, 빌리루빈 > 1.5×ULN이면 hepatic Avoid(간 쪽은 이번에 추가로 발견).
- Mirvetuximab: 빌리루빈 > 1.5×ULN이면 Avoid, ESRD는 Insufficient data.
- Dato-DXd: CLcr 30–<90이면 Monitor(ILD 증가), < 30이면 Insufficient data.
- Sacituzumab: 설사가 boxed로 인식됨(단계 2).

## 단계 2 — 약물 근거 데이터 정비

| 검토 의견 | 변경 | 위치 | 확인 |
|---|---|---|---|
| 대문자 AND 분리 실패(sacituzumab 설사) | boxed 제목 분리를 대소문자 무시로 변경 | `src/adctox/validation/label_change.py` | `test_boxed_headline_splits_upper_case_and`, `test_sacituzumab_diarrhea_is_boxed_in_the_evidence` |
| "WARNINGS AND PRECAUTIONS"를 boxed로 오인 | section 5 제목은 제외 | 같은 파일 | `test_section5_title_is_not_a_boxed_warning` |
| 제목의 첫 장기만 선택 | `axes_for_heading` 추가: 제목이 가리키는 모든 장기. 기존 `axis_for_heading`은 label-change 집계용이라 그대로 둠 | 같은 파일 | `test_axes_for_heading_returns_every_organ...` |
| Grade 3과 4를 시험 간에 합산 | 표(시험) 안에서만 합산 | `ml/drug_evidence.py`, `ml/matcher2.py` | `test_grade_3_and_4_are_not_added_across_trials` (T-DM1 23% → 17%) |
| 결측을 0이나 0.5로 처리 | 대체하지 않음. "no label table"과 "G>=3 not reported"를 구분해 표시. 발생률은 정렬에 쓰지 않고 참고로만 표시 | `ml/drug_evidence.py` | `test_missing_incidence_is_flagged_not_zero` |
| 백분위 변환으로 절대 발생률이 사라짐 | 백분위를 없애고 절대 %를 표시 | 같은 파일 | – |
| 병용·단독·암종을 구분하지 않음 | 단독요법 행을 우선하고, 병용요법 값만 있으면 [combo], lab 표면 [lab]으로 표시. 출처 표 이름을 보존 | 같은 파일 | – |
| Gemtuzumab과 Pivekimab 벡터가 동일 | 발생률을 0.5로 대체하던 처리를 없앰. 남는 동점은 "=" 표시. 두 약물은 제한 규칙(신장·간)에서 서로 구별됨 | `recommend.recommend` | `test_identical_evidence_is_shown_as_a_tie_not_an_order` |
| 근거 없는 장기가 상위 장기로 표시됨 | 표에는 라벨 경고(Boxed/W&P)가 있는 환자 장기만 표시 | `recommend.render` | `test_organs_shown_carry_label_evidence` |

단계 2에서 하지 않은 것: 워크북에 전사되지 않은 라벨 6장 임상 이상반응 표(예: sacituzumab 설사 Grade≥3)를 새로 전사하지 않았습니다. 해당 칸은 "not reported"로 표시됩니다.

## 단계 3 — 점수 함수 재설계

| 검토 의견 | 변경 |
|---|---|
| 가중평균의 분모 때문에 $\partial R/\partial s_k < 0$이 가능 | 가중평균, 분모, 기본 가중치 1, λ를 모두 없앰. 정렬 키는 (제한 최악 등급, 확정 제한 등급, B, Wn). B = Σ s_o (환자 장기 중 boxed), Wn = Σ s_o (W&P). 둘 다 s에 대해 단조 증가 |
| min-max 정규화로 최저 약물이 늘 0 | 정규화를 없애고 %도 표시하지 않음. 동점은 "=" |
| 중증 독성별 위험을 따로 보여야 함 | 열을 "Boxed on your organs", "Warn on your organs", "Boxed elsewhere"로 나눔. `--detail`을 주면 장기별 라벨 제목, 절대 발생률, 출처 표시 |
| 여러 장기의 경고가 평균으로 상쇄됨 | 평균을 쓰지 않음. 환자 장기의 boxed 경고는 B에 그대로 더해지고 W&P로 상쇄되지 않음(사전식 정렬) |

확인: `test_more_vulnerability_never_lowers_concern...`, `test_no_min_max_rescaling_and_no_percentage`, `test_boxed_warning_on_the_patients_organ_is_visible`.

B와 Wn을 boxed와 W&P로 나눈 것은 "boxed 하나가 W&P 몇 개보다 무겁다"는 환산 비율(이전 1.0 대 0.6)을 정하지 않기 위해서입니다. 대신 "boxed가 W&P보다 항상 먼저"라는 가정이 들어갑니다.

## 단계 4 — 학습 모델의 효용 검증

- 질문을 실제 사용 방식에 맞췄습니다: "자기 장기(수작업)에 학습값을 더하면 나아지는가?" (`ml/eval_learned_addon.py`, f ∈ {0.25, 0.5}를 미리 정함)
- 결과(비순환: 발생률 백분위 점수, 정답 = 라벨 경고 장기, 40개 질환 × 12개 ADC):
  - 자기 장기만: AUROC 0.644
  - +0.25L: 0.609 (차이 −0.035 [−0.054, −0.016])
  - +0.5L: 0.590 (차이 −0.054 [−0.079, −0.030])
  - 학습값을 더하면 **나빠집니다.**
- **라벨과 독립된 정답으로도 확인했습니다**: FAERS 불균형 신호를 정답으로 두고 41개 질환 × 12개 ADC를 평가했습니다.
  - 자기 장기만: 0.715
  - +0.25L: 0.689 (차이 -0.025 [-0.046, -0.004])
  - +0.5L: 0.681 (차이 -0.034 [-0.061, -0.008])
  - 결론은 같습니다: 학습값을 더하면 나빠집니다.
- 그래서 기본값을 `LEARNED_FRACTION = 0`으로 바꿨습니다. `--learned F`로만 켤 수 있고, 메뉴 기본값도 Off입니다.
- 학습/추론 context 불일치를 고쳤습니다. 추론이 학습 때와 같은 입력(lag one-hot만)을 쓰도록 맞추고 `learned_vulnerability.json`을 다시 생성했습니다(평균 |Δ| 0.005).
  - domain 정보를 넣어 다시 학습하는 것은 모델을 바꾸는 새 실험이라 하지 않았습니다. 하려면 `lab.py` 평가 프로토콜 전체를 다시 돌려야 합니다.
- 레거시 SapBERT 스크립트의 출력 경로를 `learned_vulnerability_sapbert.json`으로 분리했습니다.
- 질환 → 후속질환 예측과 ADC 독성 예측이 다른 문제라는 지적은 `ml/recommend.py` docstring과 README에 적었습니다.

## 단계 5 — 실제 결과로 검증

- **실행함: FAERS 외부 검증**(`ml/validate_faers.py`)
  - 13개 ADC × 13개 장기에서 ADC 계열 안의 보고 오즈비를 구했습니다.
  - 추천기가 쓰는 라벨 경고 수준이 FAERS 신호를 판별한 AUROC는 0.778 [0.727, 0.837]입니다(무작위 섞기 0.499, 발생률 0.651).
  - 단일 장기 환자 순서와 FAERS ROR의 Spearman 평균은 0.574입니다.
  - 보정도(leave-one-ADC-out로 추정한 P(신호 | 경고 수준)): 기울기 1.06, calibration-in-the-large -0.007, Brier 0.143(기저율 0.200).
  - **신장만 일치하지 않았습니다(ρ -0.08).**
- **구현함: 환자 단위 검증 하네스**(`ml/validate_outcomes.py`)
  - 사전 등록 분석을 고정했습니다: 투여한 ADC의 도구 등급 → 결과 AUROC, 라벨만 쓴 기준선과의 paired 차이, 환자/기관 군집 부트스트랩.
  - 합성 코호트 테스트 2개를 통과했습니다.
- **실행함: JADER 환자 단위 검증**(`ml/validate_jader.py`): 원질환이 붙은 증례 12,973건.
  - 취약 환자에서 라벨 순서의 AUROC는 0.649 [0.634, 0.665]입니다.
  - 보정도는 기울기 1.00, Brier 0.076(기저율 0.089)입니다.
  - 취약성이 독성을 증폭한다는 전제는 기각됐습니다(오즈비의 비 0.65 [0.56, 0.74]).
- **못 한 것**: 분모가 있는 환자 코호트에서의 판별력 측정. 저장소에 환자 단위 결과 데이터가 없습니다. 데이터 요건은 `ml/docs/validation_plan.md`에 있습니다.

## 사례 비교 (같은 입력, 이전 구현 → 개정 구현)

**8개 질환 환자**(nafld, ckd_stage_3, ckd_stage_4_5, dialysis, heart_failure, reduced_lvef, prior_anthracycline, coronary_artery_disease):
- 이전: Dato-DXd 0.0, Mirv 0.7 … Brentuximab 100.
- 개정:
  - 투석이 있으므로 Pivekimab(신장 Avoid, 확정)과 Brentuximab(신장 Avoid, 확정)이 맨 뒤로 갑니다.
  - 나머지는 대부분 신장 "Insufficient data"(ESRD 자료 없음)로 같은 등급입니다.
  - NAFLD가 있는데 빌리루빈을 입력하지 않아서, MMAE 계열 등은 "Avoid?"(간)로 표시됩니다.
  - Dato-DXd와 Sacituzumab은 공동 1위입니다. 둘 다 이 환자의 장기에 경고가 없습니다. 대신 Sacituzumab은 다른 장기(혈액, GI)에 boxed가 있다고 표시됩니다.

**예시 환자 2**(hepatitis_b_chronic, dry_eye, glaucoma, keratopathy_history, itp, ckd_stage_3, reduced_lvef, qt_prolongation). 사용자가 언급한 조건으로 구성했으며, 실제 11개 목록과 같은지는 확인하지 못했습니다.
- 이전: Mirvetuximab 0%(1위).
- 개정: Mirvetuximab 13위.
  - 안구 Boxed가 환자의 안구 장기에 걸립니다.
  - "Avoid?"(간, 빌리루빈 > 1.5×ULN)가 표시됩니다.
  - 원문의 안과 검진 요구가 함께 표시됩니다.
  - HBV(ASCO), 혈소판, LVEF, QTc, CLcr, 안과 검진이 체크리스트에 나옵니다.

## 테스트

- `tests/test_ml_recommender.py`: 28개(하네스 합성 코호트 2개 포함), 모두 통과.
- 전체 스위트: **708개 모두 통과**. 이전의 실패 6개는 다음과 같이 해결했습니다.
  - regex_hygiene ×2: 수치 검사가 `docs/`의 추천기 문서를 걸었던 것입니다. ML 문서 관례대로 `ml/docs/`로 옮겼습니다. 이 수치들은 `ml/results/`에서 나옵니다.
  - report_contents ×2: `report/findings.md` 목차 표에 7b 절 행이 빠져 있었습니다. 절의 결론을 요약한 행을 추가했습니다.
  - across_agent_trend: 수렴한 merged-65 적합이 비수렴 32-agent 적합(+0.1308)을 넘어섰습니다(+0.2319/+0.2066). 그래서 플래그가 비어 있는 것이 정상이며, 직접 확인했습니다. 테스트는 '수렴한 적합이 실제로 선두일 때만 빈 플래그를 허용'하도록 고쳤습니다.
  - generated_blocks: `make across-agent-trend`와 `make sync-report`로 artifact와 생성 블록을 맞췄습니다. merged-65 행이 추가되고 사전 등록 예측이 confirmed로 바뀌었습니다.
