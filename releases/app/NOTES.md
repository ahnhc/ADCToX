ADCTOX 0.6.3: 다섯 화면을 브라우저에서도 쓸 수 있다. Ubuntu, macOS, Windows 모두 0.6.3이다.

- **adctox-web (= adctox --web).** 같은 다섯 단계(질환 → 검사 수치 → AI 장기 분석 → 우선순위 → 결과)가 기본 브라우저에서 열린다. 이 컴퓨터 안에서만 돌고(127.0.0.1), 서버에는 아무것도 남지 않는다. 화면 옆의 인체 지도가 AI 장기 분석부터 환자의 장기를 밝히고, 고른 ADC의 boxed warning은 빨간 고리, warning은 주황 고리로 보여 준다. ADC 상세는 오른쪽 서랍으로 열린다. 키는 터미널과 같다(PgUp / PgDn, ↑↓, Enter, Esc). 클릭도 된다.
- 터미널 화면은 그대로 기본이다. `adctox`는 전과 같다. `adctox-web` 명령은 설치 스크립트가 만들고, `adctox --update-app`으로 올린 경우에는 다음 실행 때 생긴다. Windows zip에는 ADCTOX-web.bat가 있다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```
