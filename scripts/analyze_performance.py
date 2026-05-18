#!/usr/bin/env python3
"""
动态性能分析器
识别性能热点、并发模式、内存分配痕迹、优化手段

用法:
    python analyze_performance.py <repo_path> [--output perf.json]

输出 JSON:
{
  "benchmarks": [{"file": "...", "name": "BenchmarkXxx", "language": "go"}, ...],
  "concurrency_patterns": [{"file": "...", "pattern": "goroutine", "count": N}, ...],
  "memory_patterns": [{"file": "...", "pattern": "large_alloc", "detail": "..."}, ...],
  "optimizations": [{"file": "...", "pattern": "simd", "detail": "..."}, ...],
  "hot_paths": [{"file": "...", "function": "...", "calls": [...]}, ...]
}
"""

import os
import re
import json
import argparse
from collections import defaultdict, Counter

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


# 各语言的并发模式
CONCURRENCY_PATTERNS = {
    ".go": {
        "goroutine": re.compile(r'\bgo\s+\w+\s*\('),
        "channel": re.compile(r'\bmake\s*\(\s*chan\s+'),
        "mutex": re.compile(r'\b(sync\.Mutex|sync\.RWMutex|sync\.Map)\b'),
        "waitgroup": re.compile(r'\b sync\.WaitGroup\b'),
        "context": re.compile(r'\bcontext\.With\w*\('),
        "atomic": re.compile(r'\bsync/atomic\b'),
    },
    ".py": {
        "threading": re.compile(r'\bthreading\.(Thread|Lock|RLock)'),
        "asyncio": re.compile(r'\basyncio\.(run|gather|create_task)'),
        "multiprocessing": re.compile(r'\bmultiprocessing\.(Process|Pool)'),
        "concurrent_futures": re.compile(r'\bconcurrent\.futures\b'),
        "queue": re.compile(r'\bQueue\b'),
    },
    ".rs": {
        "thread": re.compile(r'\bstd::thread::spawn\b'),
        "async": re.compile(r'\basync\s+fn\b|\bawait\b'),
        "mutex": re.compile(r'\bMutex\b|\bRwLock\b'),
        "channel": re.compile(r'\bmpsc\b|\boneshot\b'),
        "atomic": re.compile(r'\bAtomic\w+\b'),
        "rayon": re.compile(r'\brayon\b'),
    },
    ".java": {
        "thread": re.compile(r'\bnew\s+Thread\s*\('),
        "executor": re.compile(r'\bExecutor\w*\b'),
        "synchronized": re.compile(r'\bsynchronized\b'),
        "concurrent": re.compile(r'\bjava\.util\.concurrent\b'),
        "volatile": re.compile(r'\bvolatile\b'),
    },
    ".ts": {
        "promise": re.compile(r'\bnew\s+Promise\b|\bPromise\.(all|race)\b'),
        "async_await": re.compile(r'\basync\b|\bawait\b'),
        "worker": re.compile(r'\bWorker\b|\bworker_threads\b'),
        "setimmediate": re.compile(r'\bsetImmediate\b'),
    },
}

# 内存分配模式
ALLOCATION_PATTERNS = {
    ".go": [
        ("make_slice", re.compile(r'\bmake\s*\(\s*\[\]' ), "medium"),
        ("make_map", re.compile(r'\bmake\s*\(\s*map\[' ), "medium"),
        ("large_buffer", re.compile(r'\bmake\s*\(\s*\[\]byte\s*,\s*(\d{5,})\b' ), "high"),
        ("append_in_loop", re.compile(r'for\s+.*\{[^}]*\bappend\b' ), "medium"),
    ],
    ".py": [
        ("list_comprehension", re.compile(r'\[.*for.*\]' ), "low"),
        ("deep_copy", re.compile(r'\b(copy\.deepcopy|deepcopy)\b' ), "medium"),
        ("large_list", re.compile(r'\b(range|list)\s*\(\s*(\d{5,})\b' ), "high"),
    ],
    ".rs": [
        ("vec_new", re.compile(r'\bVec::new\b|\bvec!\[' ), "low"),
        ("box_alloc", re.compile(r'\bBox::new\b' ), "medium"),
        ("large_vec", re.compile(r'\bvec!\[.*;\s*(\d{5,})\]' ), "high"),
    ],
    ".java": [
        ("arraylist", re.compile(r'\bnew\s+ArrayList\b' ), "low"),
        ("hashmap", re.compile(r'\bnew\s+HashMap\b' ), "low"),
        ("large_allocation", re.compile(r'\bnew\s+byte\[\s*(\d{5,})\s*\]' ), "high"),
    ],
}

# 性能优化关键词
OPTIMIZATION_PATTERNS = {
    "simd": re.compile(r'\bsimd\b|\bSIMD\b|\bAVX\b|\bSSE\b', re.IGNORECASE),
    "zero_copy": re.compile(r'\bzero[-_]?copy\b|\bmmap\b|\bsendfile\b|\bsplice\b', re.IGNORECASE),
    "lock_free": re.compile(r'\block[-_]?free\b|\bwait[-_]?free\b', re.IGNORECASE),
    "buffer_pool": re.compile(r'\bsync\.Pool\b|\bBufferPool\b|\bbytepool\b|\bobject.?pool\b', re.IGNORECASE),
    "unsafe": re.compile(r'\bunsafe\b'),
    "arena": re.compile(r'\barena\b|\bArena\b|\bBumpAlloc\b'),
    "cache": re.compile(r'\bcache\b|\bCache\b|\blru\b|\blfu\b', re.IGNORECASE),
    "batch": re.compile(r'\bbatch\b|\bBatch\b|\bbulk\b', re.IGNORECASE),
    "pprof": re.compile(r'\bpprof\b|\bprofile\b|\bflamegraph\b', re.IGNORECASE),
}

# Benchmark 检测
BENCHMARK_PATTERNS = {
    ".go": re.compile(r'^func\s+(Benchmark\w+)\s*\('),
    ".py": re.compile(r'^\s*def\s+(test_\w+)\s*\('),  # pytest 中也可作为性能测试
    ".rs": re.compile(r'#\[bench\]'),
    ".java": re.compile(r'@Benchmark'),
    ".ts": re.compile(r'\b Benchmark\b'),
}


def analyze_repo(repo_path):
    repo_path = os.path.abspath(repo_path)
    benchmarks = []
    concurrency = defaultdict(lambda: defaultdict(int))
    memory = []
    optimizations = defaultdict(list)

    for root, dirs, files in os.walk(repo_path):
        submodule_paths = get_submodule_paths(repo_path)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and d not in submodule_paths]
        for fname in files:
            ext = os.path.splitext(fname)[1]
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, repo_path)

            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue

            content = "".join(lines)

            # Benchmark 检测
            if ext in BENCHMARK_PATTERNS:
                for i, line in enumerate(lines, 1):
                    m = BENCHMARK_PATTERNS[ext].search(line)
                    if m:
                        benchmarks.append({
                            "file": rel, "line": i,
                            "name": m.group(1) if m.groups() else "benchmark",
                            "language": ext.lstrip(".")
                        })

            # 并发模式检测
            if ext in CONCURRENCY_PATTERNS:
                for pattern_name, pattern in CONCURRENCY_PATTERNS[ext].items():
                    count = len(pattern.findall(content))
                    if count > 0:
                        concurrency[ext][pattern_name] += count

            # 内存分配检测
            if ext in ALLOCATION_PATTERNS:
                for i, line in enumerate(lines, 1):
                    for name, pattern, severity in ALLOCATION_PATTERNS[ext]:
                        if pattern.search(line):
                            memory.append({
                                "file": rel, "line": i,
                                "pattern": name,
                                "severity": severity,
                                "snippet": line.strip()[:80]
                            })

            # 性能优化关键词
            for opt_name, pattern in OPTIMIZATION_PATTERNS.items():
                for m in pattern.finditer(content):
                    # 找到行号
                    line_num = content[:m.start()].count('\n') + 1
                    line_content = lines[line_num - 1].strip() if line_num <= len(lines) else ""
                    optimizations[opt_name].append({
                        "file": rel, "line": line_num,
                        "snippet": line_content[:80]
                    })

    # 构建热点路径（基于 benchmark 附近的函数）
    hot_paths = []
    seen_files = set()
    for bm in benchmarks[:10]:
        if bm["file"] not in seen_files:
            seen_files.add(bm["file"])
            hot_paths.append({
                "file": bm["file"],
                "benchmark": bm["name"],
                "note": "性能测试覆盖的模块"
            })

    # 汇总并发模式
    concurrency_summary = {}
    for ext, patterns in concurrency.items():
        concurrency_summary[ext.lstrip(".")] = dict(patterns)

    return {
        "benchmarks": {
            "total": len(benchmarks),
            "by_language": dict(Counter(bm["language"] for bm in benchmarks)),
            "examples": benchmarks[:15],
        },
        "concurrency_patterns": concurrency_summary,
        "memory_allocations": {
            "total_findings": len(memory),
            "high_risk": len([m for m in memory if m["severity"] == "high"]),
            "examples": memory[:15],
        },
        "optimizations": {
            k: {"count": len(v), "examples": v[:5]}
            for k, v in sorted(optimizations.items(), key=lambda x: len(x[1]), reverse=True)
            if v
        },
        "hot_paths": hot_paths,
    }


def main():
    parser = argparse.ArgumentParser(description="动态性能分析器")
    parser.add_argument("repo_path", help="仓库本地路径")
    parser.add_argument("--output", "-o", default="perf.json", help="输出 JSON 文件路径")
    args = parser.parse_args()

    if not os.path.isdir(args.repo_path):
        print(f"错误: {args.repo_path} 不是有效目录")
        return 1

    print(f"正在分析性能特征: {args.repo_path} ...")
    result = analyze_repo(args.repo_path)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"分析完成!")
    print(f"  Benchmark 数量: {result['benchmarks']['total']}")
    print(f"  并发模式类型: {len(result['concurrency_patterns'])}")
    print(f"  内存分配痕迹: {result['memory_allocations']['total_findings']}")
    print(f"  优化手段: {len(result['optimizations'])}")
    print(f"  输出: {args.output}")
    return 0


if __name__ == "__main__":
    exit(main())
