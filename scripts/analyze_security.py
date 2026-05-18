#!/usr/bin/env python3
"""
安全与合规分析器
检测敏感信息泄露、依赖许可证、潜在安全漏洞模式

用法:
    python analyze_security.py <repo_path> [--output security.json]

输出 JSON:
{
  "secrets": [{"file": "...", "line": N, "type": "api_key", "snippet": "..."}, ...],
  "license_compatibility": {"project_license": "MIT", "dependencies": [{"name": "...", "license": "..."}]},
  "security_patterns": [{"file": "...", "line": N, "pattern": "sql_injection", "severity": "high"}, ...],
  "dependency_risks": [{"package": "...", "version": "...", "risk": "outdated"}, ...]
}
"""

import os
import re
import json
import argparse
from collections import defaultdict

SKIP_DIRS = {".git", "vendor", "node_modules", "target", "dist", "build",
             ".venv", "venv", "__pycache__", ".pytest_cache"}


def get_submodule_paths(repo_path):
    """从 .gitmodules 读取 submodule 路径列表"""
    submodules = []
    gm_path = os.path.join(repo_path, ".gitmodules")
    if not os.path.exists(gm_path):
        return submodules
    try:
        with open(gm_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = re.match(r'^\s*path\s*=\s*(.+)$', line)
                if m:
                    submodules.append(m.group(1).strip())
    except Exception:
        pass
    return submodules


# 敏感信息正则
SECRET_PATTERNS = [
    ("aws_access_key", re.compile(r'AKIA[0-9A-Z]{16}')),
    ("aws_secret_key", re.compile(r'["\']?[a-zA-Z0-9/+=]{40}["\']?')),
    ("github_token", re.compile(r'gh[pousr]_[A-Za-z0-9_]{36,}')),
    ("generic_api_key", re.compile(r'(?:api[_-]?key|apikey)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{16,})["\']?', re.IGNORECASE)),
    ("private_key", re.compile(r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----')),
    ("password_in_code", re.compile(r'(?:password|passwd|pwd)\s*[:=]\s*["\']([^"\']{4,})["\']', re.IGNORECASE)),
    ("bearer_token", re.compile(r'Bearer\s+[a-zA-Z0-9_\-\.]+')),
    ("jwt_token", re.compile(r'eyJ[a-zA-Z0-9_\-]*\.eyJ[a-zA-Z0-9_\-]*\.[a-zA-Z0-9_\-]*')),
]

# 安全漏洞代码模式
SECURITY_PATTERNS = {
    ".go": [
        ("sql_injection", re.compile(r'(?:Query|Exec)\s*\(\s*[^,]*\+'), "high"),
        ("unsafe_pointer", re.compile(r'unsafe\.'), "medium"),
        ("hardcoded_path", re.compile(r'(?:os\.Open|ioutil\.ReadFile)\s*\(\s*"[^"]+"\s*\)'), "low"),
    ],
    ".py": [
        ("sql_injection", re.compile(r'(?:execute|query)\s*\(\s*["\'][^"\']*%s'), "high"),
        ("eval_danger", re.compile(r'\beval\s*\('), "high"),
        ("pickle_load", re.compile(r'pickle\.load'), "medium"),
        ("shell_injection", re.compile(r'(?:os\.system|subprocess\.call)\s*\([^)]*\+'), "high"),
    ],
    ".rs": [
        ("unsafe_block", re.compile(r'\bunsafe\s*\{'), "medium"),
        ("raw_pointer", re.compile(r'\*const\s+|\*mut\s+'), "low"),
    ],
    ".java": [
        ("sql_injection", re.compile(r'(?:createStatement|prepareStatement)\s*\(\s*[^,)]*\+'), "high"),
        ("unsafe_deserialization", re.compile(r'ObjectInputStream'), "medium"),
    ],
    ".ts": [
        ("eval_danger", re.compile(r'\beval\s*\('), "high"),
        ("inner_html", re.compile(r'\.innerHTML\s*='), "medium"),
    ],
    ".js": [
        ("eval_danger", re.compile(r'\beval\s*\('), "high"),
        ("inner_html", re.compile(r'\.innerHTML\s*='), "medium"),
    ],
}

# 常见许可证标识
LICENSE_PATTERNS = {
    "MIT": re.compile(r'MIT\s+License', re.IGNORECASE),
    "Apache-2.0": re.compile(r'Apache\s+License.*2\.0', re.IGNORECASE),
    "GPL-3.0": re.compile(r'GNU.*GENERAL.*PUBLIC.*LICENSE.*Version\s*3', re.IGNORECASE),
    "GPL-2.0": re.compile(r'GNU.*GENERAL.*PUBLIC.*LICENSE.*Version\s*2', re.IGNORECASE),
    "BSD-3": re.compile(r'BSD\s+3', re.IGNORECASE),
    "BSD-2": re.compile(r'BSD\s+2', re.IGNORECASE),
    "MPL-2.0": re.compile(r'Mozilla\s+Public\s+License', re.IGNORECASE),
    "ISC": re.compile(r'ISC\s+License', re.IGNORECASE),
}


def detect_secrets(repo_path):
    findings = []
    submodule_paths = get_submodule_paths(repo_path)
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and d not in submodule_paths]
        for fname in files:
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, repo_path)
            # 跳过二进制文件和大文件
            if os.path.getsize(fpath) > 1024 * 1024:
                continue
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                for name, pattern in SECRET_PATTERNS:
                    if pattern.search(line):
                        # 过滤 false positive：测试数据、示例值
                        if any(k in line.lower() for k in ["example", "placeholder", "your_", "test_", "fake_", "mock_"]):
                            continue
                        findings.append({
                            "file": rel, "line": i,
                            "type": name,
                            "snippet": line.strip()[:100],
                            "severity": "critical" if name in ("private_key", "aws_secret_key") else "high"
                        })
    return findings


def detect_security_patterns(repo_path):
    findings = []
    submodule_paths = get_submodule_paths(repo_path)
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and d not in submodule_paths]
        for fname in files:
            ext = os.path.splitext(fname)[1]
            if ext not in SECURITY_PATTERNS:
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, repo_path)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                for name, pattern, severity in SECURITY_PATTERNS[ext]:
                    if pattern.search(line):
                        findings.append({
                            "file": rel, "line": i,
                            "pattern": name,
                            "severity": severity,
                            "snippet": line.strip()[:100]
                        })
    return findings


def analyze_licenses(repo_path):
    licenses = {"project": "unknown", "dependencies": []}

    # 检测项目自身的许可证
    license_files = ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]
    for lf in license_files:
        lpath = os.path.join(repo_path, lf)
        if os.path.exists(lpath):
            try:
                with open(lpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                for lic_name, pattern in LICENSE_PATTERNS.items():
                    if pattern.search(content):
                        licenses["project"] = lic_name
                        break
            except Exception:
                pass
            break

    # 检测依赖的许可证（简化版，仅扫描 vendor 和已知 LICENSE 文件）
    dep_licenses = []
    submodule_paths = get_submodule_paths(repo_path)
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and d not in submodule_paths]
        if "LICENSE" in [f.upper().replace(".MD", "").replace(".TXT", "") for f in files]:
            for f in files:
                if f.upper().startswith("LICENSE"):
                    fpath = os.path.join(root, f)
                    rel = os.path.relpath(os.path.dirname(fpath), repo_path)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                            content = fp.read(2000)
                        for lic_name, pattern in LICENSE_PATTERNS.items():
                            if pattern.search(content):
                                dep_licenses.append({"path": rel, "license": lic_name})
                                break
                        else:
                            dep_licenses.append({"path": rel, "license": "unknown"})
                    except Exception:
                        pass
                    break

    # 去重
    seen = set()
    unique = []
    for d in dep_licenses:
        key = (d["path"], d["license"])
        if key not in seen:
            seen.add(key)
            unique.append(d)

    licenses["dependencies"] = unique[:30]
    return licenses


def analyze_dependencies(repo_path):
    """解析依赖文件，检查是否有明显过时或高风险依赖"""
    risks = []

    # package.json
    pj = os.path.join(repo_path, "package.json")
    if os.path.exists(pj):
        try:
            with open(pj, "r", encoding="utf-8") as f:
                data = json.load(f)
            deps = {}
            deps.update(data.get("dependencies", {}))
            deps.update(data.get("devDependencies", {}))
            for name, version in deps.items():
                # 检测 0.x 版本或明确过时的包
                if version.startswith("0.") or version.startswith("^") and version[1:].startswith("0."):
                    risks.append({"package": name, "version": version, "risk": "unstable_or_early", "ecosystem": "npm"})
        except Exception:
            pass

    # go.mod
    gm = os.path.join(repo_path, "go.mod")
    if os.path.exists(gm):
        try:
            with open(gm, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.match(r'\s*(\S+)\s+v(\S+)', line)
                    if m and not m.group(1).startswith("go "):
                        risks.append({"package": m.group(1), "version": m.group(2), "risk": "need_review", "ecosystem": "go"})
        except Exception:
            pass

    # requirements.txt
    rt = os.path.join(repo_path, "requirements.txt")
    if os.path.exists(rt):
        try:
            with open(rt, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.match(r'([a-zA-Z0-9_\-]+)', line.strip())
                    if m:
                        risks.append({"package": m.group(1), "version": "unknown", "risk": "need_review", "ecosystem": "python"})
        except Exception:
            pass

    return risks[:30]


def main():
    parser = argparse.ArgumentParser(description="安全与合规分析器")
    parser.add_argument("repo_path", help="仓库本地路径")
    parser.add_argument("--output", "-o", default="security.json", help="输出 JSON 文件路径")
    args = parser.parse_args()

    if not os.path.isdir(args.repo_path):
        print(f"错误: {args.repo_path} 不是有效目录")
        return 1

    print(f"正在扫描安全与合规问题: {args.repo_path} ...")

    result = {
        "secrets": detect_secrets(args.repo_path),
        "security_patterns": detect_security_patterns(args.repo_path),
        "license_compatibility": analyze_licenses(args.repo_path),
        "dependency_risks": analyze_dependencies(args.repo_path),
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"扫描完成!")
    print(f"  敏感信息: {len(result['secrets'])}")
    print(f"  安全模式: {len(result['security_patterns'])}")
    print(f"  项目许可证: {result['license_compatibility']['project']}")
    print(f"  依赖风险: {len(result['dependency_risks'])}")
    print(f"  输出: {args.output}")
    return 0


if __name__ == "__main__":
    exit(main())
