#!/usr/bin/env python3
import json
import platform
import shutil
import sys
required = {name: bool(shutil.which(name)) for name in ("git", "make")}
supported = (3, 12) <= sys.version_info[:2] < (3, 15)
print(json.dumps({
    "python_observed": platform.python_version(),
    "python_supported_for_project": supported,
    "required_tools": required,
    "optional_tools": {name: bool(shutil.which(name)) for name in ("docker","curl","unzip","terraform")},
    "note": "unzip is optional after extraction; Docker is required only for the PostgreSQL profile.",
    "aws_calls": 0,
}, indent=2))
sys.exit(0 if supported and all(required.values()) else 1)
