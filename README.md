# iCloud 읽기 전용 IMAP MCP 프로토타입

현재 상태: **핵심 및 공식 SDK 프로토콜 테스트 완료 / 실제 iCloud 및 ChatGPT 등록 미검증**.
메일 조회용 작은 검토 가능한 구현입니다. 보안 인증을 받은 제품이나 운영 배포본은 아닙니다.

## 지금 실행할 수 있는 것

오프라인 핵심 데모는 Python 3.14와 표준 라이브러리만 필요합니다.

```powershell
python -m unittest discover -s tests -p test_core.py -v
python demo.py
```

Windows Store 실행 별칭이 작동하지 않으면 설치된 Python 실행 파일의 절대 경로를 사용하세요.
두 명령은 가짜 메일만 사용하며 계정, 환경 변수, 자격 증명을 읽거나 IMAP 서버에 연결하지 않습니다.
핵심 테스트는 34개이며 네트워크 리스너를 시작하지 않습니다.
공식 SDK 통합 테스트 15개를 포함한 전체 검증은 아래 가상 환경에서 실행합니다.
`python verify.py`는 전체 49개 테스트와 소스 문법·제한적 비밀 패턴 검사를 실행하고 `VALIDATION.json`을 갱신합니다.
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
| `tests/test_protocol.py` | 실제 SDK 서버·클라이언트, 포트 없는 ASGI 프로토콜 왕복 |
| `requirements.lock` | Python 3.14 Windows x64 wheel의 정확한 버전과 SHA-256 |
| `DEPENDENCIES.json` | PyPI 출처·wheel 해시·라이선스 메타데이터·게시된 취약점 조회 기록 |
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

## 공식 SDK 설치와 검증

공식 [PyPI mcp 1.30.0](https://pypi.org/project/mcp/1.30.0/)의 프로젝트 URL이
`modelcontextprotocol/python-sdk`를 가리키는지 확인했습니다. v1 유지보수 API
(`mcp.server.lowlevel.Server`, `StreamableHTTPSessionManager`)와 호환되는 버전을 선택했습니다.
확인 당시 최신 주계열은 2.3.0입니다. v1이 최신 주계열이라는 의미는 아니며 운영 전 지원 일정을 재확인해야 합니다.
공식 SDK와 필수 전이 의존성 총 30개를 프로젝트 `.venv`에만 설치했습니다.
PyPI wheel만 허용하고 SHA-256을 고정했으며, 소스 배포 빌드나 별도 post-install 명령은 실행하지 않았습니다.
`pip check`는 통과했습니다. 각 버전의 PyPI 메타데이터에 게시된 취약점은 조회 당시 없었습니다.
이 조회는 독립적인 소스 감사나 모든 취약점이 없다는 보장이 아닙니다.

동일한 Python 3.14 Windows x64 환경에서 재현:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip --isolated install --require-hashes --only-binary=:all: --index-url https://pypi.org/simple -r requirements.lock
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe verify.py
```

잠금 파일은 해당 플랫폼 wheel용입니다. 다른 플랫폼은 의존성 재검토와 별도 잠금이 필요합니다.
`audit_dependencies.py`는 개발용 PyPI 메타데이터 조회 스크립트이며 MCP 도구로 노출되지 않습니다.
`httpx.ASGITransport`를 이용해 포트 없이 MCP initialize, initialized notification, tools/list, tools/call을
검증했고 공식 `ClientSession` 및 `streamable_http_client`로도 왕복을 확인했습니다.
검증하지 않은 메서드·알 수 없는 도구·중복 JSON 키·배치 요청은 경계에서 거부합니다.
SDK 모델로 사전 검증하여 잘못된 요청의 입력값이 SDK 경고 로그에 들어가지 않도록 했습니다.
이 앱 요청 문맥의 SDK 진단 로그도 내용을 제거하며, 테스트로 확인했습니다.

## 남은 실제 연결 단계 (별도 승인 필요)

1. 강한 별도 MCP 인증 비밀을 구성하고 `create_app(token)`으로 fake 앱을 만듭니다.
   테스트용 문자열과 Apple 암호를 MCP bearer 인증에 재사용하면 안 됩니다.
2. 승인 후 ASGI 실행기를 **127.0.0.1:8765**에만 바인딩합니다. 접근 로그·디버그 로그는 끄고,
   프록시 헤더 신뢰도 끕니다. 현재 코드는 자동 실행 명령이나 포트 리스너를 제공하지 않습니다.
3. ChatGPT 연결은 공식 문서에 따라 HTTPS 또는 Secure MCP Tunnel을 별도 승인·구성해야 합니다.
   현재 Guard는 원격 peer, 다른 Host, 모든 Origin을 거부하므로 터널/프록시 설정에 맞는
   인증과 호스트 검증을 다시 설계·테스트해야 합니다. 단순히 0.0.0.0으로 바꾸면 안 됩니다.
4. 계정/워크스페이스 권한 확인, 실제 도구 발견과 fake 호출까지 성공해야 등록 완료로 판단합니다.
5. 그 이후 별도 승인된 실제 계정 시험이 필요합니다. 현재 HTTP 앱은 항상 FakeIMAP만 씁니다.
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
SDK 미설치 문제는 해소했습니다. 남은 미검증 범위는 리스너·실제 전송 경로·클라이언트 등록·실제 iCloud 연결입니다.
