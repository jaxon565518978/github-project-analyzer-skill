# GitHub 开源项目分析器 — 示例

## 示例 1：完整深度分析（Go CLI 工具）

**用户输入**："帮我深度分析一下 ~/projects/cobra"

**前置条件**：用户已执行 `git clone https://github.com/spf13/cobra ~/projects/cobra`

**Agent 执行步骤**：

### 步骤 1–2：验证与自动化扫描
```bash
python scripts/analyze_deps.py ~/projects/cobra --output /tmp/cobra_deps.json
python scripts/analyze_arch.py ~/projects/cobra --output /tmp/cobra_arch.json
```

**deps.json 关键发现**：
- 模块数：12，无循环依赖
- `command.go` 被引用次数最多（核心引擎）
- `doc/` 模块仅被 `command.go` 引用（叶子模块）

**arch.json 关键发现**：
- 入口：`cobra.go` 中的 main（示例程序）
- 接口：`Commander`、`FlagErrorFunc` 等 5 个接口
- 核心结构体：`Command`（含 30+ 字段）
- 工厂函数：`NewCommand`、`AddCommand` 等

### 步骤 3–5：架构反推五步法

**入口分析**：
- 从 `cobra.go` 入口追踪 → `Command.Execute()` → `preRun`/`run`/`postRun` 生命周期

**接口分析**：
- `Commander` 接口仅 1 个方法，粒度极细 → 符合接口隔离原则
- 用 `grep "type.*interface"` 找到所有接口，确认无接口膨胀

**数据流分析**（以 `cobra run` 为例）：
- CLI 输入 → `args` 解析 → `flags` 绑定 → `Command.Run` 执行 → 帮助信息/错误输出

**依赖分析**（基于 deps.json）：
- `command.go` 是"上帝模块"（被所有模块依赖）
- `doc/` 和 `shell_completions.go` 是叶子模块
- 无循环依赖，架构干净

**配置分析**：
- 无外部配置文件，纯代码组装
- 通过 `Command` 结构体字段和钩子函数实现配置

### 步骤 6–8：模块与创新点

- **命令引擎**：命令模式 + 构建者模式
- **持久标志继承**：创新的层级配置机制，通过 `PersistentFlags` 字段实现
- **Shell 补全生成**：自动生成 bash/zsh/fish/pwsh 补全脚本

**报告输出**：完整的 Markdown 报告，包含 mermaid 依赖图和量化数据

---

## 示例 2：中大型项目并行分析（TiKV）

**用户输入**："深度分析 ~/projects/tikv，用并行方式"

**Agent 执行**：

1. **全局扫描**（串行）：
   ```bash
   python scripts/analyze_deps.py ~/projects/tikv --output /tmp/tikv_deps.json
   python scripts/analyze_arch.py ~/projects/tikv --output /tmp/tikv_arch.json
   ```

2. **架构反推五步法**（串行）：识别出 6 个核心模块批次

3. **并行派生子 agent**（3 个批次并行）：

   - **批次 A**（共识层）：`raftstore`、`raft`
   - **批次 B**（存储层）：`storage`、`engine_rocks`、`engine_traits`
   - **批次 C**（计算层）：`coprocessor`、`tidb_query`

   每个子 agent 接收：模块路径 + deps.json 切片 + arch.json 切片

4. **汇总整合**：合并所有子 agent 输出，检查模块间接口一致性

---

## 示例 3：代码考古学分析

**用户输入**："分析一下 ~/projects/kubernetes 的架构演进"

**Agent 额外执行代码考古**：

```bash
# 查找最活跃的文件（架构热点）
git log --pretty=format: --name-only | sort | uniq -c | sort -rg | head -20

# 查找重大重构记录
git log --oneline --grep="refactor\|rewrite" -30

# 查看 controller 模块的演变
git log --oneline --follow -- pkg/controller/
```

**考古发现**：
- `pkg/controller/` 从单一文件逐渐拆分为多个独立 controller
- 2016 年的某次提交引入了 informer 机制，统一了资源监听模式
- 部分早期模块（如 `pkg/client/deprecated`）成为历史包袱，仍被引用但已标记废弃

---

## 示例 4：快速概览（跳过深度分析）

**用户输入**："快速看一下 ~/projects/next.js"

**Agent 执行**：
1. 运行 `analyze_arch.py`（仅 10 秒）
2. 基于扫描结果直接输出：
   - 入口：`packages/next/src/bin/next.ts`
   - 核心结构体：`NextServer`、`DevServer`
   - 配置文件：`next.config.js` 驱动
   - 技术栈：TypeScript + React + Webpack/Turbopack

**输出**：1 页 bullet 摘要，无需人工逐文件阅读
