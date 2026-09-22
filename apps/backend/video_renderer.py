"""Local subtitle compositor. Run with requirements-media.txt dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def dependencies():
    import imageio_ffmpeg
    from PIL import ImageFont
    font = Path(os.environ.get("BOCA_CAPTION_FONT", "/System/Library/Fonts/AppleSDGothicNeo.ttc"))
    if not font.is_file():
        raise ValueError("한국어 자막 글꼴을 찾을 수 없습니다. BOCA_CAPTION_FONT를 설정해 주세요.")
    ImageFont.truetype(str(font), 28)
    return imageio_ffmpeg.get_ffmpeg_exe(), font


def caption_image(text, destination, width, height, font_path):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(str(font_path), round(width * .0583), index=4)
    except OSError:
        font = ImageFont.truetype(str(font_path), round(width * .0583))
    stroke = max(2, round(width * .004))
    maximum = width * .76 - width * .05
    lines = [text]
    if draw.textlength(text, font=font) > maximum:
        candidates = []
        for i in range(1, len(text)):
            left, right = text[:i].strip(), text[i:].strip()
            lw, rw = draw.textlength(left, font=font), draw.textlength(right, font=font)
            if not left or not right or max(lw, rw) > maximum:
                continue
            word_boundary = text[i-1].isspace() or text[i].isspace() or text[i-1] in ",.!?"
            candidates.append((abs(lw-rw) + (0 if word_boundary else width*10), left, right))
        if not candidates:
            raise ValueError("자막이 두 줄을 넘습니다. 대사를 더 짧게 나눠 주세요.")
        _, left, right = min(candidates)
        lines = [left, right]
    label = "\n".join(lines)
    spacing = round(width * .012)
    box = draw.multiline_textbbox((0, 0), label, font=font, spacing=spacing, stroke_width=stroke)
    tw, th = box[2] - box[0], box[3] - box[1]
    padding = round(width * .024)
    x, y = width * .46 - tw / 2, height * .76 - th
    draw.rounded_rectangle((x-padding, y-padding, x+tw+padding, y+th+padding),
                           radius=round(width * .025), fill=(12, 14, 18, 200))
    draw.multiline_text((x-box[0], y-box[1]), label, font=font, fill="white", spacing=spacing,
                        align="center", stroke_width=stroke, stroke_fill="black")
    image.save(destination)


def render(raw, plan_path, output, resolution):
    ffmpeg, font = dependencies()
    plan = json.loads(plan_path.read_text())
    receipt_path = output.with_suffix(".receipt.json")
    digest = hashlib.sha256(raw.read_bytes() + plan_path.read_bytes() + resolution.encode()
                            + font.read_bytes() + Path(__file__).read_bytes()).hexdigest()
    if output.is_file() and receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("input_sha256") == digest and receipt.get("output_sha256") == hashlib.sha256(output.read_bytes()).hexdigest():
            return receipt
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(raw), "-map", "0:a:0", "-af", "volumedetect",
                            "-f", "null", "-"], capture_output=True, text=True, timeout=60)
    duration = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr)
    volume = re.search(r"max_volume: ([-\d.]+) dB", probe.stderr)
    if probe.returncode or not volume or float(volume[1]) < -65:
        raise ValueError("영상에 들을 수 있는 오디오가 없습니다. 원본은 보존했고 보이스 확인이 필요합니다. 자동 재생성하지 않습니다.")
    actual_duration = sum(float(value) * multiplier for value, multiplier in zip(duration.groups(), (3600, 60, 1))) if duration else 0
    if not actual_duration or any(cue["end"] > actual_duration + .1 for cue in plan["narration"]):
        raise ValueError("실제 영상 길이와 자막 시간이 맞지 않습니다. 원본과 대본을 확인해 주세요.")
    width, height = (480, 854) if resolution == "480p" else (720, 1280)
    folder = output.with_suffix(".captions")
    folder.mkdir(exist_ok=True)
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw)]
    filters = ["[0:v]scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1[v0]" % (width, height, width, height)]
    for i, cue in enumerate(plan["narration"], 1):
        png = folder / ("caption-%02d.png" % i)
        caption_image(cue["text"], png, width, height, font)
        args += ["-i", str(png)]
        filters.append("[v%d][%d:v]overlay=0:0:enable='gte(t,%.3f)*lt(t,%.3f)'[v%d]" % (i-1, i, cue["start"], cue["end"], i))
    temporary = output.with_name(output.stem + ".part.mp4")
    args += ["-filter_complex", ";".join(filters), "-map", "[v%d]" % len(plan["narration"]),
             "-map", "0:a:0", "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(temporary)]
    try:
        subprocess.run(args, capture_output=True, check=True, timeout=120)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    receipt = {"version": 1, "input_sha256": digest, "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
               "subtitles_burned_in": True, "caption_count": len(plan["narration"]),
               "audio_present": True, "voice_verified": False, "voice_review_required": True,
               "duration": actual_duration, "resolution": resolution, "style": plan["subtitle_style"],
               "review_required": plan["review_required"]}
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resolution", choices=["480p", "720p"])
    args = parser.parse_args()
    try:
        if args.check:
            dependencies()
            print("ready")
        else:
            print(json.dumps(render(args.input, args.plan, args.output, args.resolution), ensure_ascii=False))
    except Exception as exc:
        print(str(exc) if isinstance(exc, ValueError) else "자막 편집 실패: 로컬 도구와 원본 미디어를 확인해 주세요.", file=sys.stderr)
        sys.exit(1)
