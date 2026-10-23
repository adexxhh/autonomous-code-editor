"""Small disclosed model-driven repair probes, not a representative success-rate benchmark."""
from pathlib import Path
import argparse,json,subprocess,sys,tempfile
from repair_agent import repair

CASES=[
 {"name":"clamp","source":"def clamp(value, low, high):\n    return min(low, max(high, value))\n",
  "task":"Clamp value into inclusive bounds low and high. Raise ValueError if low exceeds high.",
  "tests":"from target import clamp\nassert clamp(-2,0,5)==0\nassert clamp(8,0,5)==5\nassert clamp(3,0,5)==3\ntry:\n clamp(1,5,0)\nexcept ValueError: pass\nelse: raise AssertionError('invalid bounds')\n"},
 {"name":"mean","source":"def mean(values):\n    return sum(values) // len(values)\n",
  "task":"Return the arithmetic mean as a number for a nonempty iterable of numbers. Support one-pass generators. Raise ValueError for an empty iterable.",
  "tests":"from target import mean\nassert mean([1,2])==1.5\nassert mean(iter([2,4,6]))==4\nassert mean([-2,1])==-0.5\ntry:\n mean(iter([]))\nexcept ValueError: pass\nelse: raise AssertionError('empty iterable')\n"},
 {"name":"unique","source":"def unique(values):\n    return list(set(values))\n",
  "task":"Return unique input values in first-occurrence order. Support equality-comparable unhashable values such as lists. Do not mutate inputs.",
  "tests":"from target import unique\na=[[1],[2],[1],[]]\nassert unique(a)==[[1],[2],[]]\nassert a==[[1],[2],[1],[]]\nassert unique([3,1,3,2,1])==[3,1,2]\nassert unique([])==[]\n"}
]

class LocalHFProvider:
    def __init__(self,model):
        from serving_backend import HFRepairBackend
        self.backend=HFRepairBackend(model)
    def propose(self,context):return self.backend.propose(context)

def run_case(case,provider):
    with tempfile.TemporaryDirectory(prefix="repair-probe-") as temp:
        repo=Path(temp)
        (repo/"target.py").write_text(case["source"],encoding="utf-8")
        (repo/"verify.py").write_text(case["tests"],encoding="utf-8")
        (repo/".gitignore").write_text("__pycache__/\n",encoding="utf-8")
        for cmd in [
            ["git","init","-q"],["git","config","user.email","benchmark@localhost"],
            ["git","config","user.name","Disposable benchmark"],
            ["git","add","."],["git","commit","-qm","Fixed benchmark input"]]:
            subprocess.run(cmd,cwd=repo,check=True,capture_output=True)
        baseline=subprocess.run([sys.executable,"-B","verify.py"],cwd=repo,capture_output=True,text=True)
        if baseline.returncode==0:raise RuntimeError("Fixture is not initially failing: "+case["name"])
        if provider is None:return {"case":case["name"],"baseline_fails":True}
        result=repair(repo,"target.py",case["name"],case["task"],provider,[sys.executable,"-B","verify.py"],max_attempts=3)
        return {"case":case["name"],"baseline_fails":True,**result}

def main():
    p=argparse.ArgumentParser();p.add_argument("--model");p.add_argument("--output",default="repair-probes.json")
    p.add_argument("--check-fixtures",action="store_true");p.add_argument("--allow-local-execution",action="store_true")
    args=p.parse_args()
    if not args.check_fixtures and not args.allow_local_execution:
        p.error("Use a disposable runtime and explicitly pass --allow-local-execution")
    if not args.check_fixtures and not args.model:p.error("--model is required")
    provider=None if args.check_fixtures else LocalHFProvider(args.model)
    results=[run_case(case,provider) for case in CASES]
    report={"scope":"Three disclosed synthetic probes; not a representative repair-rate estimate",
            "actual_model_run":not args.check_fixtures,"model":args.model,
            "verified_candidates":sum(x.get("status")=="verified_candidate" for x in results),
            "cases":results}
    Path(args.output).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="cases"},indent=2))
if __name__=="__main__":main()
