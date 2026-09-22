"""Bridge AI production stages to the existing bounded Segmind queue."""
import json
from datetime import datetime, timedelta, timezone


class ProductionMediaStore:
    def _verified_terminal_video(self, db, cycle, job_id, status):
        """Only a recorded, matching provider result can resolve uncertainty."""
        job = db.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone() if job_id else None
        if not job or job["status"] != status or not job["external_id"]:
            return None
        context = json.loads(job["input_json"]).get("production", {})
        if (context.get("cycle_id") != cycle["id"] or context.get("run_id") != cycle["run_id"]
                or cycle["stage_index"] != 4 or job["request_key"] != self._production_video_request_key(db, cycle["id"])):
            return None
        assignment = self._assignment_current(db, cycle)
        if context.get("specialist_assignment_id") and (not assignment or assignment["assignment_id"] != context["specialist_assignment_id"]):
            return None
        return job

    def _resume_resolved_video(self, db, cycle, job_id):
        # Run this in the same transaction that commits the resolved stage.
        # Pause/stop, another block, and the repeated-failure breaker still win.
        run = db.execute("SELECT * FROM production_runs WHERE id=?", (cycle["run_id"],)).fetchone()
        if (run["status"] != "blocked" or run["pause_reason"] not in ("외부 작업 결과 확인 필요", "중단된 작업 결과 확인 필요")
                or db.execute("SELECT 1 FROM production_cycles WHERE run_id=? AND status='uncertain'", (cycle["run_id"],)).fetchone()):
            return
        db.execute("UPDATE production_runs SET status='running',pause_reason=NULL,updated_at=? WHERE id=?",
                   (datetime.now(timezone.utc).isoformat(), cycle["run_id"]))
        self._event(db, cycle["run_id"], cycle["id"], "images", "run.video_resolved",
                    "기존 영상 작업의 최종 결과를 확인해 자동 제작을 이어갑니다.", {"video_job_id": job_id})

    def require_run_media(self, settings, media):
        if settings.get("media_mode") == "video_only" and (not media or any(
                not isinstance(path, str) or not path.lower().endswith(".mp4") for path in media)):
            raise self.problem("영상만 실행에는 MP4 영상만 사용할 수 있습니다. 이미지 피드로 대체할 수 없습니다.", 409)

    def _block_video_only(self, cycle_id, lease_token, reason):
        result = {"status": "blocked", "fallback": None, "reason": reason,
                  "next": "영상만 실행을 대기합니다. 조건을 해결한 뒤 대시보드에서 재개해 주세요."}
        with self.db() as db:
            cycle = self._leased(db, cycle_id, lease_token)
            now = datetime.now(timezone.utc).isoformat()
            # No external request was submitted. Release this stage without
            # consuming another retry when the user resumes the same story.
            db.execute("UPDATE jobs SET status='paused',result_json=?,updated_at=? WHERE id=?",
                       (json.dumps(result, ensure_ascii=False), now, cycle_id + ":images"))
            self._specialist_cycle_status(db, cycle_id, "interrupted", result["next"])
            db.execute("UPDATE production_cycles SET status='suspended',lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?",
                       (now, cycle_id))
            db.execute("UPDATE production_runs SET status='blocked',pause_reason=?,updated_at=? WHERE id=? AND status='running'",
                       ("영상만 제작 대기: " + reason, now, cycle["run_id"]))
            self._event(db, cycle["run_id"], cycle_id, "images", "media.video_blocked", result["next"], result, "warning")
            self._retire_if_terminal(db, cycle["run_id"])
        return result

    def _production_video_request_key(self, db, cycle_id):
        # A new lease/agent is recovery, not permission for another paid
        # generation. Only a committed quality repair creates a new key.
        repair = db.execute("SELECT id FROM production_events WHERE cycle_id=? AND event='quality.repair' ORDER BY id DESC LIMIT 1",
                            (cycle_id,)).fetchone()
        return "auto-" + cycle_id + ("-r" + str(repair["id"]) if repair else "")

    def validate_auto_video(self, value):
        if not isinstance(value, dict) or set(value) - {"duration", "resolution"}:
            raise self.problem("자동 영상 설정에는 길이와 해상도만 지정할 수 있습니다.")
        duration, resolution = value.get("duration", 20), value.get("resolution", "480p")
        if type(duration) is not int or not 20 <= duration <= 30:
            raise self.problem("자동 영상 길이는 20~30초 사이의 정수로 입력해 주세요.")
        if resolution not in ("480p", "720p"):
            raise self.problem("자동 영상 해상도는 480p 또는 720p를 선택해 주세요.")
        return {"duration": duration, "resolution": resolution}

    def run_video_settings(self, settings):
        # Runs created before per-run video options retain the previous defaults.
        video = settings.get("video", {})
        legacy = self.video_config()
        return self.validate_auto_video({key: video.get(key, legacy[key]) for key in ("duration", "resolution")})

    def _production_video_request(self, job, payload):
        context = job["input"].get("production")
        if not context:
            return
        request = {key: value for key, value in payload.items() if key != "reference_images"}
        request["reference_files"] = [{"media": card["media"], "sha256": card["sha256"]} for card in job["input"]["cards"]]
        with self.db() as db:
            self._event(db, context["run_id"], context["cycle_id"], "images", "media.video.request",
                        "AI 스토리보드의 실제 영상 생성 프롬프트를 저장했습니다.",
                        {"video_job_id": job["id"], "model": self.video_config()["model"], "request": request})

    def worker_video(self, cycle_id, lease_token):
        """Submit AI-authored storyboard/copy once, without a manual video form."""
        if not self.worker_ping(cycle_id, lease_token)["can_continue"]:
            raise self.problem("중지되거나 일시정지된 실행은 새 영상을 요청하지 않습니다.", 409)
        with self.db() as db:
            cycle = self._leased(db, cycle_id, lease_token)
            if cycle["stage_index"] != 4:
                raise self.problem("영상 요청은 미디어 제작 단계에서만 가능합니다.", 409)
            run = self._run(db.execute("SELECT * FROM production_runs WHERE id=?", (cycle["run_id"],)).fetchone())
            assignment = self._specialist_required_assignment(db, cycle)
            assignment_id = assignment["assignment_id"] if assignment else None
            outputs = json.loads(cycle["result_json"])
            guides = self.cycle_video_guides(db, cycle_id, run["settings"].get("media_mode", "images"))
            guide_policy = self.cycle_video_guide_policy(db, cycle_id)
            request_key = self._production_video_request_key(db, cycle_id)
            for row in db.execute("SELECT request_key,status,input_json FROM video_jobs WHERE status NOT IN ('completed','failed','cancelled')"):
                prior_context = json.loads(row["input_json"]).get("production", {})
                if prior_context.get("cycle_id") == cycle_id and row["request_key"] != request_key:
                    raise self.problem("이미 접수한 영상 결과를 확인하기 전에는 새 수정 영상을 요청할 수 없습니다.", 409)
        if run["settings"].get("media_mode", "images") not in ("mixed", "video", "video_only"):
            raise self.problem("이 실행은 이미지 전용입니다. 영상 포함 실행에서 요청해 주세요.", 409)
        planning, storyboard, copy = (outputs.get(name, {}) for name in ("planning", "storyboard", "copy"))
        if not storyboard.get("cards") or not copy.get("caption"):
            raise self.problem("AI 스토리보드와 게시 문안이 먼저 완료되어야 합니다.", 409)
        config = self.run_video_settings(run["settings"])
        body = {
            "request_key": request_key,
            "accept_estimated_cost": True,
            "persona_id": run["persona_id"], "persona_version": run["persona_version"],
            "title": planning.get("title", "가상 인물의 일상"),
            "storyboard": storyboard.get("video_prompt") or json.dumps(storyboard["cards"], ensure_ascii=False),
            "caption": copy["caption"], "duration": config["duration"], "resolution": config["resolution"],
        }
        narration = copy.get("video_narration", storyboard.get("video_narration"))
        if narration is not None:
            body["video_narration"] = narration
        context = {"run_id": run["id"], "cycle_id": cycle_id, "content_id": cycle["content_id"]}
        if assignment_id:
            context["specialist_assignment_id"] = assignment_id
        try:
            job = self.create_video(body, production_context=context, guide_snapshot=guides, guide_policy=guide_policy)
        except self.problem as exc:
            # Mixed and legacy video-priority runs retain their image fallback.
            if any(word in str(exc) for word in ("한도", "상한", "기준 이미지", "API 키")):
                if run["settings"].get("media_mode") == "video_only":
                    return self._block_video_only(cycle_id, lease_token, str(exc))
                result = {"status": "skipped", "fallback": "images", "reason": str(exc)}
                self.worker_log(cycle_id, lease_token, "media.video_skipped", "영상 조건을 충족하지 못해 이미지 피드로 계속합니다.", result, "warning")
                return result
            raise
        self._production_video_changed(job["id"])
        return {"status": job["status"], "job_id": job["id"], "external_job_id": job["external_id"],
                "estimated_cost": job["estimated_cost"], "result": job.get("result"),
                "next": ("영상 작업자가 결과를 저장하면 미디어 단계를 완료합니다. AI 작업자는 다음 단계를 즉시 진행합니다. "
                         + ("AI 품질 검수는 보류하고 기존 영상으로 피드 등록을 진행하세요. 미확인 항목은 사람의 검수 메모로 남깁니다."
                            if run["settings"].get("ai_quality_review_enabled", True) is False else "이후 품질 검수부터 이어갑니다."))}

    def _production_video_allowed(self, job, transition=None):
        # The state check and preparation/submission reservation share the same
        # SQLite write lock as pause/stop. A committed stop wins before a new
        # reservation; an existing submitting job is retained as in flight.
        changed = False
        with self.db() as db:
            row = db.execute("SELECT * FROM video_jobs WHERE id=?", (job["id"],)).fetchone()
            if not row or row["status"] not in ("queued", "preparing"):
                return False
            if transition and row["status"] != {"preparing": "queued", "submitting": "preparing"}[transition]:
                return False
            context = json.loads(row["input_json"]).get("production")
            allowed, terminal = True, False
            if context:
                run = self._refresh(db, db.execute("SELECT * FROM production_runs WHERE id=?", (context["run_id"],)).fetchone())
                cycle = db.execute("SELECT * FROM production_cycles WHERE id=?", (context["cycle_id"],)).fetchone()
                allowed = bool(run and run["status"] == "running" and cycle and cycle["stage_index"] == 4 and cycle["status"] == "running")
                if allowed:
                    allowed = row["request_key"] == self._production_video_request_key(db, cycle["id"])
                if allowed and json.loads(run["settings_json"]).get("specialist_agents_enabled") is True:
                    assignment = self._assignment_current(db, cycle)
                    allowed = bool(assignment and assignment["assignment_id"] == context.get("specialist_assignment_id"))
                terminal = not run or run["status"] in ("stopped", "completed") or not cycle or cycle["status"] in ("failed", "cancelled", "completed")
            next_status = transition if allowed else ("cancelled" if terminal else "queued" if transition == "submitting" else None)
            if next_status:
                db.execute("UPDATE video_jobs SET status=?,updated_at=? WHERE id=? AND status IN ('queued','preparing')",
                           (next_status, datetime.now(timezone.utc).isoformat(), job["id"]))
                changed = True
        if changed:
            self._production_video_changed(job["id"])
        return allowed

    def _cancel_pending_production_videos(self, db, run_id):
        now = datetime.now(timezone.utc).isoformat()
        cancelled_cycles = set()
        for row in db.execute("SELECT * FROM video_jobs WHERE status IN ('queued','preparing')").fetchall():
            context = json.loads(row["input_json"]).get("production", {})
            if context.get("run_id") != run_id:
                continue
            db.execute("UPDATE video_jobs SET status='cancelled',error=?,updated_at=? WHERE id=?",
                       ("자동 제작 실행이 종료되어 영상 제출을 취소했습니다.", now, row["id"]))
            cancelled_cycles.add(context["cycle_id"])
            self._event(db, run_id, context["cycle_id"], "images", "media.video.cancelled",
                        "아직 제출하지 않은 영상 요청을 취소했습니다.", {"job_id": row["id"], "status": "cancelled"})
        in_flight = {json.loads(row[0]).get("production", {}).get("cycle_id") for row in db.execute(
            "SELECT input_json FROM video_jobs WHERE status IN ('submitting','running','downloading','uncertain','attention')")}
        for cycle_id in cancelled_cycles - in_flight:
            cycle = db.execute("SELECT * FROM production_cycles WHERE id=?", (cycle_id,)).fetchone()
            if cycle and cycle["stage_index"] == 4 and cycle["status"] == "running":
                db.execute("UPDATE production_cycles SET status='cancelled',lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?", (now, cycle_id))
                db.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE cycle_id=? AND status IN ('running','pending','paused')", (now, cycle_id))
                self._event(db, run_id, cycle_id, "images", "cycle.cancelled", "제출 전 영상 작업을 종료하고 기존 결과를 보존했습니다.")

    def _production_video_changed(self, job_id):
        job = self.video_job(job_id)
        context = job["input"].get("production")
        if not context:
            return
        attribution = {"specialist_assignment_id": context["specialist_assignment_id"]} if context.get("specialist_assignment_id") else {}
        token = None
        with self.db() as db:
            cycle = db.execute("SELECT * FROM production_cycles WHERE id=?", (context["cycle_id"],)).fetchone()
            if not cycle:
                return
            event = "media.video." + job["status"]
            prior = db.execute("SELECT detail_json FROM production_events WHERE cycle_id=? AND event=? AND detail_json LIKE ? ORDER BY id DESC LIMIT 1",
                               (cycle["id"], event, "%" + job_id + "%")).fetchone()
            recovery = {"poll_errors": job.get("poll_errors", 0), "next_retry_at": job.get("next_retry_at"), "error": job["error"]}
            previous = json.loads(prior[0]) if prior else {}
            if not prior or any(previous.get(key, 0 if key == "poll_errors" else None) != value for key, value in recovery.items()):
                detail = {"job_id": job_id, "status": job["status"], "external_job_id": job["external_id"],
                          "estimated_cost": job["estimated_cost"], "result": job.get("result"), **recovery}
                if job["status"] == "queued":
                    detail["input"] = job["input"]
                message = "Segmind 자동 영상: " + job["status"]
                if job.get("next_retry_at") and job["error"]:
                    message = "영상 통신 오류 " + str(job["poll_errors"]) + "회 · 기존 작업의 복구를 예약했습니다."
                self._event(db, context["run_id"], cycle["id"], "images", event, message, detail,
                            "error" if job["status"] in ("failed", "uncertain", "attention") else "warning" if job["error"] else "info")
            bound_assignment = self._assignment_current(db, cycle) if cycle["stage_index"] == 4 else None
            assignment_matches = not context.get("specialist_assignment_id") or bool(bound_assignment and bound_assignment["assignment_id"] == context["specialist_assignment_id"])
            request_matches = job["request_key"] == self._production_video_request_key(db, cycle["id"])
            if cycle["stage_index"] == 4 and cycle["status"] in ("running", "uncertain") and assignment_matches and request_matches:
                token = cycle["lease_token"]
                if job["external_id"]:
                    db.execute("UPDATE jobs SET external_job_id=? WHERE id=?", (job["external_id"], cycle["id"] + ":images"))
                if job["status"] in ("queued", "preparing", "submitting", "running", "downloading"):
                    now = datetime.now(timezone.utc)
                    db.execute("UPDATE production_cycles SET lease_expires_at=?,updated_at=? WHERE id=?",
                               ((now + timedelta(minutes=15)).isoformat(), now.isoformat(), cycle["id"]))
                    db.execute("UPDATE production_runs SET last_heartbeat_at=? WHERE id=?", (now.isoformat(), context["run_id"]))
                    db.execute("UPDATE jobs SET result_json=?,updated_at=? WHERE id=?",
                               (json.dumps({"provider": "segmind", "video_job_id": job_id, "status": job["status"],
                                            "external_job_id": job["external_id"], **recovery, **attribution}, ensure_ascii=False), now.isoformat(), cycle["id"] + ":images"))
        if not token:
            return
        if job["status"] == "completed":
            self.worker_complete(context["cycle_id"], token,
                                 {"media": [job["result"]["media_path"]], "provider": "segmind", "video_job_id": job_id,
                                  "metrics": job["result"].get("metrics", {}), "review_required": True,
                                  "video_delivery": job["result"].get("delivery"),
                                  **attribution}, job["external_id"])
        elif job["status"] in ("failed", "uncertain", "attention"):
            self.worker_fail(context["cycle_id"], token, job["error"] or "영상 작업 확인 필요", retryable=False,
                             uncertain=job["status"] in ("uncertain", "attention"),
                             resolved_video_job_id=job_id if job["status"] == "failed" else None)
