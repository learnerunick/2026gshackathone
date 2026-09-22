"""Worker-attested official source research. This module never fetches a URL."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


AFFILIATE_DOMAINS = {
    "GS리테일": ["gsretail.com"],
    "GS SHOP": ["gsshop.com"],
    "GS건설": ["gsenc.com", "xi.co.kr"],
    "GS칼텍스": ["gscaltex.com", "gscaltexmediahub.com"],
    "파르나스 호텔": ["parnashotel.com", "parnashoteljeju.com", "seoul.intercontinental.com"],
}
AFFILIATE_LABELS = {"GS리테일": "GS리테일(편의점,수퍼)", "GS SHOP": "GSSHOP",
                    "GS건설": "GS건설", "GS칼텍스": "GS칼텍스", "파르나스 호텔": "파르나스 호텔"}
AFFILIATE_SCOPES = {
    "GS리테일": "편의점 GS25와 수퍼 GS THE FRESH의 상품·서비스·공식 소식만 수집합니다.",
    "GS SHOP": "GSSHOP에서 취급하는 브랜드·상품·공식 소식을 내부 출처로 수집합니다.",
    "GS건설": "GS건설의 주거·공간·브랜드·서비스 공식 자료를 수집합니다.",
    "GS칼텍스": "GS칼텍스의 에너지·이동·생활 관련 브랜드·서비스 공식 자료를 수집합니다.",
    "파르나스 호텔": "파르나스 호텔의 숙박·다이닝·휴식·라이프스타일 상품과 공식 소식을 수집합니다.",
}


def normalize_affiliate(value):
    # Keep existing source/brief identifiers; display names can also be submitted.
    if not isinstance(value, str):
        return value
    return {"GSSHOP": "GS SHOP", "GS리테일(편의점,수퍼)": "GS리테일"}.get(value, value)


PROVENANCE = {"provider": "codex-web", "verified_by": "worker", "web_verified": True}
MAX_QUERIES, MAX_MATERIALS, MAX_REJECTED = 8, 12, 24


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def now():
    return datetime.now(timezone.utc).isoformat()


class SourceResearchStore:
    def init_source_research(self, db):
        db.execute("""CREATE TABLE IF NOT EXISTS source_research_receipts (
            id TEXT PRIMARY KEY,run_id TEXT NOT NULL,cycle_id TEXT NOT NULL UNIQUE,
            input_hash TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL
        )""")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(source_materials)")}
        for name, declaration in [("origin", "TEXT NOT NULL DEFAULT 'manual'"),
                                  ("discovery_json", "TEXT NOT NULL DEFAULT '{}'"),
                                  ("source_version", "INTEGER NOT NULL DEFAULT 1")]:
            if name not in columns:
                db.execute("ALTER TABLE source_materials ADD COLUMN " + name + " " + declaration)

    def source_research_policy(self):
        return {"provider": "codex-web", "verified_by": "worker", "affiliates": AFFILIATE_DOMAINS,
                "affiliate_labels": AFFILIATE_LABELS, "affiliate_scopes": AFFILIATE_SCOPES,
                "max_queries": MAX_QUERIES, "max_materials": MAX_MATERIALS, "max_rejected": MAX_REJECTED,
                "max_verified_age_hours": 24,
                "instructions": [
                    "수집 대상은 GS리테일(편의점,수퍼)·GSSHOP·GS건설·GS칼텍스·파르나스 호텔입니다. 현재 affiliate_scopes를 과거 프로필의 수집 목록보다 우선합니다.",
                    "GS리테일은 GS25와 GS THE FRESH 범위로 한정합니다. GSSHOP은 별도 수집 대상으로 분류하며 affiliate 값은 기존 GS SHOP 식별자를 유지합니다.",
                    "공식 페이지 본문을 직접 열어 확인합니다. 검색 스니펫만으로 사실을 등록하지 않습니다.",
                    "서버는 웹을 조회하지 않습니다. web_verified는 Codex 작업자가 확인했다고 제출한 기록입니다.",
                    "모든 claim에 본문 근거 excerpt를 연결합니다. 추론·구매 경험·가격·혜택을 지어내지 않습니다.",
                    "expires_at은 공식 페이지에 명시된 실제 종료 시각만 사용합니다. 임의 유효기간은 금지합니다.",
                    "종료일 없는 상시 정보는 expires_at=null과 validity_note를 기록하고 다음 조사 때 재확인합니다.",
                    "가격·행사 조건은 실제 종료 시각이 확인된 promotion으로만 등록하며 아니면 해당 주장을 제외합니다.",
                    "확인 가능한 자료가 없으면 materials=[]와 empty_reason을 기록합니다.",
                ]}

    def _research_input(self, db, settings):
        recent = []
        for row in db.execute("SELECT id,run_id,status,result_json FROM production_cycles ORDER BY created_at DESC LIMIT 20"):
            planning = json.loads(row["result_json"]).get("planning", {})
            if planning:
                recent.append({"cycle_id": row["id"], "run_id": row["run_id"], "status": row["status"],
                               "title": planning.get("title"), "topic_key": planning.get("topic_key"),
                               "source_ids": planning.get("source_ids", [])})
        return dict(self.source_research_policy(), enabled=settings.get("source_research_enabled") is True,
                    existing_sources=[self._source(row) for row in db.execute("SELECT * FROM source_materials ORDER BY id")],
                    recent_usage=recent)

    def _research_state(self, db, run):
        receipts = [json.loads(row[0]) for row in db.execute(
            "SELECT result_json FROM source_research_receipts ORDER BY created_at DESC LIMIT 30")]
        enabled = json.loads(run["settings_json"]).get("source_research_enabled") is True if run else self.config().get("source_research_enabled", True) is True
        return {"enabled": enabled, "latest": receipts[0] if receipts else None,
                "history": receipts, "policy": self.source_research_policy()}

    def _research_text(self, value, field, limit=2000, optional=False):
        if optional and value is None:
            return None
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise self.problem(field + " 값은 비어 있지 않은 문자열이어야 하며 길이 제한을 지켜야 합니다.")
        return self._safe_log(value.strip())

    def _canonical_research_url(self, value, affiliate=None):
        value = self._research_text(value, "url", 3000)
        if any(ord(character) < 33 for character in value) or "\\" in value:
            raise self.problem("출처 URL에 허용하지 않는 문자가 있습니다.")
        try:
            parsed = urlsplit(value)
            host = (parsed.hostname or "").lower()
            if parsed.scheme != "https" or not host or parsed.username is not None or parsed.password is not None or ":" in parsed.netloc:
                raise ValueError()
            domains = AFFILIATE_DOMAINS.get(normalize_affiliate(affiliate), []) if affiliate else sum(AFFILIATE_DOMAINS.values(), [])
            if not any(host == domain or host.endswith("." + domain) for domain in domains):
                raise ValueError()
        except ValueError:
            raise self.problem("해당 계열사의 공식 HTTPS 출처만 등록할 수 있습니다. 계정 정보와 포트는 허용하지 않습니다.")
        # www and tracking parameters do not identify a different source. Product
        # identifiers and all other query parameters remain part of its identity.
        host = host.removeprefix("www.")
        pairs = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
                 if not key.lower().startswith("utm_") and key.lower() not in
                 {"gclid", "dclid", "fbclid", "msclkid", "igshid", "_ga", "_gl", "mc_cid", "mc_eid"}]
        return urlunsplit(("https", host, parsed.path or "/", urlencode(sorted(pairs)), ""))

    def _normalize_research(self, result):
        if not isinstance(result, dict):
            raise self.problem("조사 결과는 JSON 객체여야 합니다.")
        queries, materials, rejected = result.get("queries"), result.get("materials"), result.get("rejected", [])
        if not isinstance(queries, list) or not 1 <= len(queries) <= MAX_QUERIES:
            raise self.problem("조사 질의는 1~8개가 필요합니다.")
        if not isinstance(materials, list) or len(materials) > MAX_MATERIALS:
            raise self.problem("한 조사에는 소재를 최대 12개 제출할 수 있습니다.")
        if not isinstance(rejected, list) or len(rejected) > MAX_REJECTED:
            raise self.problem("제외 자료는 최대 24개 기록할 수 있습니다.")
        clean_queries = []
        for query in queries:
            if isinstance(query, dict):
                query = dict(query, affiliate=normalize_affiliate(query.get("affiliate")))
            if not isinstance(query, dict) or query.get("affiliate") not in AFFILIATE_DOMAINS:
                raise self.problem("질의의 GS 계열사를 확인해 주세요.")
            clean_queries.append({"affiliate": query["affiliate"], "query": self._research_text(query.get("query"), "query", 1000)})
        clean_materials = []
        current = datetime.now(timezone.utc)
        for material in materials:
            if isinstance(material, dict):
                material = dict(material, affiliate=normalize_affiliate(material.get("affiliate")))
            if not isinstance(material, dict) or material.get("affiliate") not in AFFILIATE_DOMAINS:
                raise self.problem("자료의 GS 계열사를 확인해 주세요.")
            affiliate = material["affiliate"]
            if affiliate not in {query["affiliate"] for query in clean_queries}:
                raise self.problem("자료의 계열사에 대한 실제 조사 질의를 기록해 주세요.")
            url = self._canonical_research_url(material.get("url"), affiliate)
            verified = self._time(material.get("verified_at"))
            if verified > current + timedelta(minutes=5) or verified < current - timedelta(hours=24):
                raise self.problem("이번 조사에서 확인한 시각이 필요합니다. 확인 시각은 최근 24시간 이내여야 합니다.")
            expires = self._time(material["expires_at"]) if material.get("expires_at") is not None else None
            kind = material.get("material_type", "brand")
            if kind not in ["brand", "service", "product", "promotion"]:
                raise self.problem("material_type은 brand, service, product, promotion 중 하나여야 합니다.")
            if kind == "promotion" and expires is None:
                raise self.problem("행사·가격 조건에는 공식 페이지에 명시된 실제 종료 시각이 필요합니다.")
            validity = self._research_text(material.get("validity_note"), "validity_note", 2000, optional=expires is not None)
            claims, evidence = material.get("claims"), material.get("evidence")
            if not isinstance(claims, list) or not 1 <= len(claims) <= 8:
                raise self.problem("자료에는 근거가 있는 주장 1~8개가 필요합니다.")
            claims = [self._research_text(claim, "claim", 1500) for claim in claims]
            if len(set(claims)) != len(claims):
                raise self.problem("중복된 주장은 한 번만 기록해 주세요.")
            if not isinstance(evidence, list) or not 1 <= len(evidence) <= 8:
                raise self.problem("각 주장을 뒷받침하는 공식 본문 근거가 필요합니다.")
            clean_evidence = []
            for item in evidence:
                if not isinstance(item, dict):
                    raise self.problem("본문 근거는 claim과 excerpt 객체여야 합니다.")
                clean_evidence.append({"claim": self._research_text(item.get("claim"), "evidence.claim", 1500),
                                       "excerpt": self._research_text(item.get("excerpt"), "evidence.excerpt", 3000)})
            if set(claims) != {item["claim"] for item in clean_evidence}:
                raise self.problem("모든 주장에 일치하는 본문 근거를 연결해 주세요.")
            visibility = material.get("visibility", "internal" if affiliate == "GS SHOP" else "subtle")
            if visibility not in ["internal", "subtle", "explicit"] or (affiliate == "GS SHOP" and visibility != "internal"):
                raise self.problem("GS SHOP 자동 소재는 내부 정보로 보존하며 공개 노출 범위를 확인해 주세요.")
            clean_materials.append({"affiliate": affiliate, "title": self._research_text(material.get("title"), "title", 500),
                                   "url": url, "discovered_url": material["url"], "verified_at": verified.isoformat(),
                                   "expires_at": expires.isoformat() if expires else None, "claims": claims,
                                   "evidence": clean_evidence, "material_type": kind, "validity_note": validity,
                                   "visibility": visibility})
        clean_rejected = []
        for item in rejected:
            if not isinstance(item, dict):
                raise self.problem("제외 자료에는 url과 reason이 필요합니다.")
            clean_rejected.append({"url": self._research_text(item.get("url"), "rejected.url", 3000),
                                   "reason": self._research_text(item.get("reason"), "rejected.reason", 2000)})
        return {"queries": clean_queries, "materials": clean_materials, "rejected": clean_rejected,
                "decision_summary": self._research_text(result.get("decision_summary"), "decision_summary", 4000),
                "empty_reason": self._research_text(result.get("empty_reason"), "empty_reason", 2000, optional=True)}

    def worker_sources(self, cycle_id, lease_token, result):
        prepared = self._normalize_research(result)
        digest = hashlib.sha256(encode(prepared).encode()).hexdigest()
        with self.db() as db:
            cycle = self._leased(db, cycle_id, lease_token)
            run = db.execute("SELECT * FROM production_runs WHERE id=?", (cycle["run_id"],)).fetchone()
            current = datetime.now(timezone.utc)
            if (cycle["stage_index"] != 0 or cycle["status"] != "running" or
                    self._time(cycle["lease_expires_at"]) <= current or run["status"] != "running" or self._deadline_reached(run, current)):
                raise self.problem("실행 중인 소재 조사 단계의 만료되지 않은 작업 소유권이 필요합니다.", 409)
            if json.loads(run["settings_json"]).get("source_research_enabled") is not True:
                raise self.problem("이 실행은 자료 조사 계약을 사용하지 않는 이전 실행입니다.", 409)
            previous = db.execute("SELECT * FROM source_research_receipts WHERE cycle_id=?", (cycle_id,)).fetchone()
            if previous:
                if previous["input_hash"] != digest:
                    raise self.problem("이 제작 순환에는 이미 다른 조사 결과가 등록되어 있습니다.", 409)
                return dict(json.loads(previous["result_json"]), duplicate=True)
            research_id = "research-" + hashlib.sha256(cycle_id.encode()).hexdigest()[:20]
            created = now()
            job = db.execute("SELECT input_json FROM jobs WHERE id=?", (cycle_id + ":sources",)).fetchone()
            snapshot = json.loads(job[0]).get("source_research", {}).get("existing_sources", [])
            expected_versions = {source["id"]: source.get("source_version", 1) for source in snapshot}
            by_url = {}
            for row in db.execute("SELECT * FROM source_materials ORDER BY created_at"):
                try:
                    canonical = self._canonical_research_url(row["url"], row["affiliate"])
                except self.problem:
                    continue
                by_url.setdefault(canonical, row)
            accepted, skipped, seen = [], [], set()
            for material in prepared["materials"]:
                url = material["url"]
                if url in seen:
                    skipped.append({"url": url, "reason": "동일 공식 URL의 중복 제출"})
                    continue
                seen.add(url)
                if material["expires_at"] and self._time(material["expires_at"]) <= current:
                    skipped.append({"url": url, "reason": "공식 유효기간이 지난 자료"})
                    continue
                row = by_url.get(url)
                if row and row["id"] in expected_versions and row["source_version"] != expected_versions[row["id"]]:
                    skipped.append({"url": url, "reason": "조사 중 기존 소재가 수정되어 보존했습니다."})
                    continue
                if row and row["origin"] != "web_research":
                    if (row["affiliate"] != material["affiliate"] or row["status"] != "active" or
                            (row["expires_at"] and self._time(row["expires_at"]) <= current) or
                            set(json.loads(row["claims_json"])) != set(material["claims"])):
                        skipped.append({"url": url, "reason": "직접 등록·수정한 소재를 보존했습니다."})
                        continue
                    source_id, version = row["id"], row["source_version"]
                else:
                    if row and self._time(material["verified_at"]) < self._time(row["verified_at"]):
                        skipped.append({"url": url, "reason": "이미 등록된 확인 기록보다 오래된 조사입니다."})
                        continue
                    source_id = row["id"] if row else "source-" + hashlib.sha256(url.encode()).hexdigest()[:20]
                    version = row["source_version"] + 1 if row else 1
                    provenance = dict(PROVENANCE, research_id=research_id, run_id=run["id"], cycle_id=cycle_id,
                                      verified_at=material["verified_at"], discovered_url=material["discovered_url"],
                                      evidence=material["evidence"], material_type=material["material_type"],
                                      validity_note=material["validity_note"], recheck_policy="다음 콘텐츠 조사에서 공식 본문 재확인")
                    db.execute("""INSERT INTO source_materials
                        (id,affiliate,title,url,verified_at,expires_at,claims_json,visibility,status,created_at,updated_at,origin,discovery_json,source_version)
                        VALUES (?,?,?,?,?,?,?,?,'active',?,?,'web_research',?,?)
                        ON CONFLICT(id) DO UPDATE SET affiliate=excluded.affiliate,title=excluded.title,
                        verified_at=excluded.verified_at,expires_at=excluded.expires_at,claims_json=excluded.claims_json,
                        visibility=excluded.visibility,status='active',updated_at=excluded.updated_at,
                        discovery_json=excluded.discovery_json,source_version=excluded.source_version""",
                               (source_id, material["affiliate"], material["title"], url, material["verified_at"],
                                material["expires_at"], encode(material["claims"]), material["visibility"],
                                row["created_at"] if row else created, created, encode(provenance), version))
                action = "reused" if row else "added"
                accepted.append(dict(material, source_id=source_id, source_version=version, action=action))
            if not accepted and not prepared["empty_reason"]:
                raise self.problem("확인·등록 가능한 자료가 없으면 empty_reason에 이유를 명시해 주세요.")
            receipt = {"research_id": research_id, "run_id": run["id"], "cycle_id": cycle_id,
                       "source_ids": [material["source_id"] for material in accepted],
                       "added_count": sum(material["action"] == "added" for material in accepted),
                       "reused_count": sum(material["action"] == "reused" for material in accepted),
                       "skipped_count": len(skipped), "rejected_count": len(prepared["rejected"]),
                       "outcome": "accepted" if accepted else "empty", "empty_reason": prepared["empty_reason"] if not accepted else None,
                       "queries": prepared["queries"], "materials": accepted, "rejected": prepared["rejected"],
                       "skipped": skipped, "decision_summary": prepared["decision_summary"], "created_at": created,
                       "provenance": PROVENANCE}
            receipt = self._safe_log(receipt)
            db.execute("INSERT INTO source_research_receipts VALUES (?,?,?,?,?,?)",
                       (research_id, run["id"], cycle_id, digest, encode(receipt), created))
            self._event(db, run["id"], cycle_id, "sources", "sources.researched",
                        "공식 자료 조사 기록과 소재를 저장했습니다." if accepted else "확인 가능한 자료가 없어 일상 중심으로 진행합니다.",
                        {"source_research": receipt}, "info" if accepted else "warning")
            for material in accepted:
                self._event(db, run["id"], cycle_id, "sources", "source." + material["action"],
                            "조사한 GS 소재를 자동 등록했습니다." if material["action"] == "added" else "재확인한 GS 소재를 재사용합니다.",
                            {"research_id": research_id, "source_id": material["source_id"], "material": material,
                             "provenance": PROVENANCE})
            return dict(receipt, duplicate=False)

    def _research_stage_result(self, db, cycle, stage, result):
        if stage not in ["sources", "planning"]:
            return result
        run = db.execute("SELECT settings_json FROM production_runs WHERE id=?", (cycle["run_id"],)).fetchone()
        if json.loads(run[0]).get("source_research_enabled") is not True:
            return result
        row = db.execute("SELECT result_json FROM source_research_receipts WHERE cycle_id=?", (cycle["id"],)).fetchone()
        if not row:
            raise self.problem("공식 자료를 조사하고 worker-sources로 조사 기록을 먼저 저장해 주세요.", 409)
        receipt = json.loads(row[0])
        ids = result.get("source_ids", [])
        if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids) or len(ids) != len(set(ids)):
            raise self.problem("중복되지 않은 소재 ID 목록이 필요합니다.")
        if stage == "sources" and (result.get("research_id") != receipt["research_id"] or set(ids) != set(receipt["source_ids"])):
            raise self.problem("저장한 조사 기록의 research_id와 source_ids를 그대로 완료 결과에 연결해 주세요.", 409)
        if not set(ids).issubset(set(receipt["source_ids"])):
            raise self.problem("이번 공식 조사에서 확인한 소재만 기획에 사용할 수 있습니다.", 409)
        for material in receipt["materials"]:
            if material["source_id"] not in ids:
                continue
            source = db.execute("SELECT * FROM source_materials WHERE id=?", (material["source_id"],)).fetchone()
            if not source or source["source_version"] != material["source_version"]:
                raise self.problem("조사 이후 소재가 수정되었습니다. 이전 조사로 변경된 소재를 사용할 수 없습니다.", 409)
        return dict(result, source_research=receipt) if stage == "sources" else result
