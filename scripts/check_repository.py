#!/usr/bin/env python3
"""Check tracked files for accidentally committed local state and high-risk tokens.
A lightweight guard; not a replacement for a dedicated secret scanner.
"""
import re
# fixed local git command, no shell or external input
import subprocess  # nosec B404
import shutil
from pathlib import Path
root=Path(__file__).resolve().parent.parent
git=shutil.which("git")
if not git: raise SystemExit("git is required")
# fixed argv, trusted developer PATH
result=subprocess.run([git,"ls-files","-z"],cwd=root,capture_output=True,check=True)  # nosec B603
files=[p.decode() for p in result.stdout.split(b"\0") if p]
if not files: raise SystemExit("No tracked files: initialize and stage the project before this check.")
bad=[]
token=re.compile(rb"AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
for name in files:
    path=Path(name)
    if name==".env" or any(part in {".local",".venv","__pycache__"} for part in path.parts) or name.endswith((".sqlite3",".tfstate",".pyc")):
        bad.append((name,"local state must not be tracked"))
    file=root/path
    if file.is_file() and token.search(file.read_bytes()):
        bad.append((name,"potential credential"))
if bad:
    for name,reason in bad: print(name+": "+reason)
    raise SystemExit(1)
print("Tracked-file guard passed:",len(files),"files. No cloud API calls.")
