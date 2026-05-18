#!/usr/bin/env python3
"""
架构元素提取器
从代码库中提取关键架构元素：入口、接口/抽象类/trait、工厂函数、核心结构体等

用法:
    python analyze_arch.py <repo_path> [--output arch.json]

输出 JSON 结构:
{
  "entry_points": [{"file": "...", "line": N, "name": "main", "type": "function"}, ...],
  "interfaces": [{"file": "...", "line": N, "name": "Reader", "language": "go"}, ...],
  "core_structs": [{"file": "...", "line": N, "name": "Server", "fields": [...]}, ...],
  "factories": [{"file": "...", "line": N, "name": "NewServer", "returns": "Server"}, ...],
  "middleware": [{"file": "...", "name": "middleware", "pattern": "chain"}, ...]
}
"""

import os
import re
import json
import argparse
from collections import defaultdict

SKIP_DIRS = {
    ".git", "vendor", "node_modules", "target", "dist", "build",
    ".venv", "venv", "__pycache__", ".pytest_cache"
}

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

# 各语言的架构特征正则
PATTERNS = {
    ".go": {
        "entry_func": re.compile(r'^func\s+(main)\s*\('),
        "interface": re.compile(r'^type\s+(\w+)\s+interface\s*\{'),
        "struct": re.compile(r'^type\s+(\w+)\s+struct\s*\{'),
        "factory": re.compile(r'^func\s+(New\w+)\s*\('),
        "method": re.compile(r'^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\('),
        "middleware": re.compile(r'(?:Middleware|HandleFunc|Use\s*\()'),
    },
    ".py": {
        "entry_func": re.compile(r'^if\s+__name__\s*==\s*[\'"]__main__[\'"]\s*:'),
        "interface": re.compile(r'^class\s+(\w+)\s*\(\s*ABC\s*\)|^class\s+(\w+)\s*\(\s*Protocol\s*\)'),
        "struct": re.compile(r'^class\s+(\w+)\s*[\(:)]'),
        "factory": re.compile(r'^def\s+(create_\w+|build_\w+|make_\w+)\s*\('),
        "method": re.compile(r'^\s+def\s+(\w+)\s*\('),
        "middleware": re.compile(r'(?:@app\.(?:before_request|after_request)|middleware)'),
    },
    ".rs": {
        "entry_func": re.compile(r'^fn\s+(main)\s*\('),
        "interface": re.compile(r'^trait\s+(\w+)\s*\{'),
        "struct": re.compile(r'^(?:struct|enum)\s+(\w+)(?:<[^>]+>)?\s*\{'),
        "factory": re.compile(r'^fn\s+(new_\w+|build_\w+)\s*\('),
        "method": re.compile(r'^\s+fn\s+(\w+)\s*\('),
        "middleware": re.compile(r'(?:tower|axum|middleware|layer)'),
    },
    ".java": {
        "entry_func": re.compile(r'public\s+static\s+void\s+main\s*\('),
        "interface": re.compile(r'(?:public\s+)?interface\s+(\w+)\s*\{'),
        "struct": re.compile(r'(?:public\s+)?(?:class|record)\s+(\w+)\s*\{'),
        "factory": re.compile(r'(?:public\s+)?static\s+\w+\s+(?:create|build|new)\w*\s*\('),
        "method": re.compile(r'(?:public|private|protected)\s+\w+\s+(\w+)\s*\('),
        "middleware": re.compile(r'(?:Filter|Interceptor|HandlerInterceptor)'),
    },
    ".ts": {
        "entry_func": re.compile(r'(?:export\s+)?(?:async\s+)?function\s+(main)\s*\('),
        "interface": re.compile(r'(?:export\s+)?interface\s+(\w+)\s*\{'),
        "struct": re.compile(r'(?:export\s+)?(?:class|type)\s+(\w+)\s*[\{=]'),
        "factory": re.compile(r'(?:export\s+)?(?:function|const)\s+(?:create|build|make|new)\w*\s*[:=]'),
        "method": re.compile(r'(?:async\s+)?(\w+)\s*\([^)]*\)\s*[:{]'),
        "middleware": re.compile(r'(?:app\.(?:use|get|post|put|delete)|middleware)'),
    },
}


def extract_arch_elements(repo_path: str) -> dict:
    repo_path = os.path.abspath(repo_path)

    results = {
        "entry_points": [],
        "interfaces": [],
        "core_structs": [],
        "factories": [],
        "methods_by_struct": defaultdict(list),
        "middleware_patterns": [],
        "config_files": [],
    }

    for root, dirs, files in os.walk(repo_path):
        submodule_paths = get_submodule_paths(repo_path)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and d not in submodule_paths]

        for fname in files:
            ext = os.path.splitext(fname)[1]
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, repo_path)

            # 记录配置文件
            if fname in ("go.mod", "package.json", "Cargo.toml", "pyproject.toml",
                         "pom.xml", "build.gradle", "Dockerfile", "docker-compose.yml",
                         "Makefile", "CMakeLists.txt"):
                results["config_files"].append(rel_path)
                continue

            if ext not in PATTERNS:
                continue

            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue

            patterns = PATTERNS[ext]
            current_struct = None

            for i, line in enumerate(lines, 1):
                # 入口函数
                if patterns["entry_func"].search(line):
                    results["entry_points"].append({
                        "file": rel_path, "line": i,
                        "name": "main" if ext != ".py" else "__main__",
                        "type": "entry_point"
                    })

                # 接口 / trait / abstract class
                m = patterns["interface"].search(line)
                if m:
                    name = m.group(1) or m.group(2) if m.lastindex and m.lastindex > 1 else m.group(1)
                    if name:
                        results["interfaces"].append({
                            "file": rel_path, "line": i,
                            "name": name, "language": ext.lstrip(".")
                        })

                # 结构体 / class
                m = patterns["struct"].search(line)
                if m:
                    name = m.group(1)
                    current_struct = name
                    results["core_structs"].append({
                        "file": rel_path, "line": i,
                        "name": name, "language": ext.lstrip(".")
                    })

                # 工厂函数
                m = patterns["factory"].search(line)
                if m:
                    results["factories"].append({
                        "file": rel_path, "line": i,
                        "name": m.group(1) if m.groups() else "factory",
                        "language": ext.lstrip(".")
                    })

                # 方法（关联到当前结构体）
                if current_struct and "method" in patterns:
                    m = patterns["method"].search(line)
                    if m:
                        results["methods_by_struct"][current_struct].append({
                            "file": rel_path, "line": i,
                            "name": m.group(1)
                        })

                # 中间件模式
                if patterns["middleware"].search(line):
                    results["middleware_patterns"].append({
                        "file": rel_path, "line": i,
                        "snippet": line.strip()[:80]
                    })

                # 结构体结束，重置当前结构体
                if line.strip() == "}" and current_struct:
                    current_struct = None

    # 去重和排序
    for key in ("entry_points", "interfaces", "core_structs", "factories"):
        seen = set()
        unique = []
        for item in results[key]:
            identifier = (item["file"], item["name"])
            if identifier not in seen:
                seen.add(identifier)
                unique.append(item)
        results[key] = unique

    # 转换 defaultdict
    results["methods_by_struct"] = dict(results["methods_by_struct"])

    # 统计摘要
    results["summary"] = {
        "entry_points": len(results["entry_points"]),
        "interfaces": len(results["interfaces"]),
        "core_structs": len(results["core_structs"]),
        "factories": len(results["factories"]),
        "middleware_sites": len(results["middleware_patterns"]),
        "config_files": len(results["config_files"]),
    }

    return results


def main():
    parser = argparse.ArgumentParser(description="提取代码库中的架构元素")
    parser.add_argument("repo_path", help="仓库本地路径")
    parser.add_argument("--output", "-o", default="arch.json", help="输出 JSON 文件路径")
    args = parser.parse_args()

    if not os.path.isdir(args.repo_path):
        print(f"错误: {args.repo_path} 不是有效目录")
        return 1

    print(f"正在扫描: {args.repo_path} ...")
    result = extract_arch_elements(args.repo_path)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"扫描完成!")
    print(f"  入口点: {result['summary']['entry_points']}")
    print(f"  接口/trait: {result['summary']['interfaces']}")
    print(f"  核心结构体/类: {result['summary']['core_structs']}")
    print(f"  工厂函数: {result['summary']['factories']}")
    print(f"  配置文件: {result['summary']['config_files']}")
    print(f"  输出: {args.output}")
    return 0


if __name__ == "__main__":
    exit(main())
