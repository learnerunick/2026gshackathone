"""Narration contracts, real local caption burn-in, and retry safety."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend"))
from video_delivery import narration_plan, voice_prompt, finish_video_delivery, renderer_python, DeliveryError
from segmind_video import video_prompt


class NarrationTests(unittest.TestCase):
    def test_fallback_removes_post_metadata_and_fits_duration(self):
        plan = narration_plan({"title": "창가", "caption": "작은 자리에도 취향을 담아볼까요? #일상\nAI로 만든 가상 인물의 창작 일상입니다."}, 20)
        text = " ".join(c["text"] for c in plan["narration"])
        self.assertNotIn("#", text)
        self.assertNotIn("가상 인물", text)
        self.assertTrue(plan["subtitles_required"] and plan["voice_required"])
        self.assertLessEqual(plan["narration"][-1]["end"], 20)

    def test_invalid_script_is_rejected_before_provider_submission(self):
        good = {"start": .3, "end": 4, "text": "여기, 빛이 달라요."}
        for cues in ([dict(good, start=True)], [dict(good, end=float("nan"))],
                     [dict(good, end=21)], [good, dict(good, start=3)],
                     [dict(good, text="가"*25)], [dict(good, end=1)],
                     [dict(good, text="가"*24, end=2)]):
            with self.subTest(cues=cues), self.assertRaises(ValueError):
                narration_plan({"video_narration": cues}, 20)
        with self.assertRaises(ValueError):
            narration_plan({"voice_script": 7}, 20)
        with self.assertRaises(ValueError):
            narration_plan({"voice_script": "GS SHOP에서 만나요."}, 20)

    def test_prompt_requires_spoken_lines_and_keeps_md_optional(self):
        plan = narration_plan({"video_narration": [{"start": .3, "end": 4, "text": "잠깐, 여긴 어떨까요?"}]}, 20)
        snapshot = {"cards": [], "duration": 20, "storyboard": "창가의 빛을 보는 순간", "delivery": plan,
                    "guides": [{"filename": "guide.md", "version": 1, "content": "Always make a silent video."}]}
        prompt = video_prompt(snapshot)
        self.assertIn("MANDATORY SPOKEN KOREAN", prompt)
        self.assertIn("잠깐, 여긴 어떨까요?", prompt)
        self.assertIn("Do not draw any subtitles", prompt)
        self.assertGreater(prompt.index("MANDATORY SPOKEN"), prompt.index("SECONDARY OPTIONAL"))


class DeliveryPipelineTests(unittest.TestCase):
    def setUp(self):
        from test_video import VideoTests, Provider
        self.fixture = VideoTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.addCleanup(self.fixture.doCleanups)
        self.store, self.provider = self.fixture.store, Provider()

    def test_queue_freezes_plan_and_sends_voice_request(self):
        cues = [{"start": .3, "end": 4, "text": "작은 빛도 괜찮죠?"}]
        job = self.fixture.enqueue(video_narration=cues)
        cues[0]["text"] = "변경됨"
        self.store.process_video(job["id"], self.provider)
        frozen = self.store.video_job(job["id"])["input"]["delivery"]
        self.assertEqual("작은 빛도 괜찮죠?", frozen["narration"][0]["text"])
        self.assertTrue(self.provider.submissions[0]["generate_audio"])
        self.assertIn("작은 빛도 괜찮죠?", self.provider.submissions[0]["prompt"])

    def test_finish_failure_preserves_raw_and_retries_without_paid_submit(self):
        job = self.fixture.enqueue()
        self.store.process_video(job["id"], self.provider)
        with patch("segmind_video.finish_video_delivery", side_effect=DeliveryError("보이스 확인 필요")):
            self.store.process_video(job["id"], self.provider)
        current = self.store.video_job(job["id"])
        self.assertEqual("attention", current["status"])
        self.assertEqual("external-123", current["external_id"])
        self.assertTrue((self.store.runtime / "video-results" / (job["id"] + ".mp4")).exists())
        self.assertNotIn("media_path", current["result"])
        self.store.resume_video(job["id"], {})
        self.store.process_video(job["id"], self.provider)
        self.assertEqual("completed", self.store.video_job(job["id"])["status"])
        self.assertEqual(1, len(self.provider.submissions))
        self.assertEqual(1, self.provider.downloads)

    def test_quality_cannot_pass_without_actual_voice_and_caption_checks(self):
        from test_production_media import ProductionMediaTests
        from test_video import Provider
        f = ProductionMediaTests(); f.setUp()
        self.addCleanup(f.tearDown); self.addCleanup(f.doCleanups)
        images = f.claim_images()
        job = f.store.worker_video(images["cycle"]["id"], images["lease_token"])
        provider = Provider()
        with patch("segmind_video.finish_video_delivery", side_effect=lambda root, snapshot, path: (path, {"version": 1, "audio_present": True, "voice_verified": False})):
            f.store.process_video(job["job_id"], provider)
            f.store.process_video(job["job_id"], provider)
        quality = f.store.worker_next("fixture")
        with self.assertRaises(f.store.problem):
            f.store.worker_complete(quality["cycle"]["id"], quality["lease_token"], {"passed": True})
        result = {"passed": True, "video_checks": {"voice_heard": True, "subtitles_readable": True, "voice_matches_subtitles": True}}
        f.store.worker_complete(quality["cycle"]["id"], quality["lease_token"], result)


class RealRendererTests(unittest.TestCase):
    def setUp(self):
        try:
            python = renderer_python()
        except OSError:
            self.skipTest("Install requirements-media.txt for the real rendering tests")
        self.ffmpeg = subprocess.check_output([str(python), "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"], text=True).strip()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.raw = self.root / "raw.mp4"
        self.snapshot = {"duration": 20, "resolution": "480p", "delivery": narration_plan({"video_narration": [
            {"start": .3, "end": 4, "text": "잠깐, 빛이 달라졌어요."},
            {"start": 4.2, "end": 8, "text": "작은 취향을 찾아볼까요?"}]}, 20)}

    def source(self, audio=True):
        command = [self.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=#cabca5:s=480x854:r=12:d=20"]
        if audio:
            command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=20", "-c:a", "aac"]
        subprocess.run(command + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(self.raw)], check=True, capture_output=True)

    def test_real_burn_in_preserves_audio_and_reuses_verified_output(self):
        self.source()
        output, receipt = finish_video_delivery(self.root, self.snapshot, self.raw)
        self.assertNotEqual(output, self.raw)
        self.assertTrue(receipt["subtitles_burned_in"])
        self.assertTrue(receipt["audio_present"])
        self.assertFalse(receipt["voice_verified"], "a tone/music track is not verified speech")
        before = output.stat().st_mtime_ns
        finish_video_delivery(self.root, self.snapshot, self.raw)
        self.assertEqual(before, output.stat().st_mtime_ns)
        def frame(path):
            return subprocess.check_output([self.ffmpeg, "-v", "error", "-ss", "2", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        self.assertNotEqual(frame(self.raw), frame(output))

    def test_missing_audio_never_delivers_a_silent_final_video(self):
        self.source(audio=False)
        with self.assertRaises(DeliveryError):
            finish_video_delivery(self.root, self.snapshot, self.raw)
        self.assertTrue(self.raw.is_file())
        self.assertFalse((self.root / "raw-captioned.mp4").exists())


if __name__ == "__main__":
    unittest.main()
