#!/usr/bin/env python3
"""
跨语言模块依赖分析器
扫描代码库中的 import/include/use 语句，生成模块间依赖关系图

用法:
    python analyze_deps.py <repo_path> [--output deps.json]

输出 JSON 结构:
{
  "modules": {
    "pkg/a": {"files": [...], "imports": [...], "imported_by": [...]},
    ...
  },
  "edges": [{"from": "pkg/a", "to": "pkg/b", "count": 3}, ...],
  "stats": {"total_modules": N, "total_edges": M, "cyclic_deps": [...]}
}
"""

import os
import re
import json
import argparse
from collections import defaultdict, Counter
from pathlib import Path

# 语言配置: 文件扩展名 + import 语句正则
LANG_CONFIG = {
    ".go": {
        "regex": re.compile(r'^\s*import\s+(?:\(\s*)?(?:\w+\s+)?["\']([^"\']+)["\']', re.MULTILINE),
        "internal_only": True,
    },
    ".py": {
        "regex": re.compile(r'^\s*(?:from|import)\s+([\w.]+)', re.MULTILINE),
        "internal_only": True,
    },
    ".rs": {
        "regex": re.compile(r'^\s*(?:use|extern\s+crate)\s+([\w:]+)', re.MULTILINE),
        "internal_only": True,
    },
    ".js": {
        "regex": re.compile(r'(?:import\s+.*?\s+from\s+["\']|require\(["\'])([^"\']+)["\']', re.MULTILINE),
        "internal_only": False,
    },
    ".ts": {
        "regex": re.compile(r'(?:import\s+.*?\s+from\s+["\']|require\(["\'])([^"\']+)["\']', re.MULTILINE),
        "internal_only": False,
    },
    ".java": {
        "regex": re.compile(r'^\s*import\s+([\w.]+)', re.MULTILINE),
        "internal_only": True,
    },
}

SKIP_DIRS = {
    ".git", "vendor", "node_modules", "target", "dist", "build",
    ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    "*.egg-info", ".idea", ".vscode"
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


def is_internal_import(repo_path: str, import_path: str) -> bool:
    """判断 import 是否指向仓库内部模块"""
    # 过滤标准库和第三方库的常见特征
    external_markers = [
        "github.com/", "golang.org/", "google.golang.org/",
        "npm:", "https://", "http://", "./", "../"
    ]
    # 相对路径是内部的
    if import_path.startswith("./") or import_path.startswith("../"):
        return True
    # 绝对路径可能是内部的（如 Go 的 module path）
    repo_name = os.path.basename(repo_path)
    if repo_name in import_path:
        return True
    return False


def get_module_name(repo_path: str, file_path: str) -> str:
    """从文件路径推断模块名"""
    rel = os.path.relpath(file_path, repo_path)
    # 去掉文件名，保留目录路径作为模块名
    module = os.path.dirname(rel)
    # 标准化路径分隔符
    module = module.replace(os.sep, "/")
    # 处理常见语言的特殊目录结构
    parts = module.split("/")
    if parts and parts[0] in ("src", "lib", "pkg", "internal", "cmd", "app"):
        module = "/".join(parts[1:]) if len(parts) > 1 else parts[0]
    return module if module else "."


def analyze_repo(repo_path: str) -> dict:
    repo_path = os.path.abspath(repo_path)
    modules = defaultdict(lambda: {"files": [], "imports": Counter(), "imported_by": Counter()})
    all_edges = []

    for root, dirs, files in os.walk(repo_path):
        # 跳过无关目录
        submodule_paths = get_submodule_paths(repo_path)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and d not in submodule_paths]

        for fname in files:
            ext = os.path.splitext(fname)[1]
            if ext not in LANG_CONFIG:
                continue

            fpath = os.path.join(root, fname)
            cfg = LANG_CONFIG[ext]
            module = get_module_name(repo_path, fpath)
            modules[module]["files"].append(os.path.relpath(fpath, repo_path))

            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue

            for match in cfg["regex"].finditer(content):
                imp = match.group(1).strip()
                if not imp:
                    continue

                # 清理 Python 相对导入
                if ext == ".py":
                    if imp.startswith("."):
                        # 相对导入，保留
                        pass
                    else:
                        # from xxx.yyy import zzz -> 取 xxx.yyy
                        pass

                # 过滤外部依赖
                if cfg["internal_only"] and not is_internal_import(repo_path, imp):
                    continue

                # 将 import 映射到模块名
                target_module = imp.replace(".", "/").replace("::", "/")
                # 去掉最后的具体名称（如函数名）
                target_module = os.path.dirname(target_module) if "/" in target_module else target_module
                if not target_module:
                    continue

                modules[module]["imports"][target_module] += 1
                all_edges.append((module, target_module))

    # 构建反向依赖
    for mod_name, data in modules.items():
        for imp_mod in data["imports"]:
            if imp_mod in modules:
                modules[imp_mod]["imported_by"][mod_name] += data["imports"][imp_mod]

    # 构建边列表
    edge_counter = Counter(all_edges)
    edges = [
        {"from": f, "to": t, "count": c}
        for (f, t), c in edge_counter.most_common()
        if f != t  # 过滤自引用
    ]

    # 检测循环依赖（简单 DFS）
    def find_cycles():
        graph = defaultdict(set)
        for e in edges:
            graph[e["from"]].add(e["to"])
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path + [neighbor])
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(" -> ".join(cycle))
            rec_stack.remove(node)

        for node in list(graph.keys()):
            if node not in visited:
                dfs(node, [node])
        return list(set(cycles))[:10]  # 最多返回 10 个

    # 统计信息
    result = {
        "repo_path": repo_path,
        "modules": {
            k: {
                "file_count": len(v["files"]),
                "imports": dict(v["imports"]),
                "imported_by": dict(v["imported_by"]),
                "files": v["files"][:5]  # 最多展示 5 个文件
            }
            for k, v in sorted(modules.items()) if v["files"]
        },
        "edges": edges[:200],  # 最多 200 条边
        "stats": {
            "total_files_analyzed": sum(len(v["files"]) for v in modules.values()),
            "total_modules": len([m for m in modules.values() if m["files"]]),
            "total_edges": len(edges),
            "cyclic_deps": find_cycles(),
            "top_imported": [
                {"module": m, "count": sum(v["imported_by"].values())}
                for m, v in sorted(modules.items(), key=lambda x: sum(x[1]["imported_by"].values()), reverse=True)
                if sum(v["imported_by"].values()) > 0
            ][:10]
        }
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="分析代码库模块依赖关系")
    parser.add_argument("repo_path", help="仓库本地路径")
    parser.add_argument("--output", "-o", default="deps.json", help="输出 JSON 文件路径")
    args = parser.parse_args()

    if not os.path.isdir(args.repo_path):
        print(f"错误: {args.repo_path} 不是有效目录")
        return 1

    print(f"正在分析: {args.repo_path} ...")
    result = analyze_repo(args.repo_path)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"分析完成!")
    print(f"  模块数: {result['stats']['total_modules']}")
    print(f"  文件数: {result['stats']['total_files_analyzed']}")
    print(f"  依赖边: {result['stats']['total_edges']}")
    print(f"  循环依赖: {len(result['stats']['cyclic_deps'])}")
    print(f"  输出: {args.output}")
    return 0


if __name__ == "__main__":
    exit(main())
