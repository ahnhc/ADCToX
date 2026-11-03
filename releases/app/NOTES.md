ADCTOX 0.6.10: 웹 화면 글꼴이 Anthropic Sans Text Light로 바뀌어 작은 글자가 덜 뭉친다. Ubuntu, macOS, Windows 모두 0.6.10이다.

- **글꼴은 Anthropic Sans Text Light다.** Cafe24 Decobox를 뺐다. 한글과 ✓는 그대로 Pretendard다.
- **`ADCTOX_PORT`로 웹 포트를 고정한다.** 서버에서 `ADCTOX_NO_BROWSER=1 ADCTOX_PORT=8765 adctox-web`, 내 컴퓨터에서 `ssh -L 8765:127.0.0.1:8765 <사용자>@<서버>` 다음 http://localhost:8765 를 연다. 잘못된 값이나 이미 쓰는 포트는 한 줄로 알려 주고 끝난다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```
