"""Frozen Korean narration/caption plan and deterministic local finishing."""
import json
import math
import os
from pathlib import Path
import re
import subprocess

DISCLOSURE = "AI로 만든 가상 인물의 창작 일상입니다."


class DeliveryError(OSError):
    """Raw generation is safe; finishing needs attention, never resubmission."""


def narration_plan(body, duration):
    if body.get("voice_script") is not None and not isinstance(body["voice_script"], str):
        raise ValueError("보이스 대본은 문자열이어야 합니다.")
    cues = body.get("video_narration")
    source = "script"
    if cues is None:
        # Compatibility for existing briefs and the manual form. Use supplied
        # copy, never invent a product claim or speak camera instructions.
        source = "caption_fallback"
        text = body.get("voice_script") or body.get("caption", "")
        text = re.sub(r"https?://\S+|#[^\s#]+", "", text.replace(DISCLOSURE, ""))
        text = re.sub(r"\s+", " ", text).strip() or body.get("title", "")
        limit = int((duration - 1) * 4)
        if body.get("voice_script") and len(text) > limit:
            raise ValueError("보이스 대본은 %s초 기준 %s자 이내로 줄여 주세요." % (duration, limit))
        text = text[:limit].rstrip()
        chunks = []
        while text:
            end = min(22, len(text))
            if len(text) > end:
                boundary = text.rfind(" ", 8, end)
                if boundary > 0:
                    end = boundary
            chunks.append(text[:end].strip())
            text = text[end:].strip()
        if not chunks:
            raise ValueError("영상에는 한국어 보이스 대본과 자막이 필요합니다.")
        slot = (duration - .8) / len(chunks)
        cues = [{"start": round(.3 + i * slot, 2), "end": round(.3 + (i + 1) * slot, 2), "text": text}
                for i, text in enumerate(chunks)]
    if not isinstance(cues, list) or not 1 <= len(cues) <= 20:
        raise ValueError("video_narration에는 시간과 대사가 있는 1~20개 항목이 필요합니다.")
    clean, previous = [], 0
    for cue in cues:
        if not isinstance(cue, dict):
            raise ValueError("영상 대사는 start, end, text 객체여야 합니다.")
        start, end, text = cue.get("start"), cue.get("end"), cue.get("text")
        if (type(start) not in (float, int) or type(end) not in (float, int)
                or not math.isfinite(start) or not math.isfinite(end)
                or start < previous or end > duration or end - start < 1.2):
            raise ValueError("대사 시간은 겹치지 않고 영상 길이 안에 있어야 하며, 자막당 최소 1.2초가 필요합니다.")
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > 24:
            raise ValueError("자막 한 항목은 읽기 쉽게 24자 이내로 나눠 주세요.")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) / (end - start) > 7:
            raise ValueError("자막이 너무 빠릅니다. 대사를 줄이거나 표시 시간을 늘려 주세요.")
        clean.append({"start": float(start), "end": float(end), "text": text})
        previous = end
    public_text = re.sub(r"[\s._-]", "", "".join(c["text"] for c in clean)).lower()
    if any(term in public_text for term in ("gsshop", "gs샵", "gs숍", "gs쇼핑", "지에스샵", "지에스숍")):
        raise ValueError("보이스·자막에 GS SHOP 판매처명을 넣을 수 없습니다.")
    return {"version": 1, "source": source, "language": "ko-KR", "narration": clean,
            "voice_required": True, "subtitles_required": True,
            "voice_direction": "페르소나의 성격·말투를 유지하는 자연스러운 한국어 대화체. 짧은 반응과 쉼, 작은 웃음으로 생동감을 주고 광고 낭독·과장된 성대모사는 피한다. 음악과 생활음은 목소리보다 작게.",
            "subtitle_style": {"font_ratio": .0583, "max_lines": 2, "max_width_ratio": .76,
                               "center_x_ratio": .46, "bottom_ratio": .76, "color": "white",
                               "background": "black_78_percent", "outline": True},
            "review_required": ["voice_heard", "subtitles_readable", "voice_matches_subtitles"]}


def voice_prompt(delivery):
    return ("\nMANDATORY SPOKEN KOREAN VOICEOVER: Generate clearly audible spoken Korean, not only music or ambience. "
            "Use one consistent original voice matching the persona. Read the following exact lines naturally at the indicated seconds. "
            "Do not read directions or add unsupported product claims. Keep background sound below the voice. "
            "Do not draw any subtitles, letters, captions or logos in the generated frames: exact Korean subtitles will be burned in locally after generation.\n"
            + delivery["voice_direction"] + "\nTIMED SPOKEN LINES:\n"
            + json.dumps(delivery["narration"], ensure_ascii=False))


def renderer_python():
    path = Path(os.environ.get("BOCA_MEDIA_PYTHON") or
                Path(__file__).resolve().parents[2] / ".runtime/media-venv/bin/python")
    if not path.is_file():
        raise OSError("자막 편집 도구가 없습니다. docs/video-delivery.md의 로컬 설치를 완료해 주세요.")
    return path


def ensure_delivery_tools():
    try:
        subprocess.run([str(renderer_python()), str(Path(__file__).with_name("video_renderer.py")), "--check"],
                       check=True, capture_output=True, text=True, timeout=20)
    except (subprocess.SubprocessError, OSError) as exc:
        raise OSError("자막 편집 도구·한국어 글꼴을 확인해 주세요. 영상 생성은 접수하지 않았습니다.") from exc


def finish_video_delivery(root, snapshot, raw_path):
    if not snapshot.get("delivery"):
        return raw_path, None  # Previously submitted jobs keep their frozen contract.
    plan_path = raw_path.with_suffix(".delivery.json")
    plan_path.write_text(json.dumps(snapshot["delivery"], ensure_ascii=False, indent=2))
    output = raw_path.with_name(raw_path.stem + "-captioned.mp4")
    command = [str(renderer_python()), str(Path(__file__).with_name("video_renderer.py")),
               "--input", str(raw_path), "--plan", str(plan_path), "--output", str(output),
               "--resolution", snapshot["resolution"]]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
        metadata = json.loads(result.stdout)
    except subprocess.TimeoutExpired as exc:
        raise DeliveryError("자막 편집 시간이 초과되었습니다. 원본과 외부 작업 ID를 보존해 편집만 재개합니다.") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or "자막 편집 실패").strip().splitlines()[-1][:400]
        raise DeliveryError(message) from exc
    return output, metadata
