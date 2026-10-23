"""Targeted Python function replacement with Tree-sitter and explicit file isolation."""
from pathlib import Path
import ast
import difflib
import subprocess
import tempfile
import json
import argparse
import tree_sitter_python
from tree_sitter import Language, Parser

PARSER = Parser(Language(tree_sitter_python.language()))

def replace_function(source: str, name: str, replacement: str) -> str:
    raw = source.encode("utf-8")
    tree = PARSER.parse(raw)
    if tree.root_node.has_error:
        raise ValueError("Input contains Python syntax errors")
    # Top-level functions only; reject ambiguous names rather than edit the wrong scope.
    matches = []
    for node in tree.root_node.named_children:
        actual = node
        if node.type == "decorated_definition":
            actual = node.child_by_field_name("definition")
        if actual and actual.type == "function_definition":
            field = actual.child_by_field_name("name")
            if raw[field.start_byte:field.end_byte].decode() == name:
                matches.append(node)
    if len(matches) != 1:
        raise ValueError("Expected exactly one matching top-level function")
    replacement = replacement.strip() + "\n"
    parsed = ast.parse(replacement)
    if len(parsed.body) != 1 or not isinstance(parsed.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)) or parsed.body[0].name != name:
        raise ValueError("Replacement must define only the requested function")
    target = matches[0]
    updated = raw[:target.start_byte] + replacement.rstrip("\n").encode() + raw[target.end_byte:]
    if PARSER.parse(updated).root_node.has_error:
        raise ValueError("Replacement produces syntax errors")
    ast.parse(updated.decode())
    return updated.decode()

def resolve_file(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts or path.is_symlink():
        raise ValueError("Unsafe workspace path")
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or resolved.suffix != ".py":
        raise ValueError("Only Python files inside the workspace are supported")
    # Reject intermediate symlinks too.
    current = path
    while current != root:
        if current.is_symlink():
            raise ValueError("Symlinks are not editable")
        current = current.parent
    return resolved

def preview(root, relative, name, replacement):
    path = resolve_file(root, relative)
    source = path.read_text(encoding="utf-8")
    edited = replace_function(source, name, replacement)
    diff = "".join(difflib.unified_diff(source.splitlines(True), edited.splitlines(True), fromfile=relative, tofile=relative))
    return edited, diff

def evaluate_in_worktree(repo, relative, name, replacement, command=None, timeout=30):
    """Use a disposable detached worktree. Commands require explicit caller consent.
    This isolates Git changes; it is NOT an OS sandbox for untrusted code.
    """
    repo = Path(repo).resolve()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True)
    if dirty.stdout:
        raise ValueError("Commit/stash source changes before evaluating a detached HEAD")
    with tempfile.TemporaryDirectory(prefix="ast-edit-") as temporary:
        worktree = Path(temporary) / "checkout"
        subprocess.run(["git", "worktree", "add", "--detach", str(worktree), "HEAD"], cwd=repo, check=True, capture_output=True)
        try:
            edited, diff = preview(worktree, relative, name, replacement)
            resolve_file(worktree, relative).write_text(edited, encoding="utf-8")
            result = {"diff": diff, "tested": False, "passed": None, "isolation": "git-worktree-only"}
            if command:
                try:
                    run = subprocess.run(command, cwd=worktree, capture_output=True, text=True, timeout=timeout)
                    result.update(tested=True, passed=run.returncode == 0, returncode=run.returncode,
                                  stdout=run.stdout, stderr=run.stderr)
                except subprocess.TimeoutExpired:
                    result.update(tested=True, passed=False, error="timeout")
            return result
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo, check=True, capture_output=True)

def token_comparison(whole_file, replacement, encoding="cl100k_base"):
    import tiktoken
    enc = tiktoken.get_encoding(encoding)
    whole, targeted = len(enc.encode(whole_file)), len(enc.encode(replacement))
    return {"encoding": encoding, "whole_file_output_tokens": whole, "replacement_output_tokens": targeted,
            "output_token_reduction_pct": (100 * (whole-targeted)/whole) if whole else 0,
            "scope": "output payload only; excludes prompts, retries, and reasoning"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument("--function", required=True)
    parser.add_argument("--replacement", required=True)
    args = parser.parse_args()
    text = Path(args.replacement).read_text(encoding="utf-8")
    edited, diff = preview(args.repo, args.file, args.function, text)
    print(diff)
