# iCloud 읽기 전용 IMAP MCP 프로토타입

현재 상태: **가짜 데이터 핵심 테스트 완료 / 공식 MCP SDK 연결부 미실행 / 실제 iCloud 및 ChatGPT 등록 미검증**.
메일 조회용 작은 검토 가능한 구현입니다. 보안 인증을 받은 제품이나 운영 배포본은 아닙니다.

## 지금 실행할 수 있는 것

Python 3.14 이상과 표준 라이브러리만 필요합니다. 별도 설치가 없습니다.

```powershell
python -m unittest discover -s tests -v
python demo.py
```

Windows Store 실행 별칭이 작동하지 않으면 설치된 Python 실행 파일의 절대 경로를 사용하세요.
두 명령은 가짜 메일만 사용하며 계정, 환경 변수, 자격 증명을 읽거나 IMAP 서버에 연결하지 않습니다.
테스트는 34개이며 네트워크 리스너를 시작하지 않습니다.
`python verify.py`는 테스트와 소스 문법·제한적 비밀 패턴 검사를 실행하고 `VALIDATION.json`을 갱신합니다.
비밀 검사는 휴리스틱이며 완전한 보안 검토를 대신하지 않습니다.

## 범위와 구조

| 파일 | 역할 |
| --- | --- |
| `core.py` | 입력 검증, 읽기 전용 IMAP, MIME 일반 텍스트 추출, 고정 오류 코드 |
| `fixtures.py` | 합성 메일과 IMAP 명령 기록용 fake |
| `demo.py` | 오프라인 3개 도구 시연 |
| `http_guard.py` | 인증·루프백·Host·Origin·본문 크기 경계 |
| `server.py` | 공식 Python MCP v1 SDK의 Streamable HTTP ASGI 연결부, fake 전용 |
| `tests/test_core.py` | 핵심·프로토콜 명령·HTTP 경계 검증 |
| `THREAT_MODEL.md` | 위협, 통제, 남은 한계 |

도구는 `list_mailboxes`, `search`, `read_message` 세 개뿐입니다.
목록은 구성된 허용 목록만 조회합니다(기본 INBOX, 최대 10개). 임의 폴더 발견 기능은 없습니다.
검색은 최근 1,000개 UID 번호 범위, 결과 최대 50개, ASCII 검색어 1~200자로 제한됩니다.
UID 번호에 빈 구간이 있을 수 있으므로 최근 메시지 1,000건 검색과 같지 않습니다.
읽기는 검색 결과의 `uidvalidity`와 `uid`가 필요하며 오래된 UIDVALIDITY는 거부합니다.
메일 원본은 최대 128 KiB, 반환 본문은 4,000자, 전체 결과는 UTF-8 24,000바이트로 제한됩니다.
큰 메일은 부분적으로 잘못 해석하지 않고 거부합니다. 제목·발신자도 길이를 제한합니다.
첨부 및 HTML은 출력·실행하지 않습니다. HTML 전용 메일은 본문 없음으로 반환합니다.
메일 내용에 포함된 명령이나 링크는 신뢰할 수 없는 데이터입니다.

## 읽기 전용의 의미

`imaplib.select(..., readonly=True)`는 EXAMINE을 전송합니다. 본문은 BODY.PEEK만 사용합니다.
발송, 삭제, 이동, STORE, COPY, EXPUNGE, IMAP CLOSE, 읽음 처리 도구가 없습니다.
종료 시 소켓만 닫습니다. HTTP 서버에 셸이나 임의 URL 도구도 없습니다.

**Apple 앱 전용 암호 자체는 읽기 전용 권한이 아닙니다.** 이 프로그램의 제한을 우회하거나 암호가 유출되면
해당 자격 증명이 허용하는 더 넓은 메일 접근이 가능합니다. 이 구현은 자격 증명 권한을 축소하지 않습니다.
자격 증명 생성·입력·저장은 수행하지 않았습니다. 예시 이름은 `USER_PLACEHOLDER`, `PASSWORD_PLACEHOLDER`뿐입니다.

## SDK 및 HTTP 통합: 아직 완료되지 않은 단계

기존 Python에는 `mcp` SDK가 없었습니다. 새 제3자 의존성을 승인 없이 설치하지 않기 위해 설치하지 않았습니다.
`server.py`는 공식 `mcp` 배포 패키지의 v1 유지보수 API를 대상으로 작성했습니다(`mcp.server.lowlevel.Server`,
`StreamableHTTPSessionManager`). 현재 공식 SDK의 최신 주계열과는 구분해야 합니다.
아직 SDK 설치·import·실제 MCP 초기화·도구 발견·클라이언트 왕복은 검증하지 않았습니다.
임의 자체 JSON-RPC 구현으로 SDK를 대체하지 않았습니다.

통합을 진행하려면 별도 승인을 받고 다음 작업이 필요합니다.

1. 전용 가상 환경에서 공식 SDK와 전이 의존성의 버전·라이선스·취약점을 검토하고 정확한 버전과 해시를 고정합니다.
   v1 유지보수 종료 일정도 재확인하고 필요하면 v2로 연결부를 옮깁니다. 잠금 파일은 설치 검토 후 만듭니다.
2. 메모리 내 ASGI 테스트로 initialize, tools/list, 각 도구 호출, 잘못된 요청, 오류 비노출을 검증합니다.
3. 승인 후에만 강한 별도 MCP 인증 비밀을 구성하고 `create_app(token)`으로 fake 앱을 만듭니다.
   테스트용 문자열과 Apple 암호를 MCP bearer 인증에 재사용하면 안 됩니다.
4. 승인 후 ASGI 실행기를 **127.0.0.1:8765**에만 바인딩합니다. 접근 로그·디버그 로그는 끄고,
   프록시 헤더 신뢰도 끕니다. 현재 코드는 자동 실행 명령이나 포트 리스너를 제공하지 않습니다.
5. ChatGPT 연결은 공식 문서에 따라 HTTPS 또는 Secure MCP Tunnel을 별도 승인·구성해야 합니다.
   현재 Guard는 원격 peer, 다른 Host, 모든 Origin을 거부하므로 터널/프록시 설정에 맞는
   인증과 호스트 검증을 다시 설계·테스트해야 합니다. 단순히 0.0.0.0으로 바꾸면 안 됩니다.
6. 계정/워크스페이스 권한 확인, 실제 도구 발견과 fake 호출까지 성공해야 등록 완료로 판단합니다.
7. 그 이후 별도 승인된 실제 계정 시험이 필요합니다. 현재 HTTP 앱은 항상 FakeIMAP만 씁니다.
   `live_factory`는 고정 `imap.mail.me.com:993`, 시스템 CA TLS 검증, 10초 소켓 timeout을 사용하는
   독립 통합 훅입니다. 호출자가 `approved=True`로 명시하지 않으면 연결 전에 거부합니다.
   이 플래그는 승인 시스템이나 보안 경계가 아니며, 운영 연결에는 별도 비밀 저장·회전·접근 통제가 필요합니다.

현재 이 대화의 dot이 서버를 호출할 수 있다고 보장할 수 없습니다.

## 확인한 공식 자료 (2026-10-16)

- [ChatGPT custom MCP 연결](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt): HTTPS 또는 Secure MCP Tunnel 안내.
- [OpenAI 연결·테스트 안내](https://developers.openai.com/plugins/deploy/connect-chatgpt).
- [MCP transport 사양](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports): Streamable HTTP와 로컬 보안 고려 사항.
- [공식 Python SDK](https://github.com/modelcontextprotocol/python-sdk), [v1 stateless 예제](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/examples/servers/simple-streamablehttp-stateless/mcp_simple_streamablehttp_stateless/server.py).
- [Apple iCloud 서버 설정](https://support.apple.com/en-us/102525): IMAP SSL, 포트 993, 앱 전용 암호.

## 변경·환경 기록

새 전용 폴더에서 작업했으며 상위 경로와 작업 폴더에서 적용할 AGENTS.md는 발견되지 않았습니다.
Node.js 24.19.0, Git 2.55.0, 기존 Python 3.14.6을 확인했습니다.
기존 시스템 설정, 다른 저장소, 인증정보, 라이브 메일은 변경하지 않았습니다.
MCP SDK 미설치가 프로토콜 통합 검증의 정확한 현재 장애물입니다.
