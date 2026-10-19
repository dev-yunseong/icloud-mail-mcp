# iCloud 읽기 전용 IMAP MCP 프로토타입

iCloud 메일의 폴더 조회·검색·본문 읽기를 위한 읽기 전용 MCP 프로토타입입니다.
**현재 HTTP 앱은 가짜 메일만 사용하며, 실제 iCloud 연결과 ChatGPT 등록은 미검증입니다.**

## 기능과 제한

| 도구 | 기능 |
| --- | --- |
| `list_mailboxes` | 구성된 허용 목록의 폴더 조회(기본 `INBOX`, 최대 10개) |
| `search` | ASCII 검색어 1~200자로 검색, UID와 `uidvalidity` 반환(최대 50건) |
| `read_message` | 검색 결과의 `uid`와 `uidvalidity`로 일반 텍스트 본문 읽기 |

- 검색 범위는 최근 1,000개 **UID 번호**이며, 메시지 1,000건을 뜻하지 않습니다.
- 메일 원본은 최대 128 KiB, 반환 본문은 4,000자, 전체 결과는 UTF-8 24,000바이트로 제한됩니다. 큰 메일은 거부합니다.
- 첨부 파일과 HTML은 반환·실행하지 않습니다. HTML 전용 메일은 본문 없음으로 반환합니다.
- 발송·삭제·이동·읽음 처리 도구는 없습니다. IMAP 조회는 `EXAMINE`과 `BODY.PEEK`를 사용합니다.

## 빠른 시작

Python 3.14에서 저장소를 내려받고 오프라인 데모를 실행합니다. 데모와 핵심 테스트는 표준 라이브러리만 사용하며, 자격 증명을 읽거나 네트워크에 연결하지 않습니다.

```powershell
git clone https://github.com/dev-yunseong/icloud-mail-mcp.git
cd icloud-mail-mcp
python demo.py
python -m unittest discover -s tests -p test_core.py -v
```

데모는 가짜 메일로 세 도구를 차례로 호출하고 JSON 결과를 출력합니다. 직접 호출하는 예시는 [demo.py](demo.py)를 참고하세요.

## MCP SDK 설치·검증

잠금 파일은 **Python 3.14 / Windows x64**용이며 MCP v1 SDK `1.30.0`을 사용합니다. 다른 플랫폼에는 별도 의존성 검토와 잠금 파일이 필요합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip --isolated install --require-hashes --only-binary=:all: --index-url https://pypi.org/simple -r requirements.lock
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe verify.py
```

`verify.py`는 핵심·SDK 통합 테스트와 문법·제한적 비밀 패턴 검사를 실행하고 `VALIDATION.json`을 갱신합니다. SDK 테스트는 포트 없이 메모리 내 ASGI 통신으로 수행합니다.

## 실제 연결과 보안

- `server.create_app(token)`은 `/mcp`의 Streamable HTTP 앱을 만들지만, 항상 `FakeIMAP`을 사용합니다. 자동 시작 명령이나 네트워크 리스너는 제공하지 않습니다.
- HTTP 접근에는 별도의 강한 bearer 토큰이 필요합니다. 현재 가드는 루프백 peer와 `Host: 127.0.0.1:8765`만 허용하고 모든 `Origin`을 거부합니다. 원격·터널 연결은 인증과 호스트 검증을 별도로 설계·검증해야 합니다.
- `core.live_factory`는 HTTP 앱과 분리된 실제 IMAP 연결 훅입니다. `approved=True`는 보안 경계가 아니며, 실제 연결에는 별도 검토·승인과 비밀 관리가 필요합니다.
- **Apple 앱 전용 암호 자체는 읽기 전용 권한이 아닙니다.** MCP 토큰으로 재사용하거나 저장소에 기록하지 마세요.
- 메일에 포함된 명령·링크는 신뢰할 수 없는 데이터입니다. 이 프로토타입은 보안 인증 제품이나 운영 배포본이 아닙니다.

자세한 한계는 [위협 모델](THREAT_MODEL.md), 의존성 기록은 [DEPENDENCIES.json](DEPENDENCIES.json)을 참고하세요.
