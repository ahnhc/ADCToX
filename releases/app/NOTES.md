ADCTOX 0.6.12: `adctox`는 브라우저 화면을 열고, 터미널 화면은 `adctox-cli`로 연다. Ubuntu, macOS, Windows 모두 0.6.12다.

- **`adctox`는 브라우저에서 시작한다.** `adctox-web`, `adctox --web`도 그대로 쓸 수 있다.
- **`adctox-cli`(`adctox --cli`)는 같은 다섯 화면을 터미널에서 연다.** `adctox --plain`은 그대로 터미널에서 질문에 답하는 방식이다.
- Windows: `ADCTOX.bat`와 바로가기는 브라우저를 연다. 터미널은 `ADCTOX-cli.bat` 또는 `adctox-cli` 명령으로 연다(Windows Terminal이 있으면 그 창).
- 분석과 모델은 0.6.11과 같다(모델 0.8).

이미 설치했다면 앱만 올린다. `adctox-cli`는 올린 뒤 처음 실행할 때 `adctox` 옆에 생긴다.

```bash
adctox --update-app
```
