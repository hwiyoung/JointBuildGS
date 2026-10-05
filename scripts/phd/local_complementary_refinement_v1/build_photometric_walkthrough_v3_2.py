"""Publish immutable photometric walkthrough under the existing read-only server."""
from __future__ import annotations
import argparse, hashlib, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--attempt",type=Path,required=True)
    p.add_argument("--site",type=Path,required=True)
    p.add_argument("--ui",type=Path,required=True)
    p.add_argument("--packet-prefix",default="packet_photometry_v3_2")
    a=p.parse_args()
    manifest=json.loads((a.attempt/"manifest.json").read_text())
    source_receipt=json.loads((a.attempt/"receipt.json").read_text())
    if source_receipt.get("status")!="PASS_INTERNAL_FIT_DIAGNOSTIC":raise ValueError("source diagnostic technical receipt must pass")
    if manifest.get("scientific_verdict") is not None:raise ValueError("verdict must be null")
    if not manifest.get("cases"):raise ValueError("no diagnostic cases")
    before=sha(a.site/"current.json") if (a.site/"current.json").exists() else None
    name=a.packet_prefix+"_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    packet=a.site/"packets"/name
    packet.mkdir(parents=True,exist_ok=False)
    try:
        payload=packet/"assets"/"diagnostic"
        shutil.copytree(a.attempt,payload,symlinks=False)
        for f in ("index.html","app.js","style.css"):shutil.copy2(a.ui/f,packet/f)
        (packet/"data.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
        checked=[]
        for c in manifest["cases"]:
            rel=c.get("path") or c.get("case_json") or c.get("case_url")
            source=(a.attempt/rel).resolve()
            if not source.is_relative_to(a.attempt.resolve()):raise ValueError("case path escapes attempt")
            item=json.loads(source.read_text())
            if not item.get("neighbors"):raise ValueError("case has no neighbors")
            checked.append({"case_id":item["case_id"],"path":rel,"sha256":sha(source),"neighbors":len(item["neighbors"])})
        inputs=[]
        for f in sorted(a.attempt.rglob("*")):
            if f.is_file():inputs.append({"path":str(f.relative_to(a.attempt)),"sha256":sha(f)})
        output=[]
        for f in sorted(packet.rglob("*")):
            if f.is_file():output.append({"path":str(f.relative_to(packet)),"sha256":sha(f)})
        after=sha(a.site/"current.json") if (a.site/"current.json").exists() else None
        receipt={"status":"PASS","scope":"INTERNAL_FIT_DIAGNOSTIC_STATIC_PUBLICATION","scientific_verdict":None,
            "packet":name,"source_attempt":str(a.attempt),"source_manifest_sha256":sha(a.attempt/"manifest.json"),
            "cases":checked,"outputs":output,"current_before_sha256":before,"current_after_sha256":after,
            "current_pointer_updated":False,"current_pointer_observed_change":before!=after,
            "publisher_sha256":sha(Path(__file__)),"python":sys.version,
            "created_at":datetime.now(timezone.utc).isoformat(),"browser_qa":"PENDING"}
        (packet/"sources.json").write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+"\n")
        (packet/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
        print(json.dumps({"status":"PASS","packet":str(packet),"url":"http://localhost:8905/packets/"+name+"/index.html"},ensure_ascii=False))
    except Exception as e:
        (packet/"receipt.json").write_text(json.dumps({"status":"FAIL","error":str(e),"scientific_verdict":None},ensure_ascii=False,indent=2)+"\n")
        raise
if __name__=="__main__":main()
