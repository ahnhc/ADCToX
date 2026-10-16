# 이전 문서 (archive)

이 폴더의 문서는 이전 단계의 기록이다. 기록용으로 남겨 두며, 현재 앱과 모델을 설명하지 않는다.
현재 모델 문서는 [ml/docs/gemma_judge.md](../../ml/docs/gemma_judge.md), ml 폴더 안내는 [ml/README.md](../../ml/README.md)다.

## 연구와 모델

`ml/docs/`에 있던 이전 연구 문서는 [ml/docs/archive/](../../ml/docs/archive/README.md)에 있다.

| 문서 | 내용 | 대체한 문서 |
|---|---|---|
| [LEGACY_RESEARCH_OVERVIEW.md](LEGACY_RESEARCH_OVERVIEW.md) | `src/adctox` forward organ-toxicity model과 ADC 설계 열거기의 개요 | `ml/` 추천기, [gemma_judge.md](../../ml/docs/gemma_judge.md) |

## 팀 작업 (team/)

| 문서 | 내용 | 대체한 문서 |
|---|---|---|
| [team/TEAM_GUIDE.md](team/TEAM_GUIDE.md) | 팀원용 엑셀 작업 안내(2026-10) | 없음. 작업 종료 |
| [team/TEAM_HANDOFF.md](team/TEAM_HANDOFF.md) | 받은 자료 반영 절차(관리자용, 모델 0.2 기준) | 없음. 작업 종료 |
| [team/TEAMMATE_DATA_USE.md](team/TEAMMATE_DATA_USE.md) | 팀원 워크북(ADC DB, FinnGen 매핑)을 어떻게 썼는지 | 없음. 기록용 |

## 옮기지 않은 이전 문서

`docs/MODEL_CARD.md`와 `report/findings.md`도 `src/adctox` forward model의 기록이다.
테스트, `scripts/check_report.py`, `scripts/sync_report_numbers.py`, API가 이 경로를 읽으므로 그 자리에 둔다.
