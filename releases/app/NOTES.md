ADCTOX 0.6.8: 임상시험 결과를 경고 아래 점으로 보이고, SSH 터널로도 브라우저 화면이 열린다. Ubuntu, macOS, Windows 모두 0.6.8이다.

- **임상시험 결과는 해당 경고 바로 아래에 점 20개로 보인다.** 점 하나가 100명 중 5명이고, 분홍 점은 serious다. 옆에 "6 in 100 had pneumonitis, 2 serious"처럼 쓴다. 다른 치료에서도 비슷하게 생긴 사건은 회색이고 "as on other treatment"가 붙는다. 시험 이름과 두 군의 비율은 마우스를 올리면 보인다. 따로 있던 Trial results 칸과 막대는 없앴다.
- **SSH 터널로도 열린다** (`ssh -L 8080:127.0.0.1:<포트>`). 127.0.0.1, localhost, [::1]이면 포트와 상관없이 응답하고, 다른 주소 이름은 그대로 막는다.
- **ADC 상세를 목록으로 정리했다.** 승인 용도는 한 줄에 하나, Payload and linker는 Payload, Action, Linker, Bystander effect, Target 줄로 나눴다.
- **팁과 설명은 한 줄에 한 문장이다.** 세미콜론을 없앴고, 설명이 없던 제목 네 개에 설명을 붙였다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```
