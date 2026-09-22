"""Immediate, single-owner Codex production runner for the local dashboard.

Only serve starts this runner. Importing Store, reading state, and tests never
launch an AI process. SQLite stage leases remain the authority for all work.
"""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone

TIMEOUT_MESSAGE = "제작 작업자의 최대 실행 시간(45분)을 초과했습니다. 저장된 결과를 확인해 주세요."
NETWORK_MESSAGE = "Codex 네트워크 연결이 2분 동안 복구되지 않아 현재 작업자를 종료했습니다."
RESTART_MESSAGE = "서버 교체 후 기존 작업자 종료를 확인했습니다. 저장된 텍스트 단계에서 복구합니다."


def classify_worker_error(event):
    detail = str(event).lower()
    if any(word in detail for word in ("usage limit", "rate limit", "quota", "429")):
        return "fatal", "Codex 사용 한도에 도달했습니다. 한도가 회복된 뒤 재개해 주세요."
    if any(word in detail for word in ("unauthorized", "authentication", "login", "401")):
        return "fatal", "Codex 로그인을 확인한 뒤 재개해 주세요."
    if any(word in detail for word in ("stream disconnected", "waiting for network", "connection failed", "reconnecting", "failed to lookup address")):
        return "network", NETWORK_MESSAGE
    return "fatal", "Codex 실행 오류로 제작을 중단했습니다. 작업자 진단 기록을 확인해 주세요."


def worker_state(store):
    try:
        value = json.loads((store.runtime / "ai-worker" / "status.json").read_text())
        age = time.time() - float(value.pop("seen_at"))
        value["online"] = age < 30 and value.get("status") != "stopped"
        return value
    except (OSError, ValueError, KeyError, TypeError):
        return {"online": False, "status": "offline", "message": "제작 작업자가 연결되지 않았습니다. 로컬 서버를 확인해 주세요."}


class LocalProductionWorker:
    def __init__(self, store, poll_seconds=2, process_factory=subprocess.Popen):
        self.store = store
        self.poll_seconds = poll_seconds
        self.process_factory = process_factory
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.worker_id = "local-codex-" + uuid.uuid4().hex[:12]
        self.max_stage_seconds = 2700
        self.network_grace_seconds = 120
        self.directory = store.runtime / "ai-worker"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.status = {"status": "idle", "worker_id": self.worker_id, "run_id": None,
                       "message": "제작 요청을 기다리고 있습니다."}
        self.thread = threading.Thread(target=self.work, name="boca-production", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def _status(self, **values):
        self.status.update(values)
        payload = dict(self.status, seen_at=time.time())
        target = self.directory / "status.json"
        temp = self.directory / (self.worker_id + ".tmp")
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        os.replace(str(temp), str(target))

    def _snapshot(self):
        with self.store.db() as db:
            run = self.store._refresh(db, db.execute("SELECT * FROM production_runs ORDER BY created_at DESC LIMIT 1").fetchone())
            cycle = db.execute("SELECT * FROM production_cycles WHERE run_id=? ORDER BY number DESC LIMIT 1", (run["id"],)).fetchone() if run else None
            return dict(run) if run else None, dict(cycle) if cycle else None

    def _runnable(self, run, cycle):
        if not run or run["status"] != "running":
            return False
        if cycle and cycle["status"] in ("running", "uncertain"):
            if cycle["status"] == "running" and self.store._time(cycle["lease_expires_at"]) <= datetime.now(timezone.utc):
                # Use the existing uncertainty guard; never steal a live lease.
                self.store.worker_next(self.worker_id)
            return False
        if cycle and cycle.get("retry_after") and self.store._time(cycle["retry_after"]) > datetime.now(timezone.utc):
            return False
        return True

    def _command(self):
        binary = os.environ.get("BOCA_CODEX_BIN") or shutil.which("codex")
        bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
        if not binary and bundled.is_file():
            binary = str(bundled)
        if not binary:
            raise RuntimeError("Codex CLI를 찾을 수 없습니다. 설치 또는 BOCA_CODEX_BIN 설정 후 재개해 주세요.")
        return [binary, "exec", "--json", "--ephemeral", "--color", "never",
                "-C", str(self.store.root), "-s", "workspace-write",
                "-c", 'approval_policy="never"',
                "-c", "sandbox_workspace_write.network_access=true",
                "-c", 'web_search="live"', "-"]

    def _prompt(self, run):
        return ("You are the authorized runtime coordinator for this user's Boca content production request, "
                "not a developer. Execute the existing pipeline now.\n"
                "Read docs/local-production-worker.md and follow it.\n"
                "Allowed run ID: " + run["id"] + "\nWorker ID: " + self.worker_id + "\n"
                "Only this already-requested run is authorized. Never create/restart a run, edit source/config, "
                "approve content, publish, buy credits, increase budgets or install tools. "
                "Complete exactly one pipeline stage in this invocation, then exit. The local runner immediately schedules the next stage. "
                "Use the exact worker ID above in worker-next. Do not print secrets or lease tokens.\n")

    def _block(self, run_id, message):
        with self.store.db() as db:
            run = db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone()
            if run and run["status"] == "running":
                db.execute("UPDATE production_runs SET status='blocked',pause_reason=?,updated_at=? WHERE id=?",
                           (message, datetime.now(timezone.utc).isoformat(), run_id))
                self.store._event(db, run_id, None, None, "worker.launch_failed", message, level="error")
        self._status(status="error", run_id=run_id, message=message)

    def _video_wait(self, cycle):
        if not cycle or cycle["stage_index"] != 4:
            return False
        with self.store.db() as db:
            for row in db.execute("SELECT status,input_json FROM video_jobs WHERE status NOT IN ('completed','failed','cancelled')"):
                if json.loads(row["input_json"]).get("production", {}).get("cycle_id") == cycle["id"]:
                    return True
        return False

    def _finished(self, run_id, returncode, error, retryable_error=None, committed_progress=False):
        # Reconcile the process's own run even if the user has already started
        # another one. Never leave a dead owner marked as actively producing.
        with self.store.db() as db:
            run = db.execute("SELECT * FROM production_runs WHERE id=?", (run_id,)).fetchone()
            cycle = db.execute("SELECT * FROM production_cycles WHERE run_id=? ORDER BY number DESC LIMIT 1", (run_id,)).fetchone()
        if not run:
            return
        if cycle and cycle["status"] == "running":
            if cycle["lease_owner"] != self.worker_id or self._video_wait(cycle):
                return
            if retryable_error and self.store.recover_interrupted_text_stage(cycle["id"], self.worker_id, retryable_error):
                return True
            # A dead model process may have submitted media. Preserve the lease
            # and results as uncertain instead of starting a duplicate call.
            self.store.worker_fail(cycle["id"], cycle["lease_token"], error or "제작 작업자가 단계 완료 기록 없이 종료되었습니다.", uncertain=True)
            return
        if run["status"] != "running":
            return
        if retryable_error and committed_progress and cycle and cycle["status"] in ("pending", "suspended", "completed", "failed"):
            # The stage was committed before the process lost its connection.
            # Continue from that result, without retrying the committed stage.
            with self.store.db() as db:
                self.store._event(db, run_id, cycle["id"], None, "worker.continuing_saved",
                                  "연결 종료 전에 저장한 단계 결과에서 다음 작업을 이어갑니다.", {"reason": retryable_error})
            return True
        if returncode or error or not cycle or cycle["status"] not in ("completed", "failed", "suspended", "pending", "cancelled"):
            self._block(run_id, error or "Codex 제작 작업자를 실행하지 못했습니다. 로그인·사용 한도를 확인한 뒤 재개해 주세요.")

    def _terminate_process(self, process):
        # Codex and its tool subprocesses share the new session created below.
        # Stopping only the parent can leave tools running after a user stop.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        # The parent may exit before a tool that ignores SIGTERM. Fence all
        # remaining children before permitting a retry of its stage. Reaped or
        # zombie-only groups need no signal (macOS may return EPERM for them).
        if self._group_alive(process.pid):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                if self._group_alive(process.pid):
                    raise RuntimeError("종료되지 않은 도구 프로세스가 있어 자동 재시도를 보류했습니다.")
            deadline = time.monotonic() + 5
            while self._group_alive(process.pid):
                if time.monotonic() >= deadline:
                    raise RuntimeError("도구 프로세스의 종료 확인이 지연되어 자동 재시도를 보류했습니다.")
                time.sleep(.05)

    @staticmethod
    def _group_alive(group_id):
        rows = subprocess.check_output(["ps", "-axo", "pgid=,stat="], text=True, timeout=5)
        return any(len(parts) == 2 and parts[0] == str(group_id) and not parts[1].startswith("Z")
                   for parts in (line.split() for line in rows.splitlines()))

    def _recover_abandoned(self, run, cycle):
        # Called only while this supervisor owns the inherited worker.lock.
        # Any still-running Codex parent retains that lock across server exit.
        if not run or not cycle or run["status"] != "blocked" or cycle["status"] != "uncertain":
            return False
        with self.store.db() as db:
            job = db.execute("SELECT error FROM jobs WHERE cycle_id=? AND status='uncertain'", (cycle["id"],)).fetchone()
        if not job:
            return False
        return bool(self.store.recover_interrupted_text_stage(cycle["id"], cycle["lease_owner"], job["error"], abandoned=True))

    def _run_once(self, run, lock):
        stamp = uuid.uuid4().hex[:12]
        log_path = self.directory / (run["id"] + "-" + stamp + ".jsonl")
        stderr_path = log_path.with_suffix(".stderr")
        command = self._command()
        self._status(status="starting", run_id=run["id"], thread_id=None, retry_after=None, single_stage=True, message="AI 제작 작업자를 시작하고 있습니다.")
        with self.store.db() as db:
            current = db.execute("SELECT status FROM production_runs WHERE id=?", (run["id"],)).fetchone()
            if not current or current["status"] != "running":
                return
            before = db.execute("SELECT COALESCE(MAX(id),0) FROM production_events WHERE run_id=?", (run["id"],)).fetchone()[0]
            self.store._event(db, run["id"], None, None, "worker.launching", "시작 요청에 따라 로컬 AI 제작 작업자를 실행합니다.", {"worker_id": self.worker_id})
        self._status(stage_event_cursor=before)
        failure = {"fatal": None, "network_since": None, "network_error": None}
        retryable_error = None
        log_fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        err_fd = os.open(str(stderr_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(log_fd, "w") as log, os.fdopen(err_fd, "w") as stderr:
            process = self.process_factory(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=stderr, text=True, cwd=str(self.store.root),
                                           start_new_session=True, pass_fds=(lock.fileno(),))
            process.stdin.write(self._prompt(run))
            process.stdin.close()
            self._status(process_id=process.pid)

            def read_events():
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("type") == "thread.started":
                        self.status.update(status="running", thread_id=event.get("thread_id"), message="AI 제작 작업자가 요청을 처리하고 있습니다.")
                    if event.get("type") in ("error", "turn.failed"):
                        # Raw events stay private; never expose prompts/tokens.
                        kind, message = classify_worker_error(event)
                        if kind == "network":
                            if failure["network_since"] is None:
                                failure["network_since"] = time.monotonic()
                            failure["network_error"] = message
                        else:
                            failure["fatal"] = message
                    elif event.get("type") in ("item.started", "item.completed", "turn.completed"):
                        # Successful traffic supersedes a transient reconnect;
                        # do not block a completed stage on an old warning.
                        failure["network_since"] = None
                        failure["network_error"] = None

            reader = threading.Thread(target=read_events, daemon=True)
            reader.start()
            started = time.monotonic()
            last_ping = 0
            while process.poll() is None:
                current, cycle = self._snapshot()
                if not current or current["id"] != run["id"] or current["status"] in ("stopped", "completed"):
                    self._status(status="stopping", message="종료 요청에 따라 AI 작업자를 정리하고 있습니다.")
                    self._terminate_process(process)
                    break
                if current["status"] == "paused":
                    self._status(status="paused", message="일시정지 중입니다. 진행 중인 단계 결과를 보존한 뒤 다음 단계는 시작하지 않습니다.")
                self._status()
                if time.monotonic() - last_ping >= 20:
                    if cycle and cycle["status"] == "running" and cycle["lease_owner"] == self.worker_id:
                        self.store.worker_ping(cycle["id"], cycle["lease_token"])
                    last_ping = time.monotonic()
                if failure["fatal"]:
                    self._terminate_process(process)
                    break
                if failure["network_since"] is not None and time.monotonic() - failure["network_since"] > self.network_grace_seconds:
                    retryable_error = NETWORK_MESSAGE
                    self._terminate_process(process)
                    break
                if time.monotonic() - started > self.max_stage_seconds:
                    retryable_error = TIMEOUT_MESSAGE
                    self._terminate_process(process)
                    break
                if self.stop.wait(self.poll_seconds):
                    # The child inherits the lock and completes/checkpoints its
                    # current cycle. A replacement server cannot duplicate it.
                    process.wait()
                    break
            process.wait()
            reader.join(timeout=5)
            process.stdout.close()
        error = failure["fatal"] or retryable_error or failure["network_error"]
        retryable_error = None if failure["fatal"] else retryable_error or failure["network_error"]
        if retryable_error:
            self._terminate_process(process)
        with self.store.db() as db:
            progress = db.execute("SELECT 1 FROM production_events WHERE run_id=? AND id>? AND event IN ('stage.completed','stage.failed','stage.checkpoint','quality.repair','media.video.queued','media.video.running')", (run["id"], before)).fetchone()
        recovered = self._finished(run["id"], process.returncode, error, retryable_error, bool(progress))
        self._status(process_id=None)
        current, cycle = self._snapshot()
        if not recovered and current and current["id"] == run["id"] and current["status"] == "running" and not progress and not (cycle and cycle["status"] == "running"):
            self._block(run["id"], "AI 작업자가 제작 결과를 남기지 않아 반복 호출을 중지했습니다. 진단 기록을 확인한 뒤 재개해 주세요.")

    def work(self):
        with (self.directory / "worker.lock").open("a") as lock:
            # Another server or an inherited child owns the queue. Keep trying
            # so a second local server can take over after a restart.
            while not self.stop.is_set():
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    self.stop.wait(self.poll_seconds)
            else:
                return
            try:
                while not self.stop.is_set():
                    run = None
                    try:
                        self._status()
                        run, cycle = self._snapshot()
                        if self._recover_abandoned(run, cycle):
                            run, cycle = self._snapshot()
                        if self._runnable(run, cycle):
                            self._run_once(run, lock)
                        else:
                            retry_after = cycle.get("retry_after") if cycle and cycle["status"] == "pending" else None
                            self._status(status="idle", run_id=run["id"] if run else None, retry_after=retry_after,
                                         message="네트워크·시간 초과 오류를 복구했습니다. 재시도 대기 중입니다." if retry_after else "제작 요청 또는 진행 중인 단계의 결과를 기다리고 있습니다.")
                    except Exception as exc:
                        if run:
                            message = str(exc) if isinstance(exc, RuntimeError) else "로컬 AI 작업자를 시작하지 못했습니다. 실행 환경을 확인한 뒤 재개해 주세요."
                            self._block(run["id"], message)
                    self.wake.wait(self.poll_seconds)
                    self.wake.clear()
            finally:
                self._status(status="stopped", message="로컬 제작 작업자가 종료되었습니다.")
