"""Claim the requested runtime stage without printing its private lease."""
import argparse
import json
import os
from pathlib import Path
import uuid


def bootstrap(store, run_id, worker_id):
    # worker_next checks the expected run inside its claim transaction.
    claim = store.worker_next(worker_id, expected_run_id=run_id)
    if not claim.get("should_work"):
        return {"should_work": False, "reason": claim.get("reason")}
    directory = store.runtime / "ai-worker" / "claims"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_path = directory / (uuid.uuid4().hex + ".json")
    fd = os.open(str(private_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(claim, stream, ensure_ascii=False)
    cycle, job = claim["cycle"], claim["job"]
    output = store.root / "output" / "content" / cycle["content_id"] / "inputs"
    output.mkdir(parents=True, exist_ok=True)
    public_path = output / (job["stage"] + ".json")
    public = store._safe_log({
        "run": claim["run"],
        "cycle": {key: cycle[key] for key in ("id", "content_id", "number", "stage", "result")},
        "input": json.loads(job["input_json"]),
        "checkpoint": json.loads(job["result_json"]) if job.get("result_json") else None,
    })
    public_path.write_text(json.dumps(public, ensure_ascii=False, indent=2))
    return {"should_work": True, "stage": job["stage"], "cycle_id": cycle["id"],
            "claim_file": str(private_path), "input_file": str(public_path)}


if __name__ == "__main__":
    from server import Store
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--worker-id", required=True)
    args = parser.parse_args()
    print(json.dumps(bootstrap(Store(Path(__file__).resolve().parents[2]), args.run_id, args.worker_id), ensure_ascii=False))
