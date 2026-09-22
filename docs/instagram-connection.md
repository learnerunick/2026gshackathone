# Instagram 계정 인증 연결

Instagram Login 토큰은 `.runtime/secrets/instagram-token`에만 저장한다. 파일 권한은 0600, 상위 디렉터리는 0700이다. `.runtime`은 Git 제외 대상이다. 토큰을 소스 코드, 일반 설정, 브라우저 상태, 로그에 넣지 않는다.

대시보드 설정에서 대상 계정을 저장한 뒤 **연결 다시 확인**을 누르면 `POST /api/instagram/verify`가 서버의 토큰으로 다음 읽기 전용 호출을 수행한다.

Vercel 화면에서도 로그인 세션과 요청 인증을 거쳐 같은 Mac 서버의 검증 경로를 사용한다. 토큰은 Mac에만 보관하며 Vercel 환경변수나 Git에 복사하지 않는다.

- `GET https://graph.instagram.com/v26.0/me?fields=id,user_id,username,account_type`
- `GET https://graph.instagram.com/v26.0/{user_id}/content_publishing_limit?fields=config,quota_usage`

API가 반환한 계정명이 저장된 대상과 일치하고 프로페셔널 계정이며 게시 한도 조회가 성공한 경우만 인증 완료로 표시한다. 검증 기록은 비공개 파일에 저장하고, 프론트엔드에는 허용한 공개 상태 필드만 전달한다. 계정 변경, 토큰 변경·삭제, 검증 실패 시 미연결로 처리하며, 확인 기록이 24시간을 넘으면 재확인을 요구한다. 이 24시간은 검증 기록의 유효 기간이며 토큰의 실제 만료 시각을 뜻하지 않는다.

토큰 재발급 시 서버의 비공개 파일을 교체하고 연결을 다시 확인한다. 현재 장기 토큰 교환·자동 갱신은 구현하지 않았다.

**계정 인증은 게시 작업자 구현과 별개다.** 현재 `publisher_ready`는 false이며, 실제 Instagram 게시·미디어 업로드 요청을 실행하지 않는다. 승인 대기는 보존하고 게시 claim도 준비 완료 전에는 차단한다. 외부에서 접근 가능한 미디어 URL과 버전 승인·중복 방지를 연결한 게시 작업자가 추가로 필요하다.
