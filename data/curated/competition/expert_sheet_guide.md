# 전문가 검증 시트 작성법 (`expert_sheet.csv`)

각 줄은 질환 하나와, AI가 그 질환이 손상시킨다고 판정한 장기 목록이다. 판정한 모델은 두 개이고, 어느 모델의 답인지는 적지 않았다. 같은 질환이 두 줄 나오면 두 모델의 답이 다른 경우다.

| 칸 | 쓰는 법 |
|---|---|
| `organs_given` | AI가 고른 장기. 고치지 않는다 |
| `wrong_organs` | `organs_given` 중 이 질환과 관계없는 장기. 여러 개면 `;`로 구분 |
| `missing_organs` | 이 질환이 흔히 손상시키는데 빠진 장기. 아래 13개 이름 중에서 쓴다 |
| `comment` | 자유 의견 (선택) |

판단 기준: 그 질환이 진단된 환자에서 **그 장기의 기능이나 구조가 손상되어 있다고 보는가**. 드문 합병증은 빠져도 틀린 것으로 보지 않는다.

장기 이름 13개: haematologic, hepatic, cardiovascular, pulmonary, renal, gastrointestinal, neurologic, ocular, dermatologic, metabolic_endocrine, musculoskeletal, infectious_immune, otologic

`infectious_immune`는 감염 또는 면역 이상이다(자가면역 포함).

마감: 11-06. 다 채운 파일을 형찬에게 주면 `python ml/expert_sheet.py score <파일>`로 모델별 정밀도·재현율을 계산한다.
