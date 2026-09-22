# 로컬 검토 API

Python 표준 라이브러리와 SQLite를 사용한다. Codex heartbeat 작업자가 기획·스토리보드·문안·이미지·품질 검수·등록을 반복한다. 자동 영상은 이 제작 단계에 연결된 비동기 Segmind 작업자가 처리하며 수동 영상 화면도 유지한다. 서버 단독 LLM 실행이나 Instagram 직접 게시 전송은 포함하지 않는다. 영상 계약은 [Segmind 연동](segmind-video.md)을 따른다.

실행: python3 apps/backend/server.py serve

화면: http://127.0.0.1:8765

GET /api/state 는 현재 콘텐츠, 생성 작업, 페르소나, 일정, 로컬 변경 요청용 token을 반환한다. token은 로컬 동일 출처 UI에서 사용하며 외부로 보내지 않는다. 변경 요청은 X-BOCA-Token 헤더가 필요하다. 별도 프론트엔드 개발 시 동일 출처 프록시를 사용한다.

`automation.specialists.cycle`은 최신 콘텐츠 순환의 ID·번호·상태·단계 번호·갱신 시각을, `stage_jobs`는 그 순환의 단계 상태·시도 횟수·갱신 시각을 반환한다. 작업 소유권 토큰은 포함하지 않는다. 전문가 팀 상태는 이 데이터와 실제 배정 기록으로 표시하므로 별도의 산출물 파일 조회에 의존하지 않는다.

| 경로 | 동작 |
| --- | --- |
| GET /api/health | 로컬 서버 및 게시 계정 확인 상태 |
| GET /api/state | 콘텐츠·버전·작업 상태 |
| GET /api/video-library | 현재 실행과 무관한 전체 영상 제작 이력과 재생 가능한 로컬 미디어 URL |
| GET /api/video/jobs/:id/media | 저장된 해당 영상 작업의 실제 결과 파일. MP4 Range 재생 지원 |
| GET /api/video-library/imported/:content/:version/:card/media | 특정 콘텐츠 버전의 영상 카드. MP4 Range 재생 지원 |
| POST /api/generation-requests | brief를 받아 예약 작업 큐에 저장. 즉시 외부 모델을 호출하지 않음 |
| POST /api/contents/import | content와 expected_version으로 생성 결과 등록 |
| POST /api/contents/:id/edit | base_version과 title/caption/hashtags로 수정. 승인 무효화 |
| POST /api/contents/:id/approve | version에 대해 사람의 승인 저장 및 게시 대기열 생성 |
| POST /api/contents/:id/reject | version 반려 |
| POST /api/publishing/claim | 검증된 account와 현재 승인 버전으로 한 번만 게시 작업 획득 |
| POST /api/publishing/result | claim_id, status, permalink, detail로 실제 게시 결과 기록 |

파일과 데이터베이스는 .runtime/ 아래에 저장되며 Git에서 제외한다. 가져온 미디어는 해시 이름으로 복사해 원본 파일의 후속 변경과 분리한다. 승인·게시 직전에 미디어 해시와 상품 정보 유효기간을 재검사한다. 게시 직전 검증에 실패한 항목은 publication.status=blocked, content.status=ready로 돌아가며 사유를 detail과 publication.blocked 이벤트에 남긴다. 다른 정상 승인 콘텐츠의 게시 소유권 획득은 계속 가능하다. 원래 승인 기록은 이력으로 보존하지만 자동 재승인·재게시하지 않는다.

영상 라이브러리는 `{items, total, updated_at}`을 반환한다. 최근 50개 영상 작업으로 제한된 `/api/video`와 달리 전체 작업 이력을 제공하고, 영상 작업에 연결되지 않은 콘텐츠 영상도 합친다. 각 항목은 실제 제작 `status`, `media_available`, `media_url`, 등록 콘텐츠 ID·버전, 문안·스토리보드와 실패 사유를 포함한다. 자동 제작이 끝났지만 피드 등록 전인 MP4도 로컬 결과 파일이 있으면 재생할 수 있다. 조회는 공급자 API 호출·새 생성·승인·게시를 실행하지 않는다.

`media_sha256`은 재생 가능한 로컬 파일의 해시다. 프런트엔드는 ID와 해시가 같은 동안 video 요소를 유지하므로 문안 버전·제작 상태가 바뀌어도 재생을 다시 시작하지 않는다. 해시 조회는 파일의 inode·크기·수정 시각 등을 기준으로 캐시하며 실제 영상 제공 시 무결성을 다시 확인한다.

새 AI 결과는 낡은 버전을 기반으로 했거나 승인된 콘텐츠를 대상으로 하면 별도 제안으로 보존된다. 제안 적용 UI는 아직 없다. 현재 UI는 제목·문안·해시태그를 수정하며 이미지 순서 편집과 OAuth 연결 UI는 후속 작업이다.

테스트: python3 -m unittest discover -s tests -v

## 연속 생성 제어

새 영상 요청은 보이스·자막 delivery v1을 동결한다. `/api/video/jobs`의 선택 입력 `voice_script` 또는 `video_narration: [{start,end,text}]`를 사용하고 없으면 문안에서 호환 대본을 만든다. 자동 worker-video는 copy의 대본을 우선한다. 자막 합성 후 `result.delivery`와 완성 media_path를 저장하고 raw_media_path에 원본을 보존한다. quality의 `video_checks` 세 항목은 실제 재생·청취 확인 후 모두 true여야 한다. 상세 계약은 [영상 자막·보이스](video-delivery.md)를 참고한다.

시작·재개·기획안 제작 API는 커밋 후 로컬 제작 작업자를 즉시 깨운다. `automation.worker_runtime`은 실제 총괄의 online/status/message/run_id를 제공하며 단계 소유권 기반 `worker_status`와 구별한다. 로컬 총괄이 활성 상태이면 다른 예약 작업자의 `worker-next`는 `should_work:false, reason:managed_locally`를 반환한다. 기존 유효한 단계의 완료·체크포인트는 유지한다. 진단 원문·인증·lease는 공개 runtime 상태에 포함하지 않는다.

GET /api/state의 automation에는 최신 run, stages, logs(최근 100개), sources, worker_status, worker_last_seen_at이 들어간다. run의 completed_count는 해당 실행에서 피드 등록을 끝낸 콘텐츠 수다. `run.settings.stop_after_posts`가 양의 정수이면 목표 도달 즉시 status=completed가 되며, null이면 개수 제한이 없다. UI는 5초마다 상태를 갱신한다.

| 경로 | 입력과 동작 |
| --- | --- |
| POST /api/runs/start | persona_id, start_at, end_at(시간대 포함 ISO), media_mode(images/mixed/video_only; 기존 video 지원), stop_after_posts(null 또는 1~1000 정수). 활성 실행이 있으면 동일 실행을 반환해 중복 시작 방지. 고정된 미디어 형식이나 목표 개수를 명시적으로 변경하면 409 |
| POST /api/runs/:id/pause | 새 단계·외부 호출 시작 중지. 반환 중인 결과는 보존 |
| POST /api/runs/:id/resume | 일시정지/확인 필요 실행을 재개. uncertain 작업은 먼저 확인 필요 |
| POST /api/runs/:id/stop | 해당 실행 중지. 생성 파일·로그는 유지 |
| GET /api/logs | run_id(선택), after_id(기본 0), limit(기본 100, 최대 500). 오름차순 로그와 전역 소재 이벤트 조회 |
| GET /api/runs/:id/artifacts | 실제 파일 목록, event_count, last_event_id, 단계별 상태·시도·요약·다운로드 URL |
| GET /api/runs/:id/logs?format=log | 해당 실행의 가독 로그 다운로드. format=jsonl로 이벤트 JSONL 다운로드 |
| GET /api/runs/:id/stages/:cycle/:stage | 해당 단계의 input/result/checkpoints/attempts/external_job_ids/summary/events 및 previews |
| GET /api/runs/:id/stages/:cycle/:stage/media/:index | 해당 단계에 실제 저장된 이미지·영상 미리보기. MP4는 HTTP Range 지원 |
| POST /api/sources | affiliate, title, url, verified_at, expires_at, claims, visibility. 출처 URL 기준 갱신 |
| POST /api/worker/next | worker_id. should_work와 소유권 토큰, 단계, 기존 결과 반환 |
| POST /api/worker/inspect | cycle_id(선택). 복구용 run, cycle, jobs 조회. 소유권 정보가 있어 인증된 POST만 허용 |
| POST /api/worker/ping | cycle_id, lease_token, external_job_id(선택). 소유권 연장·실행 지속 가능 여부 |
| POST /api/worker/video | cycle_id, lease_token. images 단계에서 AI 기획·스토리보드·문안을 Segmind에 연결. 조건 미충족: mixed/기존 video는 skipped/fallback:images, video_only는 blocked/fallback:null과 실행 확인 대기 |
| POST /api/worker/checkpoint | cycle_id, lease_token, result. release:true는 external_idle:true 확인 필요 |
| POST /api/worker/log | cycle_id, lease_token, event, message, detail(선택), level |
| POST /api/worker/complete | cycle_id, lease_token, result, external_job_id(선택). 검증 후 다음 단계로 이동 |
| POST /api/worker/fail | cycle_id, lease_token, error, retryable(기본 true), uncertain(기본 false) |
| POST /api/worker/repair | cycle_id, lease_token, target_stage, issues. 검수 단계에서 필요한 부분부터 제한적 재생성 |

HTTP 변경·작업자 요청에는 모두 X-BOCA-Token이 필요하다. worker 소유권 토큰은 공개 로그에 넣지 않는다. 자동 생성에 속한 jobs는 일반 job-update로 변경하지 못한다.

media_mode는 새 실행의 settings에 고정된다. 생략 시 config 값 또는 images를 사용하며 현재 대시보드 기본 선택은 mixed다. mixed는 이야기에 따라 이미지 또는 영상을 선택한다. video_only는 영상만 만들며 planning.content_format=video와 MP4 미디어를 요구한다. 조건 미충족은 이미지 대체 없이 확인 대기하며 조건 해결 후 사용자가 재개한다. 기존 중지 실행은 서버 시작으로 재개되지 않으며 사용자 시작 요청이 필요하다.

`POST /api/settings`의 `generation.auto_video: {duration: 20, resolution: "480p"}`는 자동 영상 기본값을 저장한다. 길이는 정수 20~30, 해상도는 480p/720p만 허용하며 예산 변경은 지원하지 않는다. `GET /api/state`의 `studio.settings.generation.auto_video`에서 저장값을 확인한다. 저장 자체로 제작을 시작하지 않는다.

`POST /api/runs/start`에 `video: {duration: 25, resolution: "720p"}`를 선택적으로 보낼 수 있다. 생략하면 저장된 자동 영상 기본값(최초 20초·480p)을 사용한다. 새 실행의 `settings.video`에 고정하며 기존 활성 실행에 다른 값을 명시하면 409다. 실행 중 기본값 저장은 다음 실행에만 적용된다. 단계 입력의 `video_settings`는 기획부터 생성까지 같은 값이고 images 전용 실행에는 null이다. `/api/worker/video`는 실행에 고정된 값을 실제 생성 요청에 사용한다.

worker-video는 CLI `python3 apps/backend/server.py worker-video CYCLE TOKEN`과 같다. 기존 Segmind의 한 편 예상 $8·UTC 하루 예상 $15·동시 대기/진행/확인 필요 2건 한도를 공유한다. API 키·기준 이미지·한도 조건이 맞지 않으면 이미지 제작을 계속한다. 접수된 영상은 비동기 작업자가 완료 파일을 저장하고 images 단계까지만 완료한다. quality와 register는 Codex 작업자가 이어서 처리하며 자동 영상 완료가 곧 콘텐츠 등록·사람 승인·SNS 게시를 뜻하지 않는다.

각 단계 결과에 decision_summary로 공개 선택 근거 요약을 남긴다. 커밋된 이벤트와 작업 결과는 `.runtime/production/<run_id>/events.log`, `events.jsonl`, `cycles/<cycle_id>/<stage>.json`으로 동기화한다. 원자적 파일 교체 방식이므로 실시간 확인은 tail -F를 사용한다. 롤백된 이벤트를 내보내지 않고 재시작·조회에서 누락 파일을 재구성한다. 키·인증 토큰·내부 사고 과정은 파일과 다운로드에서 제외한다. 이 파일 API는 읽기·다운로드이며 제작을 시작하지 않는다.

단계 조회의 `previews`는 `{kind, url, name, alt, available, origin}` 목록이다. 결과·체크포인트에 기록된 실제 로컬 미디어와 register에 기록된 정확한 콘텐츠 버전의 미디어만 제공한다. 기록된 미디어 파일이 없으면 `available:false`, `url:null`로 표시하며 허용되지 않은 경로는 제외한다. 클라이언트가 임의의 파일 경로를 지정할 수 없고 프로젝트 밖 파일·심볼릭 링크 이탈을 허용하지 않는다. 단계 상세 화면은 읽기 쉬운 결과와 미디어를 먼저 보여주고 입력·원본 JSON은 접어서 제공한다.

register 조회의 `registered_content`는 `{id, version, payload}` 또는 `null`이다. 문안·해시태그도 해당 등록 버전의 실제 payload에서 가져오므로 이전 copy 단계나 이후 수정된 현재 콘텐츠와 혼동하지 않는다. `source_snapshot`은 해당 단계 완료 이벤트에 저장된 당시 소재 목록 또는 `null`이며 현재 소재 목록으로 대체하지 않는다.

실행 상태는 scheduled/running/paused/blocked/stopped/completed다. 단계는 sources/planning/storyboard/copy/images/quality/register다. completed는 종료 시각에 새 작업을 멈춘 상태이며 모든 결과가 성공했음을 뜻하지 않는다. 별도 completed_count, failed_count와 이벤트를 함께 확인한다.

재시작 복구와 CLI 예시는 docs/overnight-runbook.md를 따른다. 개수 제한은 실행별 선택이며 활성 콘텐츠 순환은 한 개다. 새 실행에서 stop_after_posts 생략/null은 제한 없음이다. 문자열·불리언·소수·0·음수·1000 초과는 400으로 거절한다. 활성 실행에 개수를 생략하면 기존 설정을 유지한다. 성공적인 register만 1건을 세며 실패·재시도·카드 장수·영상 수·기존 콘텐츠 수는 무관하다. 목표 도달의 run.completed 이벤트에 완료 사유와 목표·완료 수를 기록한다. 완료된 실행은 재개할 수 없고 새 실행은 사용자가 명시적으로 시작한다. max_pending_requests는 이전 수동 요청 큐의 대기 한도이며 연속 생성 누적 건수와 무관하다. 세 콘텐츠 연속 실패, 실제 도구 사용 제한, 불확실한 외부 호출은 확인 없이 우회하지 않는다.

스튜디오 확장으로 로컬 페르소나 생성·선택을 제공한다. 실제 Instagram OAuth와 API 게시 전송 워커는 별도 연결 과제다. 이 API의 게시 소유권/결과 기록은 실제 SNS 전송을 수행하는 연결과 구분된다.

## 스튜디오 확장

### 전문 서브에이전트 배정

신규 run은 `specialist_agents_enabled:true`를 기본으로 고정하며 `config/specialists.json`의 역할 pack·버전·지침을 settings에 저장한다. 사용자 POST 본문으로 비활성화하지 못한다. 이전 실행은 저장된 설정으로 계속 읽을 수 있다. `worker-next`의 `job.input_json.specialist`에는 이번 단계 역할과 산출물 계약이 담긴다.

`POST /api/worker/agent` 입력은 `{cycle_id,lease_token,agent_id,role_id,action:"assign"}`이다. CLI는 `worker-agent CYCLE TOKEN --agent-id 실제canonicalID --role-id 역할ID`다. 총괄이 실제 Codex 위임 도구에서 받은 `/root/...` ID를 기록한다. 서버는 ID 형식·역할·소유권을 검증하며 Codex 런타임 자체를 인증하지 않는다(`recorded_by:coordinator`, `runtime_verified:false`). 같은 단계의 현재 배정을 다른 agent로 덮어쓸 수 없으며 품질 검수에는 같은 콘텐츠의 제작 agent를 재사용하지 못한다.

응답에는 `assignment_id`, `run_id`, `cycle_id`, `job_id`, `stage`, `role_id`, `role_name`, `agent_id`, `attempt`, `status`, `created_at`, `updated_at`, `result_summary`, `result_artifact`가 있다. 결과 저장은 `worker-complete.result.specialist_assignment_id`로 현재 배정을 참조해야 한다. 이전 시도나 다른 단계의 ID를 쓸 수 없다. 상태는 assigned/completed/failed/uncertain/interrupted로 완료·실패·중단 기록에 따라 바뀐다. `result_artifact`는 저장된 해당 단계 결과의 API URL이다. 원본 에이전트 출력 경로는 result의 `result_artifact`로 추가 보존할 수 있다.

`automation.specialists`는 현재 run의 enabled/roles/coordinator, 최근 assignments, current/latest와 **다음 실행용** configured_enabled/configured_roles/configured_coordinator/configuration_error를 구분해 제공한다. 배정 전 역할이 표시되는 것은 에이전트 실행을 뜻하지 않는다. 단계 JSON에도 specialist, specialist_assignment, specialist_assignments가 포함된다.

자동 영상은 전문 담당 배정을 production context에 고정하며 해당 배정이 현재 단계와 일치할 때만 images를 완료한다. 원래 전문 담당자의 결과는 비동기 완료 후에도 추적된다. 실제 위임·중지·결과 인계 순서는 [전문가 운영](specialist-agents.md)을 따른다.

### GS 공식 소재 자동 탐색

신규 run은 `settings.source_research_enabled:true`를 기본으로 고정한다. 사용자 POST 본문으로 이 검증을 끌 수 없다. 기존 저장 run의 설정은 그대로 유지한다. `worker-next`의 `job.input_json.source_research`에는 허용 공식 도메인, 조사 상한, 기존 소재와 작업자 계약이 포함된다. HTTP 서버는 웹 검색 도구가 아니며 Codex 작업자가 실제 웹 검색·원문 열기를 수행한다.

`POST /api/worker/sources`는 `cycle_id`, `lease_token`, `result`를 받는다. CLI는 `python3 apps/backend/server.py worker-sources CYCLE TOKEN --result 조사결과.json`이다. `result` 구조:

```text
queries: [{affiliate, query}]
materials: [{affiliate, title, url, verified_at, expires_at,
             claims: [확인한 사실], evidence: [{claim, excerpt}],
             material_type: brand|service|product|promotion,
             validity_note, visibility}]
rejected: [{url, reason}]
decision_summary: 짧은 공개 조사 요약
empty_reason: 채택 가능한 소재가 없을 때 실제 사유
```

종료일이 없는 일반 자료는 `expires_at:null`과 `validity_note`가 필요하고, promotion은 실제 미래 종료일이 필요하다. `queries`와 `materials` 상한은 작업 입력의 계약을 따른다. `evidence.claim`은 해당 `claims`의 사실과 일치해야 한다. 등록은 현재 sources 단계·유효한 작업 소유권·실행 상태에서만 가능하다. 자동 등록이 수동 수정 내용을 덮어쓰지 않는다.

응답은 `research_id`, `run_id`, `cycle_id`, `source_ids`, `added_count`, `reused_count`, `skipped_count`, `rejected_count`, `outcome`, `empty_reason`, `queries`, `rejected`, `skipped`, `materials`, `decision_summary`, `created_at`, `provenance`를 포함하는 조사 기록이다. `provenance.provider:codex-web`, `verified_by:worker`, `web_verified:true`는 작업자가 원문을 확인해 제출했다는 기록이며 서버가 페이지를 별도로 다운로드했다는 의미가 아니다.

sources 완료는 `worker-complete`에 `{research_id,source_ids,decision_summary}`를 제출한다. 서버가 해당 순환의 저장된 조사와 선택한 소재를 검증하고 완료 결과에 `source_research` 기록을 포함한다. 조사 기록 없는 신규 run 완료, 다른 순환의 기록 재사용, 미등록·만료 소재 선택은 거절한다. 검색 도구 오류는 `worker-fail`로 기록하고 빈 검색 성공으로 위장하지 않는다. 운영 절차와 출처 범위는 [GS 소재 자동 탐색](source-research.md)에 있다.

GET /api/state의 studio에는 personas, active_persona_id, briefs, settings가 추가된다. persona 레코드는 id/version/display_name/bio/profile/created_at/updated_at을 포함한다. profile은 기존 페르소나 설정과 같은 구조다. 기존 config의 첫 페르소나는 보존하며 새 프로필과 수정 버전은 SQLite에 저장한다.

| 경로 | 입력과 동작 |
|---|---|
| POST /api/personas | profile 객체로 새 페르소나 생성. 생성만으로 현재 인물이나 실제 SNS 계정을 바꾸지 않음 |
| POST /api/personas/:id | base_version, profile로 새 버전 저장. 오래된 편집 거절 |
| POST /api/personas/:id/select | 대시보드의 현재 인물 선택. 실행 중인 run의 인물 스냅샷 유지 |
| POST /api/briefs | persona_id, title, brief, format, affiliate로 기획 초안 저장 |
| POST /api/briefs/:id | base_version 및 수정 필드. 제작이 요청된 기획은 새 초안으로 작성 |
| POST /api/briefs/:id/produce | 실제 제작 대기열 연결. 동일 초안의 중복 요청 방지 |
| POST /api/settings | instagram.account 및 generation 운영 설정 저장. 인증 성공이나 유료 API 사용 권한을 설정값으로 주장할 수 없음 |
| GET /api/contents/:id/export | 현재 버전의 미디어·caption.txt·내부 manifest.json을 ZIP으로 다운로드. 승인·게시 상태 변경 없음 |

콘텐츠는 persona_id와 persona_version을 보존한다. 다른 인물을 선택하거나 프로필을 수정해도 이미 만들어진 콘텐츠의 검토·승인은 해당 원래 버전으로 가능하다. 제작 중인 실행은 run.persona 스냅샷을 유지하며, 새 프로필 버전은 다음 실행에 사용한다.

기획안만 요청한 실행은 queued 모드로 해당 인물의 요청을 소비하며 큐가 비면 완료된다. 콘텐츠 자동 생성은 continuous 모드로 새 이야기를 계속 만든다. 기존 연속 실행에 기획을 요청하면 다음 순환에서 해당 기획을 우선 사용한다. worker-next의 job.input_json을 파싱하면 brief에 기획안 스냅샷이 있으며 cycle.brief_id도 함께 반환된다. 단일 로컬 작업자에 다른 인물의 활성 실행을 동시에 요청하면 충돌을 안내한다.

다운로드 묶음에는 내부 출처·검토 메모가 포함된다. 공개 게시 문안은 caption.txt에서 분리해서 제공하며, ZIP 다운로드를 게시 성공 또는 사람의 승인으로 기록하지 않는다. 외부 Instagram OAuth·게시 전송 자체는 별도 연결 과제다.

페르소나 기준 이미지 등록은 POST /api/personas/:id/references에 version, mother(프로젝트 내 실제 파일 경로), daughter(선택)를 전달한다. 동일 버전·역할에는 최초 이미지가 고정되며 동일 경로와 해시의 재등록은 중복 처리한다. 다른 파일로 교체하려면 새 프로필 버전이 필요하다. GET /api/personas/:id/portrait는 등록된 실제 대표 이미지만 제공한다.

### 영상 제작 참고 MD

`GET /api/video`의 `guides`로 등록한 MD를 조회한다. `POST /api/video/guides`는 filename/content/base_version으로 등록하거나 같은 이름을 교체한다. `POST /api/video/guides/:id`는 base_version/enabled로 적용 여부를 바꾸고, `POST /api/video/guides/:id/delete`는 base_version으로 삭제한다. 변경 요청은 기존 로컬 인증을 사용한다. 수동 영상 요청의 guide_versions가 현재 활성 MD와 다르면 409다. AI 자동 제작은 콘텐츠 순환 시작 시 활성 MD를 고정해 각 단계의 job.input_json.video_guides로 전달하고, 자동 영상 모델에도 같은 본문과 버전을 사용한다. 변경은 다음 콘텐츠부터 적용되며 이미지 중심 실행에는 넣지 않는다. MD 관리는 콘텐츠 제작 → AI 자동 제작 안에서 수행한다. 상세 제한과 적용 범위는 [Segmind 연동](segmind-video.md#영상-제작-참고-md)을 따른다.
