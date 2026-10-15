ADCTOX 0.3.5: abbreviations and several names on one line.

- **한 줄에 여러 질환:** `asd adhd`처럼 띄어 써서 넣으면 `각각 따로 추가`가 나온다. 전에는 한 질환으로 읽었다.
- **약어 추천:** 약어가 뜻할 수 있는 질환을 모두 추천한다.
  - `asd`: 심방중격결손, 자폐 스펙트럼 장애 등
  - `adhd`도 이제 추천이 나온다.
- **장기 없음 표시:** 13개 장기에 속하지 않는 질환(정신, 발달, 생식 등)은 `Unmapped` 대신 `None of the 13 organs`로 표시한다.

업데이트: `adctox --update-app`
