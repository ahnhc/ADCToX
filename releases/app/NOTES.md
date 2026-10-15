ADCTOX 0.3.6: 질환명 추천 정리.

- **유전 아형 정리:** `Alzheimer disease 2~8`, `Parkinson disease 12`처럼 번호가 붙은 유전 아형이 추천 목록을 채우지 않는다.
  - 일반 질환이 이미 보이면 숨긴다.
  - 숫자를 입력하면(`alzheimer disease 2`) 다시 나온다.
- **동물 질환 제외:** `..., domestic cat`, `..., koala` 같은 동물 질환은 추천에서 뺀다.
- **0.3.5 포함:**
  - `asd adhd`처럼 띄어 쓴 여러 질환을 각각 추가할 수 있다.
  - 약어 추천이 나온다.

업데이트: `adctox --update-app`
