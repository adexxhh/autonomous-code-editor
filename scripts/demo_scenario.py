"""Real Tree-sitter edit and isolated Git validation demo."""
from pathlib import Path
import tempfile,subprocess,sys,json
from ast_editor import replace_function,evaluate_in_worktree,token_comparison
def main():
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)
        for args in [["init"],["config","user.email","demo@example.invalid"],["config","user.name","Demo"]]:
            subprocess.run(["git",*args],cwd=root,capture_output=True,check=True)
        source="# Unicode: caf?\ndef untouched():\n    return 99\n\ndef add(a,b):\n    return a-b\n"
        (root/"example.py").write_text(source,encoding="utf-8")
        subprocess.run(["git","add","."],cwd=root,check=True)
        subprocess.run(["git","commit","-m","Local fixture"],cwd=root,check=True,capture_output=True)
        replacement="def add(a,b):\n    return a+b"
        command=[sys.executable,"-c","from example import add; assert add(2,3)==5"]
        result=evaluate_in_worktree(root,"example.py","add",replacement,command)
        print("Tree-sitter selects top-level function: add")
        print(result["diff"])
        print("Isolated subprocess assertion passed:",result["passed"])
        print("Original checkout unchanged:",(root/"example.py").read_text(encoding="utf-8")==source)
        failed=evaluate_in_worktree(root,"example.py","add","def add(a,b):\n    return 0",command)
        print("Incorrect candidate rejected:",failed["passed"] is False)
        print("Token measurement (one fixture, output payload only):")
        print(json.dumps(token_comparison(replace_function(source,"add",replacement),replacement),indent=2))
if __name__=="__main__":main()
