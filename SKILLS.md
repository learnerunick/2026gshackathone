# 프로젝트 스킬 연결 내역

연결일: 2026-09-21

사용자가 추천한 스킬을 모두 연결해 달라고 요청해 아래 구성을 적용했다. 여기서 연결은 Codex가 읽고 사용할 수 있도록 스킬과 필요한 참고 지침을 설치한 것을 뜻한다. 서비스 백엔드의 생성 API, SNS 계정, Remotion 영상 프로젝트까지 구축한 상태는 아니다.

## 사용 가능한 구성

| 스킬 | 상태 | 용도 | 설치 범위 |
| --- | --- | --- | --- |
| `imagegen` | 기존 스킬 유지 | 실사형 기준 이미지 및 장면 생성·수정 | 사용자 환경의 시스템 스킬 |
| `skill-creator` | 기존 스킬 유지 | 프로젝트용 스킬 제작·수정 | 사용자 환경의 시스템 스킬 |
| `openai-docs` | 기존 스킬 유지 | 모델·SDK·인증 관련 공식 문서 확인 | 사용자 환경의 시스템 스킬 |
| `grill-me`, `grilling` | 기존 설치 유지 | 미정 사항과 설계 의존성을 질문으로 구체화 | 사용자 환경 |
| `frontend-design` | 추가 설치 완료 | 대시보드의 시각적 설계와 UI 구현 | 사용자 환경 |
| `playwright` | 추가 설치 완료 | 실제 브라우저에서 UI 흐름 확인 | 사용자 환경 |
| `remotion-best-practices` | 추가 설치 완료 | Remotion 영상 제작·편집·렌더링 지침 | 사용자 환경 |
| `persona-content` | 프로젝트용으로 새로 작성 | 페르소나·스토리·카드·문안·출처·일관성 검수 | 이 프로젝트 |

추가 설치한 외부 스킬은 `~/.agents/skills/` 아래에 있다. 프로젝트 전용 스킬은 [`.agents/skills/persona-content/SKILL.md`](.agents/skills/persona-content/SKILL.md)에 있다.

## 출처와 설치 버전

| 스킬 | 원본 | 설치 기준 커밋 |
| --- | --- | --- |
| `frontend-design` | [anthropics/skills — skills/frontend-design](https://github.com/anthropics/skills/tree/34040c9c568585f6929bedeaad110ad08f079624/skills/frontend-design) | `34040c9c568585f6929bedeaad110ad08f079624` |
| `playwright` | [openai/skills — skills/.curated/playwright](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/playwright) | `49f948faa9258a0c61caceaf225e179651397431` |
| `remotion-best-practices` | [remotion-dev/skills — skills/remotion-best-practices](https://github.com/remotion-dev/skills/tree/bbb139d5ba3709b1ffeb27184e9579c681230a08/skills/remotion-best-practices) | `bbb139d5ba3709b1ffeb27184e9579c681230a08` |

Remotion의 버전 메타데이터는 `4.0.526`이다. 이 스킬에 포함된 생성, 마크업, 자막, 미리보기, 렌더링 등 하위 참고 문서도 함께 설치했다.

원본에 적용한 호환 수정은 다음과 같다.

- Playwright의 실행 도구 경로를 실제 설치 위치인 `~/.agents/skills/playwright/scripts/playwright_cli.sh`에 맞췄다. 시스템 환경 변수 `CODEX_HOME`을 다시 설정하는 예제는 제거했다.
- Remotion의 최상위 `version` 필드를 `metadata.version`으로 옮겨 스킬 형식에 맞췄다. 본문과 하위 지침은 유지했다.

## 프로젝트 전용 콘텐츠 스킬

`persona-content`에는 다음 프로젝트 기준을 반영했다.

- 실사형 가상 인플루언서와 공감·일상 공유·취향 발견 중심의 이야기.
- 페르소나 기준 이미지의 역할 구분과 결과 비교. 이름·연령·성별 등 미정인 설정은 임의로 확정하지 않음.
- 약 5장을 참고하되, 콘텐츠에 따라 카드 장수를 유동적으로 정함.
- 상품 출처와 유효기간, 최근 주제 중복, 가상 인물 표시, 허구의 구매·사용 경험 여부 확인.
- 사람이 수정한 내용과 콘텐츠 버전 보존. AI 검수와 사람의 승인을 구분.
- 편집 영상과 생성 영상을 구분하고, 실제 실행은 현재 요청과 기존 승인 범위를 따름.

이 스킬은 [프로젝트 인계 문서](PROJECT_HANDOFF.md)를 참고한다. 프로젝트를 이동하거나 공유할 때 해당 문서도 함께 유지한다.

## 사용 예시

```text
$grill-me MVP 시연 범위를 구체화해줘.
$persona-content 현재 합의된 페르소나 자료로 카드형 피드 스토리보드를 작성해줘.
$imagegen 확정한 인물 기준 이미지를 참고해 다음 장면을 만들어줘.
$frontend-design 콘텐츠 미리보기와 수정·승인이 편한 대시보드를 구현해줘.
$playwright 로컬 대시보드의 수정·승인·재승인 흐름을 확인해줘.
$remotion-best-practices 완성된 이미지와 문안으로 짧은 편집 영상을 만들어줘.
$openai-docs 선택한 생성 API의 현재 인증 방식과 호출 방법을 확인해줘.
```

예시는 향후 사용 방법이며, 설치 과정에서 이 작업들을 실행한 것은 아니다. 새 스킬은 다음 대화 차례부터 사용할 수 있고, 목록에 표시되지 않으면 앱을 재시작한다.

## 확인한 범위

- 새로 설치·작성한 네 스킬의 형식 검증 통과.
- 스킬 내부의 상대 Markdown 링크와 참고 문서 존재 확인.
- 기존 `imagegen`, `skill-creator`, `openai-docs`, `grill-me`, `grilling` 파일 존재 확인.
- Node.js와 `npx` 사용 가능 확인.
- Playwright 실행 도구의 `--help` 호출 성공. 실제 브라우저의 UI 조작은 아직 실행하지 않음.
- Remotion 영상 프로젝트 생성·렌더링, 이미지·영상 생성, SNS 게시 실행은 하지 않음.

## 팀원에게 공유할 때

프로젝트의 `.agents/skills/persona-content/`와 이 문서·인계 문서는 함께 공유할 수 있다. 사용자 환경의 외부 스킬은 프로젝트 파일만 전달하면 설치되지 않으므로, 팀원 환경에서 `skill-installer`로 위 원본 경로와 버전을 설치한다. 스킬이 있다고 해서 생성 서비스의 계정·인증·예산·게시 권한이 공유되는 것은 아니다.
