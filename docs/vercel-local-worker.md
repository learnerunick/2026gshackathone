# Vercel 대시보드 + 현재 Mac AI 작업자

현재의 Codex 로그인, 로컬 제작 작업자, Segmind 연결, SQLite, 생성 파일을 그대로 사용한다. Vercel에는 화면과 인증된 중계 API만 배포한다. 새 OpenAI API 키나 클라우드 DB는 필요하지 않다.

```text
브라우저
  → Vercel: 공개 대시보드 / API 게이트웨이
  → HTTPS 터널: 요청 서명 확인
  → Mac: remote_bridge.py (127.0.0.1:8787)
  → 기존 server.py (127.0.0.1:8765)
  → 기존 SQLite · Codex 제작 작업자 · Segmind · 미디어
```

대시보드의 생성 요청은 기존 Mac 서버에 저장된다. 실제 생성은 현재의 `LocalProductionWorker`와 영상 작업자가 수행한다. 브라우저를 닫아도 Mac 서버가 실행 중이면 진행된다. Mac이 꺼지거나 잠들거나 터널이 중단되면 원격 조회·제어·미디어 재생을 할 수 없다. Vercel이 Mac을 대신해 제작하지는 않는다.

## 추가된 구성

| 경로 | 역할 |
| --- | --- |
| `vercel.json`, `package.json` | Node 22 중계 함수, 정적 빌드, API·미디어 라우팅 |
| `api/gateway.mjs`, `deploy/gateway.mjs` | 로그인 없는 접근, Origin·요청 토큰 검증, Mac 요청 서명, 스트리밍 |
| `deploy/routes.json` | Mac과 Vercel이 공유하는 원격 허용 경로 |
| `apps/backend/remote_bridge.py` | 기존 로컬 API에 연결하는 별도 인증 서버 |
| `deploy/vercel/` | 원격 빌드에만 추가하는 연결 표시·분할 업로드 |
| `scripts/build-vercel.mjs` | 대시보드 정적 파일만 `dist/`에 복사 |
| `scripts/setup_remote.py` | 비공개 `.env.remote` 최초 생성 |
| `deploy/cloudflare/config.example.yml` | Mac으로 연결하는 터널 설정 예시 |

## 1. 비공개 설정 생성

저장소 루트에서 실행한다.

```sh
python3 scripts/setup_remote.py
```

`.env.remote`가 권한 `0600`으로 생성된다. 기존 파일이 있으면 덮어쓰지 않는다. 이 파일은 Git과 Vercel 업로드에서 제외된다. 암호를 채팅·스크린샷·Git에 붙이지 않는다.

파일의 두 주소를 실제 배포 주소로 바꾼다. 주소에는 경로나 쿼리를 넣지 않는다.

| 환경변수 | 설정 |
| --- | --- |
| `BOCA_PUBLIC_ORIGIN` | 실제 접속할 고정 주소. 예: `https://boca.example.com` 또는 프로젝트의 `https://…vercel.app` |
| `BOCA_BRIDGE_ORIGIN` | Mac 터널의 고정 HTTPS 주소. 예: `https://boca-worker.example.com` |
| `BOCA_BRIDGE_SECRET` | 자동 생성된 서명 키. Mac과 Vercel에 같은 값 사용 |
| `BOCA_SESSION_SECRET` | 자동 생성된 요청 토큰 서명 키. 기존 환경변수 이름을 유지하며 Vercel에서 사용 |

두 비밀값은 서로 다른 값으로 생성된다. 서버 환경변수이므로 `NEXT_PUBLIC_` 등을 붙여 브라우저에 공개하지 않는다. 실제 값 대신 `.env.example`만 커밋한다.

## 2. Mac 서버와 인증 브리지 실행

현재 서버가 `8765`에서 실행 중이면 그대로 둔다. 실행되어 있지 않을 때만 기존 명령으로 시작한다.

```sh
python3 apps/backend/server.py serve
```

별도 터미널에서 브리지를 실행한다.

```sh
python3 apps/backend/remote_bridge.py --env-file .env.remote
```

기존 서버의 포트가 다르면 `--local-port 8766`처럼 지정한다. 브리지는 `127.0.0.1:8787`에만 바인딩하며 자체적으로 AI를 실행하거나 운영 DB의 실행 상태를 바꾸지 않는다. 요청 기록은 `.runtime/remote-bridge/requests.sqlite3`에 별도로 저장한다.

Mac의 기존 Codex CLI 로그인·도구·권한과 영상 생성 설정이 계속 유효해야 한다. 제작 중에는 Mac 절전과 프로세스 종료를 피한다. 작업자 세부 동작은 [로컬 자동 제작 작업자](local-production-worker.md)를 따른다.

## 3. HTTPS 터널 연결

Cloudflare 계정·관리 중인 도메인과 `cloudflared` 설치가 필요한 구성이다. 터널 설치·외부 노출은 이 코드 추가만으로 실행되지 않는다.

로컬 관리 터널을 사용할 경우, 계정 인증과 터널 생성 후 예시 설정을 `.runtime/remote-bridge/tunnel.yml`에 복사한다.

```sh
cloudflared tunnel login
cloudflared tunnel create boca-worker
cp deploy/cloudflare/config.example.yml .runtime/remote-bridge/tunnel.yml
```

설정 파일의 터널 UUID, 자격 증명 파일의 절대 경로, `hostname`을 실제 값으로 바꾼다. `hostname`은 `BOCA_BRIDGE_ORIGIN`의 호스트와 같아야 한다. 그 후 실제 호스트 이름을 넣어 연결한다.

```sh
cloudflared tunnel route dns boca-worker boca-worker.example.com
cloudflared tunnel --config .runtime/remote-bridge/tunnel.yml run boca-worker
```

터널의 서비스 주소는 반드시 `http://127.0.0.1:8787`을 사용한다. 기존 로컬 UI 포트 `8765`에는 원격 요청 서명 검증이 없으므로 터널을 직접 연결하지 않는다. 이 브리지는 서명 없는 요청을 거부한다. Cloudflare Access를 별도로 켠 경우 이 구현에는 Access 서비스 토큰 전달 기능이 없으므로 해당 인증 설정도 함께 맞춰야 한다.

공식 설정 문서: [Cloudflare Tunnel 구성](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/).

### 도메인 없이 시연할 때

해커톤 시연에는 Quick Tunnel을 사용할 수 있다. 인증 브리지 `8787`에만 연결하며, 생성된 HTTPS 주소를 `BOCA_BRIDGE_ORIGIN`에 넣는다.

```sh
.runtime/bin/cloudflared tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:8787
```

Quick Tunnel 주소는 프로세스를 다시 시작하면 바뀔 수 있다. 새 주소를 Mac의 `.env.remote`와 Vercel Production 환경변수에 함께 반영하고 다시 배포해야 한다. 프로세스가 종료되면 원격 연결도 끊긴다. 고정 주소로 계속 운영할 때는 위의 관리형 터널 구성을 사용한다. [공식 Quick Tunnel 안내](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)는 이 방식을 개발·테스트용으로 한정한다.

## 4. Git → Vercel 연결

Vercel에서 이 Git 저장소를 가져오고 다음처럼 설정한다.

| 항목 | 값 |
| --- | --- |
| Root Directory | 저장소 루트 (`.`) |
| Framework Preset | Other |
| Node.js Version | 22.x |
| Build Command | `npm run build` |
| Output Directory | `dist` |

빌드·함수 설정은 `vercel.json`에 포함되어 있다. `.env.remote`의 환경변수 네 개를 Vercel 프로젝트의 **Production 환경변수**에 등록하고 배포한다. 주소를 바꾸거나 환경변수를 변경한 경우 다시 배포한다. `BOCA_PUBLIC_ORIGIN`과 다른 별칭·Preview URL에서는 변경 요청이 차단된다. 운영 환경변수는 Preview에 복사하지 않는다. 별도 Preview가 필요하면 별도 Mac 테스트 데이터와 주소·키를 사용한다.

주소를 열면 암호 입력 없이 대시보드가 바로 표시된다. 기존 `/login.html` 북마크도 원래 목적지로 이동한다. 현재 Mac에 있는 콘텐츠와 실행 상태가 표시되어야 한다. 첫 확인은 데이터 조회와 영상 재생으로 한다. 시작·재개 버튼은 실제 Mac 제작 작업자를 깨우므로 생성할 의도가 있을 때 사용한다.

Git에는 코드·문서·설정 예시만 올린다. `.runtime/`, `output/`, `.env.remote`, Codex 인증정보, Segmind 키, 터널 자격 증명은 제외한다. `dist/`도 생성 결과이므로 Git에 올릴 필요가 없다. 기존 콘텐츠는 Git으로 업로드되지 않고 인증된 연결을 통해 Mac에서 제공된다.

플랫폼 설정 참고: [Vercel Node.js 함수](https://vercel.com/docs/functions/runtimes/node-js), [vercel.json](https://vercel.com/docs/project-configuration/vercel-json).

## 동작과 제약

- **생성·비용 정책:** 요청이 기존 서버에 전달되므로 현재 제작 목표, 한도, 품질 검수 설정, 사람의 버전 승인, Segmind 예산 규칙을 그대로 따른다. 별도 AI API 과금 방식으로 전환하지 않는다. Vercel·터널의 사용료와 트래픽은 사용하는 호스팅 요금제에 따른다.
- **저장:** SQLite와 이미지·영상은 계속 Mac에 저장된다. Vercel에 별도 복제본을 만들지 않는다. 원격과 로컬 화면에서 같은 내용을 수정한다. 백업할 때 기존 운영 데이터와 `.runtime/remote-bridge/`의 요청 기록도 함께 보존한다.
- **접속:** 해커톤 MVP는 로그인 없이 공개되며 링크에 접근한 사용자가 대시보드의 조회·수정·제작 제어 기능을 이용한다. 로그인 쿠키와 접속 암호는 사용하지 않는다. 같은 출처의 JSON 변경 요청과 요청 토큰은 계속 검증하고, Mac 중계 인증과 허용 경로도 유지한다. 브리지 키를 바꾸면 Mac과 Vercel을 함께 갱신한다.
- **허용 범위:** 기존 화면의 조회, 제작 요청·제어, 문안 수정·검수, 영상 업로드·제작을 지원한다. CLI용 작업자 API, 콘텐츠 파일 import, 게시 API, Mac 파일 경로를 받는 페르소나 참고 사진 등록은 외부에 열지 않는다. 참고 사진의 최초 등록은 기존 Mac 작업 흐름을 사용한다.
- **큰 파일:** 영상·ZIP은 스트리밍하며 영상의 `Range` 요청을 전달한다. 영상 참고 이미지는 기존 10MB 제한을 유지하고 작은 요청으로 나누어 업로드한다. 생성 자체는 Mac에서 비동기로 진행되며, 단일 파일 전송은 게이트웨이의 270초 시간 제한 안에 끝나야 한다. 느린 연결에서 대용량 다운로드는 중단될 수 있다.
- **불확실한 응답:** POST 요청을 자동 재전송하지 않는다. 같은 요청 ID와 본문을 다시 받으면 저장된 결과를 반환한다. 서버가 처리했는지 확인할 수 없는 요청은 확인 필요 상태로 보존한다. 새 요청 ID로 다시 누르는 동작까지 같은 요청으로 간주하지 않으므로, 연결 오류 후에는 제작 기록을 먼저 확인한다.
- **중단 표시:** Mac 서버·터널에 연결되지 않으면 연결 오류를 표시한다. 연결 상태는 Mac API 도달 여부이며 Codex의 로그인·사용 한도까지 보장하지 않는다.
- **상태 전송:** 원격 `/api/state`의 `jobs`는 상태 요약만 제공하고 화면에서 사용하지 않는 작업 `input`·`result`는 제외한다. 원본은 Mac에 그대로 저장되며 제작 단계·아티팩트 API에서 상세 기록을 조회한다. 브리지와 Vercel은 JSON을 gzip으로 전송하고, 원격 화면의 조회 대기 시간은 30초다. 제작 이력이 누적되어도 반복 입력 때문에 첫 화면이 시간 초과되지 않도록 한다.

## 로컬 검증

Node 22, Python 3.9 이상에서 다음을 실행한다. 통합 테스트는 임시 DB와 동적 포트를 사용하며 Codex·Segmind 작업자를 시작하지 않는다.

```sh
npm ci
npm run build
npm run test:remote
python3 -m unittest discover -s tests -p 'test_remote_bridge.py' -v
```

로컬 화면 검증용 `npm run dev:remote`도 제공한다. 서버 환경에 네 환경변수와 `BOCA_ALLOW_LOCAL_DEVELOPMENT=1`을 넣으면 loopback HTTP 주소만 허용한다. 기본 화면 포트는 `8788`이다. 이 스크립트는 기존 Mac 서버나 브리지를 자동 시작하지 않는다. Vercel에서는 개발 예외를 사용할 수 없다.

실제 Vercel 배포와 HTTPS 터널 연결은 별도 단계다. 로컬 테스트 통과가 실제 계정·도메인·네트워크 연결까지 확인했다는 뜻은 아니다.
