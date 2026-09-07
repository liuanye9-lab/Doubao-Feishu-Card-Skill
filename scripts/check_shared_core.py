"""Check the provider-neutral core in two independently installable Skills."""
import argparse
import ast
import hashlib
from pathlib import Path

FILES = ('text_quality.py', 'review_evidence.py', 'generate_card.py', 'layout_coordination.py',
         'plan_card.py', 'validate_card.py', 'check_shared_core.py')

FUNCTIONS = {'feishu_cli.py': ('push_cardkit',),
             'finalize_card.py': ('attach_delivery_evidence', 'record_review')}

def function_ast(path, name):
    module = ast.parse(path.read_text(encoding='utf-8'))
    return next((ast.dump(node, include_attributes=False) for node in module.body
                 if isinstance(node, ast.FunctionDef) and node.name == name), None)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--peer', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    mismatches = []
    for name in FILES:
        peer = args.peer / 'scripts' / name
        if not peer.is_file() or hashlib.sha256((root/name).read_bytes()).digest() != hashlib.sha256(peer.read_bytes()).digest():
            mismatches.append(name)
    for filename, names in FUNCTIONS.items():
        for name in names:
            peer = args.peer / 'scripts' / filename
            local = function_ast(root / filename, name)
            if not peer.is_file() or not local or local != function_ast(peer, name):
                mismatches.append(filename + ':' + name)
    print('shared core: ' + (', '.join(mismatches) if mismatches else 'identical'))
    return bool(mismatches)

if __name__ == '__main__':
    raise SystemExit(main())
