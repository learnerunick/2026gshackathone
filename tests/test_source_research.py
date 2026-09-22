"""Automatic GS source research contracts, with isolated storage and no network."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "apps/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location("boca_source_research_server", BACKEND / "server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Store, Problem = module.Store, module.Problem


class SourceResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "config", self.root / "config")
        self.current = datetime.now(timezone.utc)
        config_path = self.root / "config/overnight.json"
        config = json.loads(config_path.read_text())
        config["ai_quality_review_enabled"] = True  # Legacy seven-stage policy.
        config.update(specialist_agents_enabled=False, start_at=(self.current - timedelta(minutes=1)).isoformat(),
                      generation_end_at=(self.current + timedelta(hours=2)).isoformat(),
                      media_mode="images")
        config_path.write_text(json.dumps(config))
        (self.root / "fixture.png").write_bytes(b"source-research-fixture-image")
        self.store = Store(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def start(self):
        self.run = self.store.start_run({"media_mode": "images"})
        claim = self.store.worker_next("source-research-fixture-worker")
        self.assertTrue(claim["should_work"], claim)
        self.assertEqual("sources", claim["job"]["stage"])
        return claim

    def database_snapshot(self):
        with sqlite3.connect(str(self.store.db_path)) as db:
            return tuple(db.iterdump())

    def source_rows(self):
        with sqlite3.connect(str(self.store.db_path)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM source_materials ORDER BY id")]

    def manual_source(self, **changes):
        body = {"affiliate": "GS SHOP", "title": "현업이 저장한 소재", "url": "https://www.gsshop.com/fixture-manual",
                "verified_at": (self.current - timedelta(minutes=5)).isoformat(),
                "expires_at": (self.current + timedelta(days=2)).isoformat(),
                "claims": ["수동으로 검토한 사실"], "visibility": "internal"}
        body.update(changes)
        return self.store.upsert_source(body)

    def material(self, **changes):
        claim = "공식 페이지에 소개된 생활 소품 자료"
        body = {"affiliate": "GS SHOP", "title": "공식 생활 소품 자료",
                "url": "https://www.gsshop.com/fixture-source",
                "verified_at": (self.current - timedelta(minutes=1)).isoformat(),
                "expires_at": (self.current + timedelta(days=2)).isoformat(),
                "claims": [claim], "evidence": [{"claim": claim, "excerpt": "검증용 페이지 본문: " + claim}],
                "material_type": "product", "visibility": "internal"}
        body.update(changes)
        return body

    def batch(self, materials=None, **changes):
        body = {"queries": [{"affiliate": "GS SHOP", "query": "site:gsshop.com 생활 소품 공식 자료"}],
                "materials": materials if materials is not None else [self.material()], "rejected": [],
                "decision_summary": "직접 확인한 공식 자료만 생활 이야기의 참고 정보로 사용합니다."}
        body.update(changes)
        return body

    def research(self, claim, body=None, token=None):
        return self.store.worker_sources(claim["cycle"]["id"], token or claim["lease_token"],
                                         body if body is not None else self.batch())

    def complete_sources(self, claim, receipt):
        return self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"],
                                          {"research_id": receipt["research_id"], "source_ids": receipt["source_ids"],
                                           "decision_summary": "검증한 공식 출처를 다음 기획에 전달합니다."})

    def finish_cycle(self, claim, receipt):
        self.complete_sources(claim, receipt)
        number = claim["cycle"]["number"]
        results = {"planning": {"title": "자료 조사 일상 %d" % number, "topic_key": "research-%d" % number,
                                "source_ids": receipt["source_ids"]},
                   "storyboard": {"cards": [{"scene": "집의 작은 선반을 정돈하는 장면"}]},
                   "copy": {"caption": module.DISCLOSURE, "hashtags": []},
                   "images": {"media": ["fixture.png"]}, "quality": {"passed": True}}
        for stage in ("planning", "storyboard", "copy", "images", "quality", "register"):
            current = self.store.worker_next("source-research-fixture-worker")
            self.assertTrue(current["should_work"], current)
            self.assertEqual(stage, current["job"]["stage"])
            if stage == "register":
                content = self.store.ingest({"id": current["cycle"]["content_id"], "title": "자료 조사 일상 %d" % number,
                                             "topic_key": "research-%d" % number,
                                             "persona_id": self.run["persona_id"], "persona_version": self.run["persona_version"],
                                             "caption": module.DISCLOSURE, "sources": [],
                                             "cards": [{"media": "fixture.png", "alt": "검증용 이미지"}]})
                result = {"content_id": content["id"], "version": content["version"]}
            else:
                result = results[stage]
            self.store.worker_complete(current["cycle"]["id"], current["lease_token"], result)

    def test_new_run_requires_research_and_start_body_cannot_disable_worker_contract(self):
        run = self.store.start_run({"media_mode": "images", "source_research_enabled": False})
        self.assertIs(True, run["settings"]["source_research_enabled"])
        claim = self.store.worker_next("source-research-fixture-worker")
        research = json.loads(claim["job"]["input_json"])["source_research"]
        self.assertIs(True, research["enabled"])
        self.assertEqual("codex-web", research["provider"])
        self.assertEqual("worker", research["verified_by"])
        self.assertEqual({"GS리테일", "GS SHOP", "GS건설", "GS칼텍스", "파르나스 호텔"}, set(research["affiliates"]))
        self.assertEqual(["GS리테일", "GS SHOP", "GS건설", "GS칼텍스", "파르나스 호텔"],
                         self.store.config()["brand_targets"])
        self.assertIn("gsshop.com", research["affiliates"]["GS SHOP"])
        self.assertEqual("GSSHOP", research["affiliate_labels"]["GS SHOP"])
        self.assertEqual("GS리테일(편의점,수퍼)", research["affiliate_labels"]["GS리테일"])
        self.assertIn("GS25", research["affiliate_scopes"]["GS리테일"])
        self.assertIn("GS THE FRESH", research["affiliate_scopes"]["GS리테일"])
        self.assertEqual((8, 12, 24), (research["max_queries"], research["max_materials"], research["max_rejected"]))
        self.assertEqual([], research["existing_sources"])
        self.assertTrue(research["instructions"])

    def test_sources_completion_requires_matching_saved_receipt_and_server_provenance(self):
        claim = self.start()
        for result in ({"source_ids": []}, {"research_id": "invented-receipt", "source_ids": []}):
            with self.subTest(result=result), self.assertRaises(Problem):
                self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"], result)
        receipt = self.research(claim)
        with self.assertRaises(Problem):
            self.store.worker_complete(claim["cycle"]["id"], claim["lease_token"],
                                       {"research_id": receipt["research_id"], "source_ids": ["invented-source"]})
        completed = self.complete_sources(claim, receipt)
        saved = completed["cycle"]["result"]["sources"]["source_research"]
        self.assertEqual(receipt["research_id"], saved["research_id"])
        self.assertEqual({"provider": "codex-web", "verified_by": "worker", "web_verified": True}, saved["provenance"])
        self.assertEqual(receipt["source_ids"], saved["source_ids"])

    def test_invalid_expired_and_other_stage_leases_cannot_register_research(self):
        claim = self.start()
        before = self.database_snapshot()
        with self.assertRaises(Problem):
            self.research(claim, token="wrong-fixture-token")
        self.assertEqual(before, self.database_snapshot())
        with self.store.db() as db:
            db.execute("UPDATE production_cycles SET lease_expires_at=? WHERE id=?",
                       ((self.current - timedelta(minutes=1)).isoformat(), claim["cycle"]["id"]))
        before = self.database_snapshot()
        with self.assertRaises(Problem):
            self.research(claim)
        self.assertEqual(before, self.database_snapshot())
        with self.store.db() as db:
            db.execute("UPDATE production_cycles SET lease_expires_at=? WHERE id=?",
                       ((self.current + timedelta(minutes=10)).isoformat(), claim["cycle"]["id"]))
        receipt = self.research(claim)
        self.complete_sources(claim, receipt)
        planning = self.store.worker_next("source-research-fixture-worker")
        self.assertEqual("planning", planning["job"]["stage"])
        with self.assertRaises(Problem):
            self.research(planning)

    def test_paused_stopped_and_deadline_runs_cannot_register_new_research(self):
        claim = self.start()
        self.store.control_run(self.run["id"], "pause")
        with self.assertRaises(Problem):
            self.research(claim)
        self.assertEqual([], self.source_rows())
        self.store.control_run(self.run["id"], "resume")
        with self.store.db() as db:
            db.execute("UPDATE production_runs SET end_at=? WHERE id=?",
                       ((self.current - timedelta(minutes=1)).isoformat(), self.run["id"]))
        with self.assertRaises(Problem):
            self.research(claim)
        self.assertEqual([], self.source_rows())
        with self.store.db() as db:
            db.execute("UPDATE production_runs SET end_at=?,status='running' WHERE id=?",
                       ((self.current + timedelta(hours=1)).isoformat(), self.run["id"]))
        self.store.control_run(self.run["id"], "stop")
        with self.assertRaises(Problem):
            self.research(claim)
        self.assertEqual([], self.source_rows())

    def test_only_official_https_affiliate_urls_pass_without_spoofing_or_ports(self):
        claim = self.start()
        invalid = ("https://gsshop.com.evil.example/item", "https://evil-gsshop.com/item",
                   "https://name@gsshop.com/item", "https://gsshop.com@evil.example/item",
                   "http://www.gsshop.com/item", "https://www.gsshop.com:443/item",
                   "https://www.gsshop.com:8443/item", "https://www.gsretail.com/item")
        for url in invalid:
            with self.subTest(url=url):
                before = self.database_snapshot()
                with self.assertRaises(Problem):
                    self.research(claim, self.batch([self.material(url=url)]))
                self.assertEqual(before, self.database_snapshot())
        materials = [self.material(affiliate=affiliate, url=url) for affiliate, url in (
            ("GS칼텍스", "https://gscaltexmediahub.com/fixture-source"),
            ("GS건설", "https://www.gsenc.com/fixture-source"),
            ("GS리테일", "https://www.gsretail.com/fixture-source"),
            ("GS SHOP", "https://m.gsshop.com/fixture-source"),
            ("파르나스 호텔", "https://www.parnashotel.com/fixture-source"))]
        queries = [{"affiliate": entry["affiliate"], "query": entry["affiliate"] + " 공식 생활 자료"} for entry in materials]
        receipt = self.research(claim, self.batch(materials, queries=queries))
        self.assertEqual(5, receipt["added_count"])
        self.assertEqual(5, len(receipt["source_ids"]))

    def test_parnas_domains_reject_lookalikes_and_other_company_urls(self):
        for url in ("https://www.parnashotel.com/hotel/introduction",
                    "https://www.parnashoteljeju.com/ko/main.do",
                    "https://seoul.intercontinental.com/eshop"):
            with self.subTest(url=url):
                self.store._canonical_research_url(url, "파르나스 호텔")
        for url in ("https://parnashotel.com.evil.example/item", "https://evil-parnashotel.com/item",
                    "https://www.gsshop.com/item", "https://other.intercontinental.com/item"):
            with self.subTest(url=url), self.assertRaises(Problem):
                self.store._canonical_research_url(url, "파르나스 호텔")

    def test_display_alias_reuses_legacy_source_and_keeps_shop_visibility_guard(self):
        manual = self.manual_source(claims=[self.material()["claims"][0]])
        claim = self.start()
        material = self.material(affiliate="GSSHOP", url=manual["url"])
        queries = [{"affiliate": "GSSHOP", "query": "site:gsshop.com 생활 자료"}]
        receipt = self.research(claim, self.batch([material], queries=queries))
        self.assertEqual([manual["id"]], receipt["source_ids"])
        self.assertEqual("GS SHOP", receipt["materials"][0]["affiliate"])
        self.assertEqual(1, len(self.source_rows()))
        material["visibility"] = "explicit"
        with self.assertRaises(Problem):
            self.store._normalize_research(self.batch([material], queries=queries))

    def test_manual_sources_accept_new_target_and_display_aliases(self):
        for index, (label, stored) in enumerate((
                ("파르나스 호텔", "파르나스 호텔"), ("GSSHOP", "GS SHOP"),
                ("GS리테일(편의점,수퍼)", "GS리테일"))):
            with self.subTest(affiliate=label):
                source = self.manual_source(affiliate=label, url="https://example.com/manual-%d" % index)
                self.assertEqual(stored, source["affiliate"])

    def test_canonical_duplicates_and_repeated_receipts_do_not_repeat_writes(self):
        claim = self.start()
        body = self.batch([
            self.material(url="https://www.gsshop.com/fixture-product?prdCd=123&utm_source=fixture#details"),
            self.material(url="https://gsshop.com/fixture-product?fbclid=fixture&prdCd=123"),
            self.material(url="https://www.gsshop.com/fixture-product?prdCd=456"),
        ])
        first = self.research(claim, body)
        self.assertEqual(2, first["added_count"])
        self.assertEqual(2, len(first["source_ids"]))
        self.assertEqual(2, len(self.source_rows()))
        urls = {row["url"] for row in self.source_rows()}
        self.assertEqual({"https://gsshop.com/fixture-product?prdCd=123", "https://gsshop.com/fixture-product?prdCd=456"}, urls)
        before = self.database_snapshot()
        duplicate = self.research(claim, deepcopy(body))
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(first["research_id"], duplicate["research_id"])
        self.assertEqual(before, self.database_snapshot())
        changed = deepcopy(body)
        changed["decision_summary"] = "같은 순환에 다른 조사 기록을 덮어쓰려는 요청"
        with self.assertRaises(Problem) as caught:
            self.research(claim, changed)
        self.assertEqual(409, caught.exception.status)
        self.assertEqual(before, self.database_snapshot())

    def test_manual_sources_are_preserved_and_claim_conflicts_are_not_overwritten(self):
        manual = self.manual_source()
        conflict = self.manual_source(url="https://www.gsshop.com/fixture-conflict", claims=["사람이 확인한 별도 사실"])
        late = self.manual_source(url="https://www.gsshop.com/fixture-edited-during-research")
        claim = self.start()
        self.manual_source(url=late["url"], title="조사 도중 사람이 수정한 제목")
        original = self.source_rows()
        matching_claim = manual["claims"][0]
        matching = self.material(url=manual["url"], title="자동 조사가 바꾸려는 수동 제목", claims=[matching_claim],
                                 evidence=[{"claim": matching_claim, "excerpt": matching_claim}])
        changed = self.material(url=conflict["url"], claims=["원래 기록과 다른 AI의 주장"],
                                evidence=[{"claim": "원래 기록과 다른 AI의 주장", "excerpt": "원래 기록과 다른 AI의 주장"}])
        late_copy = self.material(url=late["url"], claims=[matching_claim],
                                  evidence=[{"claim": matching_claim, "excerpt": matching_claim}])
        receipt = self.research(claim, self.batch([matching, changed, late_copy]))
        self.assertEqual([manual["id"]], receipt["source_ids"])
        self.assertEqual(1, receipt["reused_count"])
        self.assertEqual(2, receipt["skipped_count"])
        self.assertEqual(original, self.source_rows())

    def test_batches_are_bounded_and_invalid_batches_are_atomic(self):
        claim = self.start()
        oversized = [self.batch([self.material(url="https://gsshop.com/fixture-%d" % number) for number in range(13)]),
                     self.batch(queries=[{"affiliate": "GS SHOP", "query": "검증 검색 %d" % number} for number in range(9)]),
                     self.batch(rejected=[{"url": "https://example.com/%d" % number, "reason": "공식 출처 아님"} for number in range(25)]),
                     self.batch([self.material(), self.material(url="https://outside.example/not-official")])]
        before = self.database_snapshot()
        for body in oversized:
            with self.subTest(size=len(body["materials"])), self.assertRaises(Problem):
                self.research(claim, body)
            self.assertEqual(before, self.database_snapshot())
        self.assertEqual(1, self.research(claim)["added_count"])

    def test_exact_queries_evidence_and_provenance_are_saved_to_log_and_stage_artifacts(self):
        claim = self.start()
        body = self.batch(rejected=[{"url": "https://example.com/fixture-unsupported", "reason": "공식 계열사 출처가 아니어서 제외"}])
        receipt = self.research(claim, body)
        self.complete_sources(claim, receipt)
        stage = self.store.read_stage_result(self.run["id"], claim["cycle"]["id"], "sources")
        saved = stage["result"]["source_research"]
        self.assertEqual(body["queries"], saved["queries"])
        self.assertEqual(body["rejected"], saved["rejected"])
        self.assertEqual(1, saved["rejected_count"])
        self.assertEqual("codex-web", saved["provenance"]["provider"])
        self.assertEqual("worker", saved["provenance"]["verified_by"])
        serialized = json.dumps(stage, ensure_ascii=False)
        for text in (body["queries"][0]["query"], body["materials"][0]["evidence"][0]["excerpt"],
                     body["decision_summary"], "공식 계열사 출처가 아니어서 제외"):
            self.assertIn(text, serialized)
        log, _, _ = self.store.export_log(self.run["id"], "jsonl")
        log_text = log.decode()
        self.assertIn(body["queries"][0]["query"], log_text)
        self.assertIn(body["materials"][0]["evidence"][0]["excerpt"], log_text)
        self.assertIn(receipt["research_id"], log_text)
        self.assertNotIn(claim["lease_token"], log_text)

    def test_expired_materials_never_become_usable_and_empty_results_require_explicit_reason(self):
        claim = self.start()
        body = self.batch([self.material(expires_at=(self.current - timedelta(hours=1)).isoformat())])
        with self.assertRaises(Problem):
            self.research(claim, body)
        self.assertEqual([], self.source_rows())
        body["empty_reason"] = "확인한 자료의 행사 유효기간이 지나 사용 가능한 정보가 없습니다."
        receipt = self.research(claim, body)
        self.assertEqual("empty", receipt["outcome"])
        self.assertEqual([], receipt["source_ids"])
        self.assertEqual(1, receipt["skipped_count"])
        self.assertEqual(body["empty_reason"], receipt["empty_reason"])
        self.assertEqual([], self.source_rows())
        self.complete_sources(claim, receipt)

    def test_fresh_verification_evidence_and_material_validity_are_required(self):
        claim = self.start()
        invalid = [self.material(verified_at=(self.current - timedelta(days=2)).isoformat()),
                   self.material(verified_at=(self.current + timedelta(hours=1)).isoformat()),
                   self.material(material_type="promotion", expires_at=None, validity_note="유효기간을 모름"),
                   self.material(expires_at=None), self.material(evidence=[])]
        before = self.database_snapshot()
        for material in invalid:
            with self.subTest(material=material), self.assertRaises(Problem):
                self.research(claim, self.batch([material]))
            self.assertEqual(before, self.database_snapshot())
        receipt = self.research(claim, self.batch([self.material(material_type="brand", expires_at=None,
                                                                  validity_note="공식 브랜드 소개이며 기간 한정 혜택을 포함하지 않습니다.")]))
        self.assertEqual("accepted", receipt["outcome"])

    def test_next_cycle_receives_existing_sources_and_previous_research_provenance(self):
        manual = self.manual_source()
        claim = self.start()
        first_input = json.loads(claim["job"]["input_json"])["source_research"]
        self.assertIn(manual["id"], {source["id"] for source in first_input["existing_sources"]})
        receipt = self.research(claim)
        self.finish_cycle(claim, receipt)
        following = self.store.worker_next("source-research-fixture-worker")
        self.assertEqual("sources", following["job"]["stage"])
        self.assertEqual(2, following["cycle"]["number"])
        research_input = json.loads(following["job"]["input_json"])["source_research"]
        sources = research_input["existing_sources"]
        by_id = {source["id"]: source for source in sources}
        self.assertTrue(set(receipt["source_ids"]).issubset(by_id))
        self.assertEqual("manual", by_id[manual["id"]]["origin"])
        automatic = by_id[receipt["source_ids"][0]]
        self.assertEqual("codex-web", automatic["provenance"]["provider"])
        self.assertTrue(automatic["source_version"] >= 1)
        recent = next(row for row in research_input["recent_usage"] if row["cycle_id"] == claim["cycle"]["id"])
        self.assertEqual(self.run["id"], recent["run_id"])
        self.assertEqual("completed", recent["status"])
        self.assertEqual("research-1", recent["topic_key"])
        self.assertEqual(receipt["source_ids"], recent["source_ids"])


if __name__ == "__main__":
    unittest.main()
