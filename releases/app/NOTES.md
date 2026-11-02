ADCTOX 0.6.7: 브라우저 화면을 영어로 바꾸고 처음 쓰는 사람을 위한 도움말을 넣었다. Ubuntu, macOS, Windows 모두 0.6.7이다.

- **브라우저 화면은 영어다.** 단계는 Conditions, Labs, Organs, Priority, Results다. 한글로 입력해도 읽고, 영어 이름으로 보여 준다. 터미널 화면은 그대로다.
- **도움말이 있다.** 단계마다 처음 열 때 짧은 팁 카드가 뜨고(Got it, Hide all tips), 점선 밑줄 제목에 마우스를 올리면 설명이 뜨며, 위쪽 `?`는 단계, 결과 읽는 법, 키를 한 창에 보인다.
- **Label restriction은 3칸 막대다.** 1칸 Monitor, 2칸 Not studied, 3칸 Avoid이고, 입력하지 않은 값에 따라 올라갈 수 있는 칸은 점선이다. 그 뒤에 원인 장기가 붙는다.
- **Trial results는 막대다.** 사건마다 ADC 막대(serious 부분은 분홍)와 대조군 막대를 한 축척으로 그린다.
- **Key values는 게이지다.** ×ULN은 0~3(1×, 1.5× 눈금), CLcr는 0~120 mL/min(30, 60, 90 눈금)이다.
- 첫 화면은 검색창만 있고, 인체 지도는 Labs부터 나온다.
- **글꼴은 Cafe24 Decobox다** (SIL OFL 1.1). ×, →, ✓ 같은 기호와 한글은 Pretendard로 보인다.
- **밝은 화면 하나, 네 가지 색이다.** 남색 #364F6B(글자), 청록 #3FC1C9(강조, Monitor, 기준 안), 밝은 회색 #F5F5F5(바탕), 분홍 #FC5185(Avoid, boxed warning, 기준을 넘은 수치)이고, Not studied는 남색 글자다. 다크 모드는 없앴다. 왼쪽 위 로고도 없앴다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```
