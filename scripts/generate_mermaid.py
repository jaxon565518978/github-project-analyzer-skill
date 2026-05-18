#!/usr/bin/env python3
"""
可视化生成器
将 deps.json 转换为 Mermaid 图表，提取 API 接口清单

用法:
    python generate_mermaid.py <deps.json> [--type deps|api] [--output diagram.mmd]

输出: Mermaid 语法文本或 API 接口 JSON
"""

import json
import argparse
import os


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


def generate_dependency_graph(deps_data, max_nodes=30):
    """从 deps.json 生成 Mermaid 依赖图"""
    modules = deps_data.get("modules", {})
    edges = deps_data.get("edges", [])

    # 选择最活跃的模块
    module_scores = {}
    for name, data in modules.items():
        imports = sum(data.get("imports", {}).values())
        imported_by = sum(data.get("imported_by", {}).values())
        module_scores[name] = imports + imported_by

    top_modules = sorted(module_scores.keys(), key=lambda x: module_scores[x], reverse=True)[:max_nodes]
    top_set = set(top_modules)

    lines = ["graph TD"]

    # 节点定义（按入度分组）
    for mod in top_modules:
        data = modules.get(mod, {})
        imported_by = sum(data.get("imported_by", {}).values())
        if imported_by > 5:
            lines.append(f'    {node_id(mod)}["{mod}"]')
        elif imported_by > 0:
            lines.append(f'    {node_id(mod)}["{mod}"]')
        else:
            lines.append(f'    {node_id(mod)}["{mod}"]')

    # 边定义
    edge_set = set()
    for edge in edges:
        src = edge.get("from", "")
        dst = edge.get("to", "")
        if src in top_set and dst in top_set and src != dst:
            key = (src, dst)
            if key not in edge_set:
                edge_set.add(key)
                count = edge.get("count", 1)
                lines.append(f'    {node_id(src)} -->|"{count}"| {node_id(dst)}')

    return "\n".join(lines)


def generate_api_summary(repo_path, max_apis=50):
    """扫描代码提取公开 API 接口"""
    import re

    SKIP_DIRS = {".git", "vendor", "node_modules", "target", "dist", "build",
                 ".venv", "venv", "__pycache__"}

    api_patterns = {
        ".go": re.compile(r'^func\s+([A-Z]\w+)\s*\([^)]*\)\s*(?:\([^)]*\)|\w+)?\s*\{'),
        ".py": re.compile(r'^\s*(?:async\s+)?def\s+([a-z_]\w*)\s*\('),
        ".rs": re.compile(r'^\s*pub\s+(?:async\s+)?fn\s+([a-z_]\w*)\s*\('),
        ".java": re.compile(r'(?:public\s+)(?:static\s+)?\w+\s+([a-zA-Z]\w*)\s*\('),
        ".ts": re.compile(r'(?:export\s+)?(?:async\s+)?(?:function\s+)?([a-zA-Z]\w*)\s*\([^)]*\)\s*[:{]'),
    }

    http_patterns = [
        re.compile(r'(?:Get|Post|Put|Delete|Patch|Head|Options)\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'@(?:Get|Post|Put|Delete|Patch|RequestMapping)\s*\(\s*["\']?([^"\']*)["\']?'),
        re.compile(r'\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'),
        re.compile(r'(?:app|router)\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'),
    ]

    apis = []
    routes = []

    for root, dirs, files in os.walk(repo_path):
        submodule_paths = get_submodule_paths(repo_path)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and d not in submodule_paths]
        for fname in files:
            ext = os.path.splitext(fname)[1]
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, repo_path)

            if ext not in api_patterns:
                continue

            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    lines = content.split("\n")
            except Exception:
                continue

            # 提取公开函数
            func_re = api_patterns.get(ext)
            if func_re:
                for i, line in enumerate(lines, 1):
                    m = func_re.match(line.strip())
                    if m:
                        name = m.group(1)
                        # 过滤私有/内部函数
                        if name.startswith("_") or "test" in name.lower():
                            continue
                        apis.append({
                            "file": rel, "line": i,
                            "name": name,
                            "type": "function",
                            "language": ext.lstrip(".")
                        })

            # 提取 HTTP 路由
            for pattern in http_patterns:
                for m in pattern.finditer(content):
                    route = m.group(1) if m.groups() else m.group(0)
                    if route and len(route) > 1:
                        routes.append({
                            "file": rel,
                            "route": route,
                            "method": "inferred"
                        })

    # 去重
    seen_apis = set()
    unique_apis = []
    for api in apis:
        key = (api["file"], api["name"])
        if key not in seen_apis:
            seen_apis.add(key)
            unique_apis.append(api)

    seen_routes = set()
    unique_routes = []
    for r in routes:
        key = (r["file"], r["route"])
        if key not in seen_routes:
            seen_routes.add(key)
            unique_routes.append(r)

    return {
        "functions": unique_apis[:max_apis],
        "http_routes": unique_routes[:max_apis],
        "summary": {
            "total_functions": len(unique_apis),
            "total_routes": len(unique_routes),
            "by_language": dict(__import__('collections').Counter(a["language"] for a in unique_apis))
        }
    }


def node_id(name):
    """将模块名转换为合法的 Mermaid 节点 ID"""
    return re.sub(r'[^a-zA-Z0-9_]', '_', name).strip('_')[:40]


import re


def main():
    parser = argparse.ArgumentParser(description="可视化生成器")
    parser.add_argument("input", help="输入文件（deps.json 或仓库路径）")
    parser.add_argument("--type", "-t", choices=["deps", "api"], default="deps",
                        help="生成类型：deps=依赖图, api=API 清单")
    parser.add_argument("--output", "-o", required=True, help="输出文件路径")
    parser.add_argument("--max-nodes", "-n", type=int, default=30, help="依赖图最大节点数")
    args = parser.parse_args()

    if args.type == "deps":
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        mermaid = generate_dependency_graph(data, max_nodes=args.max_nodes)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(mermaid)
        print(f"Mermaid 依赖图已生成: {args.output}")
        print(f"  节点数: {args.max_nodes}")

    elif args.type == "api":
        if not os.path.isdir(args.input):
            print(f"错误: API 模式需要目录路径")
            return 1
        api_data = generate_api_summary(args.input)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(api_data, f, ensure_ascii=False, indent=2)
        print(f"API 清单已生成: {args.output}")
        print(f"  函数数量: {api_data['summary']['total_functions']}")
        print(f"  HTTP 路由: {api_data['summary']['total_routes']}")

    return 0


if __name__ == "__main__":
    exit(main())
