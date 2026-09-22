"""Optional per-run feed targets; fixtures never call generators or publish."""
from concurrent.futures import ThreadPoolExecutor
import json
import unittest

import test_automation as fixtures


class ProductionLimitTests(unittest.TestCase):
    # Reuse the isolated fixture helpers without inheriting unrelated tests.
    setUp = fixtures.AutomationTests.setUp
    tearDown = fixtures.AutomationTests.tearDown
    claim = fixtures.AutomationTests.claim
    complete = fixtures.AutomationTests.complete
    result_for = fixtures.AutomationTests.result_for
    finish_cycle = fixtures.AutomationTests.finish_cycle

    def payload(self, claim):
        payload = fixtures.AutomationTests.payload(self, claim)
        payload["cards"] *= 5
        return payload

    def run_state(self):
        return self.store.automation_state()["run"]

    def test_reject_invalid_targets_before_creating_run(self):
        for invalid in (True, False, 0, -1, 1001, 1.0, 1.5, "2", "", [], {}):
            with self.subTest(target=invalid), self.assertRaises(fixtures.Problem):
                self.store.start_run({"stop_after_posts": invalid})
        self.assertIsNone(self.run_state())
        accepted = self.store.start_run({"stop_after_posts": 1000})
        self.assertEqual(1000, accepted["settings"]["stop_after_posts"])

    def test_target_counts_registered_feeds_not_cards_or_manual_contents(self):
        self.store.start_run({"stop_after_posts": 2})
        first = self.claim("sources")
        manual = self.payload(first)
        manual.update(id="manual-content", title="수동 피드", topic_key="manual-topic")
        self.store.ingest(manual)
        self.assertEqual(0, self.run_state()["completed_count"])
        self.complete(first)
        for stage in fixtures.STAGES[1:]:
            self.complete(self.claim(stage))
        self.assertEqual("running", self.run_state()["status"])
        self.assertEqual(1, self.run_state()["completed_count"])
        self.finish_cycle()
        run = self.run_state()
        self.assertEqual("completed", run["status"])
        self.assertEqual(2, run["completed_count"])
        self.assertEqual(2, run["cycle_number"])
        self.assertIsNone(run["current_stage"])
        self.assertEqual("목표 제작 건수 달성", run["pause_reason"])
        self.assertFalse(self.store.worker_next("next-worker")["should_work"])
        contents = self.store.state()["contents"]
        self.assertEqual(3, len(contents))
        self.assertTrue(all(content["status"] == "ready" and content["publication"] is None for content in contents))
        events = [event for event in self.store.logs(run_id=run["id"]) if event["event"] == "run.completed"]
        self.assertEqual(1, len(events))
        self.assertEqual({"reason": "target_count_reached", "stop_after_posts": 2, "completed_count": 2}, events[0]["detail"])

    def test_omitted_and_legacy_targets_remain_unlimited(self):
        run = self.store.start_run({})
        self.assertIsNone(run["settings"]["stop_after_posts"])
        for _ in range(2):
            self.finish_cycle()
        self.assertEqual("running", self.run_state()["status"])
        # Existing runs predating the option have no key and remain unlimited.
        with self.store.db() as db:
            settings = dict(run["settings"])
            settings.pop("stop_after_posts")
            db.execute("UPDATE production_runs SET settings_json=? WHERE id=?", (json.dumps(settings), run["id"]))
        self.store = fixtures.Store(self.root)
        self.finish_cycle()
        self.assertEqual("running", self.run_state()["status"])
        self.assertEqual(3, self.run_state()["completed_count"])
        self.assertIsNone(self.store.start_run({"stop_after_posts": None})["settings"].get("stop_after_posts"))

    def test_target_is_frozen_on_repeated_start_and_config_change(self):
        run = self.store.start_run({"stop_after_posts": 2})
        self.assertEqual(run["id"], self.store.start_run({})["id"])
        self.assertEqual(run["id"], self.store.start_run({"stop_after_posts": 2})["id"])
        for changed in (None, 1, 3):
            with self.subTest(target=changed), self.assertRaises(fixtures.Problem):
                self.store.start_run({"stop_after_posts": changed})
        config_path = self.root / "config/overnight.json"
        config = json.loads(config_path.read_text())
        config["stop_after_posts"] = 1
        config_path.write_text(json.dumps(config))
        self.store = fixtures.Store(self.root)
        self.finish_cycle()
        self.assertEqual("running", self.run_state()["status"])
        self.finish_cycle()
        self.assertEqual(2, self.run_state()["completed_count"])
        self.assertEqual("completed", self.run_state()["status"])
        # A newly requested default run is unlimited even if an old config was edited.
        fresh = self.store.start_run({})
        self.assertIsNone(fresh["settings"]["stop_after_posts"])

    def test_failed_cycles_retries_and_pause_restart_do_not_consume_target(self):
        run = self.store.start_run({"stop_after_posts": 1})
        first = self.claim("sources")
        self.store.worker_fail(first["cycle"]["id"], first["lease_token"], "fixture retry", retryable=True)
        retried = self.claim("sources")
        self.assertEqual(first["cycle"]["id"], retried["cycle"]["id"])
        self.store.worker_fail(retried["cycle"]["id"], retried["lease_token"], "fixture failure", retryable=False)
        self.assertEqual(0, self.run_state()["completed_count"])
        self.assertEqual(1, self.run_state()["failed_count"])
        self.store.control_run(run["id"], "pause")
        self.store = fixtures.Store(self.root)
        self.assertFalse(self.store.worker_next("paused-worker")["should_work"])
        self.store.control_run(run["id"], "resume")
        self.finish_cycle()
        current = self.run_state()
        self.assertEqual("completed", current["status"])
        self.assertEqual(1, current["completed_count"])
        self.assertEqual(2, current["cycle_number"])
        self.store = fixtures.Store(self.root)
        with self.assertRaises(fixtures.Problem):
            self.store.control_run(run["id"], "resume")
        self.assertFalse(self.store.worker_next("restarted-worker")["should_work"])

    def test_concurrent_last_completion_and_next_claim_cannot_overshoot(self):
        self.store.start_run({"stop_after_posts": 1})
        for stage in fixtures.STAGES[:-1]:
            self.complete(self.claim(stage))
        final = self.claim("register")
        result = self.result_for(final)
        self.assertEqual(0, self.run_state()["completed_count"])
        self.assertFalse(self.store.worker_next("while-registering")["should_work"])
        with ThreadPoolExecutor(max_workers=4) as pool:
            completions = [pool.submit(self.complete, final, result) for _ in range(2)]
            claims = [pool.submit(self.store.worker_next, "competing-worker-%s" % index) for index in range(2)]
            completed = [future.result() for future in completions]
            self.assertTrue(all(not future.result()["should_work"] for future in claims))
        self.assertEqual([False, True], sorted(item["duplicate"] for item in completed))
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda index: self.store.worker_next("after-worker-%s" % index), range(8)))
        self.assertTrue(all(not claim["should_work"] for claim in claims))
        self.assertEqual(1, self.run_state()["completed_count"])
        self.assertEqual(1, self.run_state()["cycle_number"])
        self.assertEqual("completed", self.run_state()["status"])

    def test_refresh_restores_terminal_limit_before_new_cycle(self):
        run = self.store.start_run({"stop_after_posts": 1})
        self.finish_cycle()
        # Restore an old checkpoint with a committed success and stale run status.
        with self.store.db() as db:
            db.execute("UPDATE production_runs SET status='paused',pause_reason='checkpoint' WHERE id=?", (run["id"],))
            db.execute("DELETE FROM production_events WHERE run_id=? AND event='run.completed'", (run["id"],))
        self.store = fixtures.Store(self.root)
        self.assertFalse(self.store.worker_next("recovery-worker")["should_work"])
        self.assertEqual("completed", self.run_state()["status"])
        self.assertEqual(1, self.run_state()["cycle_number"])
        with self.assertRaises(fixtures.Problem):
            self.store.control_run(run["id"], "resume")
        events = [event for event in self.store.logs(run_id=run["id"]) if event["event"] == "run.completed"]
        self.assertEqual(1, len(events))

    def test_repaired_stages_receive_new_inputs_and_keep_old_results_only_in_history(self):
        run = self.store.start_run({"stop_after_posts": 1})
        for stage in fixtures.STAGES[:4]:
            self.complete(self.claim(stage))
        images = self.claim("images")
        self.store.worker_checkpoint(images["cycle"]["id"], images["lease_token"], {"completed_media": ["fixture.png"]})
        self.complete(images, external_job_id="previous-provider-job")
        quality = self.claim("quality")
        self.store.worker_repair(quality["cycle"]["id"], quality["lease_token"], "copy", ["문안 수정 후 이미지 재제작"])
        invalidated = self.store.read_stage_result(run["id"], images["cycle"]["id"], "images")
        self.assertEqual("pending", invalidated["status"])
        self.assertIsNone(invalidated["result"])
        self.assertIsNone(invalidated["checkpoint"])
        self.assertIsNone(invalidated["external_job_id"])
        self.assertIn("previous-provider-job", invalidated["external_job_ids"])
        self.assertIn("이전 결과를 이력에 보존", invalidated["summary"])
        self.assertEqual(1, len(invalidated["checkpoints"]))
        self.assertTrue(any(event["event"] == "stage.completed" and event["detail"]["result"]["media"] == ["fixture.png"]
                            for event in invalidated["events"]))
        copy = self.claim("copy")
        updated_copy = {"caption": "검수 의견을 반영한 새 문안. " + fixtures.module.DISCLOSURE, "hashtags": ["#새로운기록"]}
        self.complete(copy, updated_copy)
        revised_images = self.claim("images")
        self.assertEqual(updated_copy, json.loads(revised_images["job"]["input_json"])["previous_results"]["copy"])
        self.assertIsNone(revised_images["job"]["result_json"])
        self.assertIsNone(revised_images["job"]["external_job_id"])
        self.complete(revised_images)
        revised_quality = self.claim("quality")
        self.assertEqual(updated_copy, json.loads(revised_quality["job"]["input_json"])["previous_results"]["copy"])
        self.complete(revised_quality)
        self.complete(self.claim("register"))
        self.assertEqual("completed", self.run_state()["status"])
        self.assertEqual(1, self.run_state()["completed_count"])

    def test_default_source_and_specialist_contracts_complete_exactly_one_feed(self):
        config_path = self.root / "config/overnight.json"
        config = json.loads(config_path.read_text())
        config.update(specialist_agents_enabled=True, source_research_enabled=True)
        config_path.write_text(json.dumps(config))
        run = self.store.start_run({"stop_after_posts": 1})
        for stage in fixtures.STAGES:
            claim = self.claim(stage)
            role = json.loads(claim["job"]["input_json"])["specialist"]["role_id"]
            assignment = self.store.worker_agent(claim["cycle"]["id"], claim["lease_token"],
                                                  "/root/fixture_" + role, role)
            if stage == "sources":
                fact = "네트워크 호출 없이 검증하는 공식 출처 형식의 임시 소재"
                receipt = self.store.worker_sources(claim["cycle"]["id"], claim["lease_token"], {
                    "queries": [{"affiliate": "GS SHOP", "query": "site:gsshop.com 생활 소품"}],
                    "materials": [{"affiliate": "GS SHOP", "title": "통합 검증용 가상 소재",
                                   "url": "https://www.gsshop.com/fixture-production-limit",
                                   "verified_at": self.reference_time.isoformat(), "expires_at": None,
                                   "validity_note": "기간 한정 혜택 없는 테스트용 브랜드 정보",
                                   "material_type": "brand", "claims": [fact],
                                   "evidence": [{"claim": fact, "excerpt": fact}]}],
                    "rejected": [], "decision_summary": "임시 DB에서 수집 기록 계약만 검증합니다.",
                })
                self.source = next(source for source in self.store.automation_state()["sources"] if source["id"] in receipt["source_ids"])
                result = {"research_id": receipt["research_id"], "source_ids": receipt["source_ids"]}
            else:
                result = self.result_for(claim)
            result["specialist_assignment_id"] = assignment["assignment_id"]
            self.complete(claim, result)
        state = self.store.automation_state()
        self.assertEqual("completed", state["run"]["status"])
        self.assertEqual(1, state["run"]["completed_count"])
        self.assertEqual(1, state["run"]["cycle_number"])
        self.assertEqual(7, len([assignment for assignment in state["specialists"]["assignments"]
                                if assignment["run_id"] == run["id"] and assignment["status"] == "completed"]))
        self.assertFalse(self.store.worker_next("no-second-feed")["should_work"])
        content = self.store.state()["contents"][0]
        self.assertEqual("ready", content["status"])
        self.assertIsNone(content["publication"])

    def test_repair_clears_current_expert_attribution_but_preserves_history(self):
        config_path = self.root / "config/overnight.json"
        config = json.loads(config_path.read_text())
        config["specialist_agents_enabled"] = True
        config_path.write_text(json.dumps(config))
        run = self.store.start_run({"stop_after_posts": 1})

        def assign(claim):
            role = json.loads(claim["job"]["input_json"])["specialist"]["role_id"]
            return self.store.worker_agent(claim["cycle"]["id"], claim["lease_token"], "/root/fixture_" + role, role)

        prior = {}
        for stage in fixtures.STAGES[:-2]:
            claim = self.claim(stage)
            prior[stage] = assign(claim)
            result = self.result_for(claim)
            result["specialist_assignment_id"] = prior[stage]["assignment_id"]
            self.complete(claim, result)
        quality = self.claim("quality")
        prior["quality"] = assign(quality)
        cycle_id = quality["cycle"]["id"]
        self.store.worker_repair(cycle_id, quality["lease_token"], "copy", ["문안 수정 요청"])
        for stage in ("copy", "images", "quality"):
            invalidated = self.store.read_stage_result(run["id"], cycle_id, stage)
            self.assertIsNone(invalidated["specialist_assignment"])
            self.assertEqual([prior[stage]["assignment_id"]], [item["assignment_id"] for item in invalidated["specialist_assignments"]])
            self.assertEqual("completed", invalidated["specialist_assignments"][0]["status"])
        unchanged = self.store.read_stage_result(run["id"], cycle_id, "storyboard")
        self.assertEqual(prior["storyboard"]["assignment_id"], unchanged["specialist_assignment"]["assignment_id"])
        replacement = self.claim("copy")
        self.assertIsNone(self.store.read_stage_result(run["id"], cycle_id, "copy")["specialist_assignment"])
        assigned = assign(replacement)
        current = self.store.read_stage_result(run["id"], cycle_id, "copy")
        self.assertEqual(assigned["assignment_id"], current["specialist_assignment"]["assignment_id"])
        self.assertEqual("assigned", current["specialist_assignment"]["status"])
        self.assertEqual(2, len(current["specialist_assignments"]))
        result = self.result_for(replacement)
        result["specialist_assignment_id"] = assigned["assignment_id"]
        self.complete(replacement, result)
        current = self.store.read_stage_result(run["id"], cycle_id, "copy")
        self.assertEqual(assigned["assignment_id"], current["specialist_assignment"]["assignment_id"])
        self.assertEqual("completed", current["specialist_assignment"]["status"])


if __name__ == "__main__":
    unittest.main()
