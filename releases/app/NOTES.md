ADCTOX 0.6.2: ADC 상세에 주요 임상시험 결과가 들어갔다. Ubuntu, macOS, Windows 모두 0.6.2다.

- **Trial results on the patient's organs.** ADC를 고르면 그 ADC의 주요 임상시험(ClinicalTrials.gov에 게시된 결과)에서 환자 장기마다 라벨 경고가 가리키는 이상반응을 `pneumonitis 18/257 (7.0%, vs 0.4%), serious 1/257`처럼 보인다. ADC arm의 환자 수와 비율, 대조군의 비율, serious 수다. 라벨 경고가 없는 장기는 가장 흔한 이상반응과 가장 흔한 serious 이상반응을 보인다. 환자의 암을 입력했으면 그 암의 임상시험을 고른다(HER2+ 유방암이면 DESTINY-Breast02). ADC 15종의 임상시험 32건 중 결과가 게시된 28건이고, ALFA-0701, POLARIX, LUMINOSITY는 `no results posted`로 나온다. ADC 순서는 바뀌지 않는다.
- 검사 수치 화면에서 `Other` 묶음이 없어졌다. Child-Pugh는 Liver, LVEF는 Cardio, UGT1A1은 Genotype 아래에 있다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```
