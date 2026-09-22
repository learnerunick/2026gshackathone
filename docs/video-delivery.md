# 영상 자막·보이스 필수 구성

새 영상 요청은 한국어 보이스 대본과 같은 내용의 자막을 포함한다. 기존에 접수·완료한 영상의 입력이나 사람의 승인 버전은 변경하지 않는다. 기존 20초·480p 자동 기본값과 Segmind 한 편 $8·하루 $15·대기 2건 한도는 유지한다.

## 전문가 인계

- 스토리보드: 각 장면의 행동·감정·보이스 시점과 쉼을 설계한다. 대사·작은 반응으로 재미를 만들되 매번 같은 도입이나 웃음소리를 반복하지 않는다.
- 카피: 영상이면 `video_narration: [{"start":0.3,"end":3.8,"text":"여기, 빛이 달라졌어요."}]`를 작성한다. 항목당 24자 이내·최소 1.2초·초당 최대 7자, 시간 중첩 금지, 영상 길이 안에 배치한다. 실제 구매·사용 경험이나 근거 없는 상품 주장은 만들지 않는다.
- 비주얼: 같은 대본을 Segmind의 한국어 보이스 생성 지시문에 넣는다. 캐릭터 성격·말투에 맞는 일관된 창작 목소리, 자연스러운 쉼·반응, 목소리보다 작은 음악·생활음을 요구한다. 생성 모델에 한글을 그리게 하지 않는다.
- 서버: 생성 원본을 보존하고 자막을 별도 로컬 편집으로 MP4에 직접 입힌다. 자막 합성이 끝나야 완성 미디어로 전달한다.
- 검수: 실제 완성본을 재생·청취하고 `video_checks: {"voice_heard":true,"subtitles_readable":true,"voice_matches_subtitles":true}`와 근거를 제출해야 quality 완료가 가능하다. 읽기 속도·위치·잘림·오타·타이밍도 확인한다. 오디오 트랙이나 배경음만으로 보이스를 확인했다고 표시하지 않는다.

수동 영상은 `voice_script`로 대본을 입력할 수 있다. 비우면 게시 문안 앞부분에서 해시태그·URL·별도 가상 인물 고지를 뺀 문장을 짧게 나눠 사용하며 `source:caption_fallback`으로 남긴다. 자동 제작에서는 `copy.video_narration`을 우선하고, 이전 기획과의 호환을 위해 대본이 없을 때도 같은 fallback을 명시적으로 기록한다. 게시 문안의 가상 인물 고지는 유지된다.

## 가독성과 저장

- 480p 약 28px / 720p 약 42px 한국어 글꼴, 흰 글씨·검은 외곽선·어두운 반투명 배경, 최대 두 줄.
- 화면 너비의 약 76% 안에 배치하며 화면 맨 아래와 오른쪽을 비워 버튼·게시 문안에 가려질 가능성을 줄인다. 특정 플랫폼의 모든 UI에 대한 보장은 아니며 실제 게시 미리보기에서 확인한다.
- 영상마다 생성 입력에 `delivery` 대본·스타일·버전을 고정한다. 입력/출력 해시와 자막 개수·오디오 확인·검수 요구를 receipt에 저장한다.
- 원본 `video-ID.mp4`, 자막 완성 `video-ID-captioned.mp4`, 대본 `.delivery.json`, 렌더 receipt·자막 PNG를 보존한다. 같은 입력으로 재개하면 기존 완성본 해시를 확인해 재사용한다.
- 오디오 없음·무음·자막 합성 실패는 `attention`으로 남긴다. `resume_video`는 저장된 원본의 후편집만 재개하며 Segmind에 유료 생성을 재제출하지 않는다. 자막 완료 파일이 등록되기 전에는 완성이라고 표시하지 않는다.
- `audio_present:true`는 음성 인식 결과가 아니다. `voice_verified:false`/`voice_review_required:true`를 명시하고 독립 검수와 사람 승인으로 실제 한국어 대사를 확인한다.

## 로컬 설치

```sh
python3 -m venv .runtime/media-venv
.runtime/media-venv/bin/python -m pip install -r requirements-media.txt
.runtime/media-venv/bin/python apps/backend/video_renderer.py --check
```

FFmpeg는 imageio-ffmpeg에 포함된 실행 파일을 사용한다. macOS 기본 글꼴은 Apple SD Gothic Neo다. 다른 환경에서는 한국어 글꼴 파일을 `BOCA_CAPTION_FONT`, 편집용 Python 경로를 `BOCA_MEDIA_PYTHON`으로 지정한다. 도구·글꼴 사전 확인 실패 시 유료 영상 요청 전에 중지한다. 외부 TTS 요금제나 API 키는 추가하지 않았다.

Segmind의 [현재 API 문서](https://www.segmind.com/models/seedance-2.5/api)는 `generate_audio`의 대화·효과음·음악 공동 생성을 지원한다. 대사 준수·음질·싱크는 결과마다 확인해야 한다. 자막은 로컬 이미지 오버레이를 사용하며 [FFmpeg 필터](https://ffmpeg.org/ffmpeg-filters.html)의 타임라인으로 합성한다.
