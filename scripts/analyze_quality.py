#!/usr/bin/env python3
"""
代码质量分析器
检测测试覆盖率、代码异味、文档注释率、圈复杂度等指标
支持按语言动态调整阈值，自动跳过 git submodule

用法:
    python analyze_quality.py <repo_path> [--output quality.json]
"""

import os
import re
import json
import argparse
from collections import defaultdict, Counter

# ========== 按语言动态阈值配置 ==========
QUALITY_THRESHOLDS = {
    ".go": {
        "long_function": 60,      # Go 函数普遍较短
        "long_file": 400,
        "complexity_high": 15,
        "complexity_medium": 8,
        "comment_target": 40,     # Go 推荐 40%+
    },
    ".py": {
        "long_function": 50,      # Python 函数建议 < 50 行
        "long_file": 500,
        "complexity_high": 12,
        "complexity_medium": 7,
        "comment_target": 30,
    },
    ".rs": {
        "long_function": 50,      # Rust 函数较短
        "long_file": 400,
        "complexity_high": 12,
        "complexity_medium": 7,
        "comment_target": 35,
    },
    ".java": {
        "long_function": 60,      # Java 类方法可稍长
        "long_file": 600,         # Java 类文件天然较大
        "complexity_high": 15,
        "complexity_medium": 8,
        "comment_target": 35,
    },
    ".ts": {
        "long_function": 50,
        "long_file": 500,
        "complexity_high": 12,
        "complexity_medium": 7,
        "comment_target": 30,
    },
    ".js": {
        "long_function": 50,
        "long_file": 500,
        "complexity_high": 12,
        "complexity_medium": 7,
        "comment_target": 25,
    },
    ".c": {
        "long_function": 80,      # C 函数允许较长
        "long_file": 600,
        "complexity_high": 15,
        "complexity_medium": 8,
        "comment_target": 30,
    },
    ".cpp": {
        "long_function": 70,
        "long_file": 600,
        "complexity_high": 15,
        "complexity_medium": 8,
        "comment_target": 30,
    },
    ".h": {
        "long_function": 80,
        "long_file": 600,
        "complexity_high": 15,
        "complexity_medium": 8,
        "comment_target": 35,
    },
    ".hpp": {
        "long_function": 70,
        "long_file": 600,
        "complexity_high": 15,
        "complexity_medium": 8,
        "comment_target": 35,
    },
}

# 默认阈值（未知语言回退）
DEFAULT_THRESHOLDS = {
    "long_function": 60,
    "long_file": 500,
    "complexity_high": 15,
    "complexity_medium": 8,
    "comment_target": 30,
}

# ========== 目录过滤配置 ==========
SKIP_DIRS = {".git", "vendor", "node_modules", "target", "dist", "build",
             ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
             ".idea", ".vscode", "*.egg-info"}

CODE_EXTS = {".go", ".py", ".rs", ".java", ".ts", ".js", ".c", ".cpp", ".h", ".hpp"}

TEST_PATTERNS = [
    re.compile(r"_test\.go$"),
    re.compile(r"test_.*\.py$"),
    re.compile(r".*_test\.py$"),
    re.compile(r"tests?\.rs$"),
    re.compile(r".*Test\.java$"),
    re.compile(r".*\.spec\.(ts|js)$"),
    re.compile(r".*\.test\.(ts|js)$"),
]

BRANCH_KEYWORDS = re.compile(
    r'\b(if|else|elif|for|while|switch|case|catch|throw|'
    r'break|continue|return|goto|and|or|\|\||&&|\?\:)\b',
    re.IGNORECASE
)

FUNCTION_PATTERNS = {
    ".go": re.compile(r'^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\('),
    ".py": re.compile(r'^\s*def\s+(\w+)\s*\('),
    ".rs": re.compile(r'^\s*(?:async\s+)?fn\s+(\w+)\s*\('),
    ".java": re.compile(r'(?:public|private|protected)?\s*(?:static\s+)?\w+\s+(\w+)\s*\('),
    ".ts": re.compile(r'(?:export\s+)?(?:async\s+)?(?:function\s+)?(\w+)\s*\([^)]*\)\s*(?:\:|\{)'),
    ".js": re.compile(r'(?:async\s+)?(?:function\s+)?(\w+)\s*\([^)]*\)\s*(?:\{|=>)'),
}

COMMENT_PATTERNS = {
    ".go": re.compile(r'^\s*//'),
    ".py": re.compile(r'^\s*#|^\s*"""|^\s*\'\'\''),
    ".rs": re.compile(r'^\s*//|^\s*///|^\s*//!'),
    ".java": re.compile(r'^\s*//|^\s*/\*'),
    ".ts": re.compile(r'^\s*//|^\s*/\*'),
    ".js": re.compile(r'^\s*//|^\s*/\*'),
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


def is_test_file(fname):
    for pat in TEST_PATTERNS:
        if pat.search(fname):
            return True
    return False


def should_skip_dir(dname, submodule_paths):
    """判断目录是否应该跳过"""
    if dname in SKIP_DIRS:
        return True
    if dname.startswith("."):
        return True
    if dname.startswith(".git"):
        return True
    for sp in submodule_paths:
        if dname == os.path.basename(sp) or dname == sp.split("/")[0]:
            return True
    return False


def analyze_repo(repo_path):
    repo_path = os.path.abspath(repo_path)
    submodule_paths = get_submodule_paths(repo_path)
    source_files = []
    test_files = []
    smells = []
    complexity_data = []
    function_comments = {"commented": 0, "total": 0}
    mock_usage = Counter()

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not should_skip_dir(d, submodule_paths)]
        for fname in files:
            ext = os.path.splitext(fname)[1]
            if ext not in CODE_EXTS:
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, repo_path)

            if is_test_file(fname):
                test_files.append(rel)
            else:
                source_files.append(rel)

            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue

            # 测试文件中的 mock 检测
            if is_test_file(fname):
                content = "".join(lines)
                for m in re.finditer(r'\b(mock|stub|fake|spy|patch|Mock|Stub|Fake)\w*\b', content):
                    mock_usage[m.group(0)] += 1
                continue

            # 获取该语言的阈值配置
            thresholds = QUALITY_THRESHOLDS.get(ext, DEFAULT_THRESHOLDS)

            # 代码异味检测
            func_start = 0
            func_name = None
            func_lines = 0
            branches = 0
            has_doc = False

            comment_re = COMMENT_PATTERNS.get(ext)
            func_re = FUNCTION_PATTERNS.get(ext)

            for i, line in enumerate(lines):
                stripped = line.strip()

                if func_re:
                    m = func_re.match(stripped)
                    if m:
                        if func_name and func_lines > 0:
                            if func_lines > thresholds["long_function"]:
                                smells.append({
                                    "file": rel, "line": func_start,
                                    "type": "long_function",
                                    "detail": f"函数 {func_name} 有 {func_lines} 行（{ext} 建议 < {thresholds['long_function']}）"
                                })
                            if not has_doc:
                                function_comments["total"] += 1
                            else:
                                function_comments["commented"] += 1
                                function_comments["total"] += 1

                        func_start = i + 1
                        func_name = m.group(1)
                        func_lines = 0
                        branches = 0
                        has_doc = False
                        for j in range(max(0, i - 5), i):
                            if comment_re and comment_re.match(lines[j]):
                                has_doc = True
                                break

                if func_name:
                    func_lines += 1
                    if BRANCH_KEYWORDS.search(stripped):
                        branches += 1

            # 文件长度检测
            if len(lines) > thresholds["long_file"]:
                smells.append({
                    "file": rel, "line": 1,
                    "type": "long_file",
                    "detail": f"文件有 {len(lines)} 行（{ext} 建议 < {thresholds['long_file']}）"
                })

            # TODO/FIXME/HACK 检测
            for i, line in enumerate(lines):
                m = re.search(r'\b(TODO|FIXME|HACK|XXX|BUG)\b', line, re.IGNORECASE)
                if m:
                    smells.append({
                        "file": rel, "line": i + 1,
                        "type": "todo_marker",
                        "detail": f"发现 {m.group(1)}: {line.strip()[:60]}"
                    })

            # 圈复杂度估算
            if func_name and func_lines > 0:
                score = "low"
                if branches > thresholds["complexity_high"]:
                    score = "high"
                elif branches > thresholds["complexity_medium"]:
                    score = "medium"
                complexity_data.append({
                    "file": rel, "function": func_name,
                    "branches": branches, "lines": func_lines,
                    "score": score
                })

    # 汇总
    total_src = len(source_files)
    total_test = len(test_files)
    ratio = f"1:{total_src // max(total_test, 1)}" if total_test > 0 else "N/A"

    top_smells = Counter(s["type"] for s in smells)
    top_complex = sorted([c for c in complexity_data if c["score"] != "low"],
                         key=lambda x: x["branches"], reverse=True)[:20]

    comment_rate = 0
    if function_comments["total"] > 0:
        comment_rate = function_comments["commented"] / function_comments["total"] * 100

    return {
        "thresholds_used": {ext: QUALITY_THRESHOLDS.get(ext, DEFAULT_THRESHOLDS)
                            for ext in CODE_EXTS if ext in QUALITY_THRESHOLDS},
        "test_metrics": {
            "source_files": total_src,
            "test_files": total_test,
            "test_ratio": ratio,
            "mock_usage": dict(mock_usage.most_common(10)),
        },
        "documentation": {
            "commented_functions": function_comments["commented"],
            "total_functions": function_comments["total"],
            "comment_rate_percent": round(comment_rate, 1),
        },
        "code_smells": {
            "total": len(smells),
            "by_type": dict(top_smells.most_common(10)),
            "examples": smells[:15],
        },
        "complexity": {
            "high_risk_functions": len([c for c in complexity_data if c["score"] == "high"]),
            "medium_risk_functions": len([c for c in complexity_data if c["score"] == "medium"]),
            "top_complex": top_complex,
        }
    }


def main():
    parser = argparse.ArgumentParser(description="代码质量分析器")
    parser.add_argument("repo_path", help="仓库本地路径")
    parser.add_argument("--output", "-o", default="quality.json", help="输出 JSON 文件路径")
    args = parser.parse_args()

    if not os.path.isdir(args.repo_path):
        print(f"错误: {args.repo_path} 不是有效目录")
        return 1

    print(f"正在分析代码质量: {args.repo_path} ...")
    result = analyze_repo(args.repo_path)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"分析完成!")
    print(f"  源码文件: {result['test_metrics']['source_files']}")
    print(f"  测试文件: {result['test_metrics']['test_files']}")
    print(f"  测试比例: {result['test_metrics']['test_ratio']}")
    print(f"  代码异味: {result['code_smells']['total']}")
    print(f"  注释率: {result['documentation']['comment_rate_percent']}%")
    print(f"  输出: {args.output}")
    return 0


if __name__ == "__main__":
    exit(main())
