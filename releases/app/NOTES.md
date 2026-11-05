ADCTOX 0.6.11: 입력한 질환은 판정 모델(x2te) 하나만 읽고, 모델 묶음이 1.4 GB에서 305 MB로 준다. Ubuntu, macOS, Windows 모두 0.6.11이다.

- **BioLORD와 SapBERT를 쓰지 않는다.** 질환 목록(registry) 연결도 판정 모델이 고른 MONDO, HPO 개념으로 한다. 같은 입력의 장기, 순위는 0.6.10과 같다(gold dev 전체).
- **판정 모델이 실패하면 예전 linker로 넘어가지 않는다.** 입력은 Not understood로 표시되고 이유가 나온다.
- **장기를 못 찾은 입력에 검증되지 않은 추정값을 붙이지 않는다.** Unmapped 줄에만 나온다.
- 검색창 AI 추천은 판정 모델이 고른 가까운 질환 이름이다. 증상 문장 검색은 글자 단위 비교로 한다.

모델 0.8을 받는다. 앱을 먼저 올린 다음 모델을 올린다.

```bash
adctox --update-app
adctox --update-models
```
