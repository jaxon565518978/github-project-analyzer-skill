---
name: github-project-analyzer
description: Analyzes a locally cloned GitHub repository to extract the overall technical architecture, core modules, module-level design patterns, and innovative features. Use when the user provides a local directory path containing cloned open-source code and asks for project analysis, architecture review, technical breakdown, or wants to understand how the project is built. Also triggers when analyzing, reviewing, or dissecting source code that originated from GitHub.
---

# GitHub 开源项目分析器

## 概述

分析用户已下载到本地的 GitHub 仓库，结合自动化代码扫描工具与系统化架构反推方法论，产出一份全面的技术分析报告，涵盖整体架构、核心模块、模块级方案设计、创新点、代码质量、安全合规、性能特征与可视化架构图。

## 前置条件

用户必须已经将 GitHub 仓库克隆到本地目录。本 skill **不执行**克隆操作。

如果用户只提供了 GitHub URL 而没有本地路径，提示用户先运行 `git clone <url>`，完成后再将目录路径提供给本 skill。

## 工作流程

```
任务进度：
- [ ] 步骤 1：验证本地目录并获取元数据
- [ ] 步骤 2：运行自动化代码扫描工具
- [ ] 步骤 3：分析仓库结构与文件树
- [ ] 步骤 4：识别技术栈
- [ ] 步骤 5：通过架构反推五步法提炼设计
- [ ] 步骤 6：提取核心模块
- [ ] 步骤 7：分析每个核心模块的方案设计
- [ ] 步骤 8：识别创新点与差异化设计
- [ ] 步骤 9：代码质量分析
- [ ] 步骤 10：安全与合规扫描
- [ ] 步骤 11：性能特征分析
- [ ] 步骤 12：可视化与 API 提取
- [ ] 步骤 13：代码考古学（可选）
- [ ] 步骤 14：生成结构化报告
```

### 步骤 1：验证本地目录并获取元数据

1. 确认用户提供的本地路径存在且为目录
2. 检查 `.git/config` 确认其为 git 仓库
3. 从 `.git/config` 中提取 remote origin URL，得到 `owner/repo`
4. 如果系统安装了 `gh` CLI，可使用 `gh api repos/{owner}/{repo}` 获取：
   - 主要编程语言、topics、描述
   - Stars、Forks、Open Issues 数量
   - 创建/更新时间、License
5. 读取本地 `README.md`（或其他 `.md` 变体）
6. 若仓库关联了 wiki 或文档站点，一并记录

### 步骤 2：运行自动化代码扫描工具

在步骤 3 之前，先运行以下脚本获取量化数据：

```bash
# 模块依赖分析：模块间 import 关系、入度/出度、循环依赖
python scripts/analyze_deps.py <repo_path> --output /tmp/deps.json

# 架构元素提取：入口、接口、核心结构体、工厂函数、中间件、配置
python scripts/analyze_arch.py <repo_path> --output /tmp/arch.json

# 代码质量分析：测试比例、代码异味、注释率、圈复杂度
python scripts/analyze_quality.py <repo_path> --output /tmp/quality.json

# 安全与合规扫描：敏感信息、许可证、安全漏洞模式
python scripts/analyze_security.py <repo_path> --output /tmp/security.json

# 性能特征分析：benchmark、并发模式、内存分配、优化手段
python scripts/analyze_performance.py <repo_path> --output /tmp/perf.json
```

**解读 deps.json**：
- `stats.total_modules`：模块数量，反映项目规模
- `stats.cyclic_deps`：循环依赖列表，暴露架构耦合问题
- `stats.top_imported`：被引用最多的模块，通常是核心基础设施
- `edges`：模块间调用关系，用于绘制依赖图

**解读 arch.json**：
- `entry_points`：程序入口，理解启动流程
- `interfaces`：抽象接口列表，理解扩展点和契约
- `core_structs`：核心数据结构，理解状态模型
- `factories`：工厂函数列表，理解对象创建模式
- `middleware_patterns`：中间件使用痕迹，理解请求管道
- `config_files`：配置文件清单，理解系统组装方式

**解读 quality.json**：
- `test_metrics`：测试文件比例、mock 使用模式
- `code_smells`：过长函数、过长文件、TODO/FIXME 标记
- `documentation.comment_rate_percent`：函数注释覆盖率
- `complexity`：高/中风险函数列表（基于分支语句估算）

**解读 security.json**：
- `secrets`：潜在敏感信息泄露（密钥、token、密码）
- `security_patterns`：SQL 注入、eval、unsafe、shell 注入等漏洞模式
- `license_compatibility`：项目许可证及依赖许可证分布
- `dependency_risks`：不稳定版本或需审查的依赖

**解读 perf.json**：
- `benchmarks`：性能测试覆盖情况
- `concurrency_patterns`：goroutine、thread、async/await、mutex 等使用统计
- `memory_allocations`：大对象分配、循环内 append 等高风险内存模式
- `optimizations`：simd、zero-copy、lock-free、buffer pool 等优化手段

### 步骤 3：分析仓库结构与文件树

1. 使用本地文件工具列出根目录内容
2. 深入探索关键目录：`src/`、`lib/`、`pkg/`、`core/`、`internal/`、`cmd/` 等
3. 查找与架构相关的文件：
   - `ARCHITECTURE.md`、`DESIGN.md`、`docs/architecture/`
   - `docker-compose.yml`、`Dockerfile`、`k8s/`（部署拓扑）
   - `go.mod`、`package.json`、`Cargo.toml`、`pyproject.toml`（依赖信息）
4. 记录顶层目录及其 apparent 角色
5. 对于超大仓库，使用 `find` 并限制深度

### 步骤 3.5：项目类型自动检测

根据仓库特征自动判断项目类型，后续报告章节将据此调整：

**检测逻辑（按优先级匹配）**：

1. **CLI/工具**：满足任一条件即判定
   - 存在 `cmd/` 目录且包含子命令入口
   - `package.json` 中有 `"bin"` 字段
   - `arch.json` 中 main 入口解析命令行参数（flag/arg/cobra 等）
   - README 以命令行用法为主，无 HTTP/服务相关描述

2. **服务/后端**：满足任一条件即判定
   - 存在 `Dockerfile` / `docker-compose.yml` / `k8s/`
   - 依赖包含 web 框架（gin、express、fastapi、spring-boot、axum 等）
   - `arch.json` 中有 HTTP handler / server 启动痕迹
   - 存在数据库连接配置或 ORM 依赖

3. **库/SDK**：不满足 CLI 和服务特征，且满足任一条件
   - `package.json` 中有 `"main"` / `"module"` / `"types"` 字段
   - `Cargo.toml` 中有 `[lib]` 段
   - `setup.py` / `pyproject.toml` 中声明为 library
   - 存在大量公开接口但无 main 入口

4. **不确定/通用**：以上均不匹配时回退到通用模板

### 步骤 4：识别技术栈

基于已收集的数据，整理以下内容：

- **主要编程语言** 与运行时
- **框架与库**（从依赖文件中提取）
- **构建工具**（Makefile、CMake、Bazel、Vite、Webpack 等）
- **基础设施**：容器化、编排、CI/CD（`.github/workflows/`）
- **数据存储**：数据库、缓存、消息队列（从依赖和配置中推断）

### 步骤 5：架构反推五步法

不要仅依赖 README 的描述，而是**从代码中反推真实的架构设计**：

**5.1 入口分析法**：从 `arch.json` 的 `entry_points` 出发，追踪初始化顺序、配置加载、依赖注入方式。

**5.2 接口分析法**：从 `arch.json` 的 `interfaces` 出发，分析契约粒度、实现者分布、接口分离程度。

**5.3 数据流分析法**：选取一个典型请求，端到端追踪输入层→处理层→存储层→输出层，标记每层数据形态变化。

**5.4 依赖分析法**：从 `deps.json` 出发，绘制模块依赖图，识别上帝模块、边缘模块、循环依赖。

**5.5 配置分析法**：从 `arch.json` 的 `config_files` 出发，理解系统组装方式、中间件注册、特性开关。

### 步骤 6：提取核心模块

结合自动化扫描与人工判断：

- `deps.json` 中的模块名和依赖关系
- `arch.json` 中的接口和结构体归属
- 顶层目录或 `src/`、`pkg/`、`internal/` 下的目录名
- README 中描述组件的章节

对每个核心模块记录：名称、位置、职责、关键文件、入度/出度、依赖关系。

### 步骤 7：分析每个核心模块的方案设计

对照代码特征识别设计模式（见 [reference.md](reference.md) 中的设计模式特征库），分析数据流、抽象层、扩展性。

### 步骤 8：识别创新点与差异化设计

结合扫描结果与人工分析，验证创新点的真实性（非 README 营销话术）。

### 步骤 9：代码质量分析

基于 `quality.json` 的量化数据，产出质量评估：

- **测试健康度**：测试比例是否合理？mock 使用是否过度？是否缺少集成测试？
- **代码异味分布**：过长函数集中在哪些模块？TODO/FIXME 是否堆积？
- **文档覆盖率**：注释率低于 30% 的模块需要重点关注
- **复杂度热点**：圈复杂度高的函数是否是核心业务逻辑？是否可以通过重构降低？

### 步骤 10：安全与合规扫描

基于 `security.json` 产出安全评估：

- **敏感信息**：是否有硬编码密钥/token？（即使是测试文件也需标注）
- **漏洞模式**：是否存在 SQL 注入、eval、unsafe 代码？是否在合理范围内使用？
- **许可证风险**：项目许可证是什么？依赖中是否有 GPL 等传染性许可证？
- **依赖安全**：是否有 0.x 版本或明显过时的依赖？

### 步骤 11：性能特征分析

基于 `perf.json` 产出性能画像：

- **Benchmark 覆盖**：哪些模块有性能测试？是否覆盖了热点路径？
- **并发策略**：使用哪种并发模型？锁的粒度是否合理？是否有 race condition 风险？
- **内存特征**：是否存在大对象分配、循环内频繁 append、深拷贝等模式？
- **优化手段**：是否使用了 zero-copy、SIMD、buffer pool、unsafe 等高级优化？权衡是什么？

### 步骤 12：可视化与 API 提取

生成架构可视化产出：

```bash
# 从 deps.json 生成 Mermaid 依赖图
python scripts/generate_mermaid.py /tmp/deps.json --type deps --output /tmp/deps.mmd

# 从源码提取公开 API 清单
python scripts/generate_mermaid.py <repo_path> --type api --output /tmp/api.json
```

将 Mermaid 依赖图嵌入报告。从 `api.json` 中提取 HTTP 路由和公开函数，评估 API 设计的 RESTful 程度、一致性、版本管理策略。

### 步骤 13：代码考古学（可选）

对于历史悠久或架构复杂的项目：

```bash
# 最活跃文件（架构热点）
git log --pretty=format: --name-only | sort | uniq -c | sort -rg | head -30
# 重大重构记录
git log --oneline --grep="refactor\|rewrite" -30
# 文件演变历史
git log --oneline --follow -- <file>
```

回答：哪些模块是后来追加的？是否存在历史包袱？架构是否经历过重大转型？

### 步骤 14：生成报告

根据步骤 3.5 检测到的项目类型，选择对应的报告模板：

| 项目类型 | 使用模板 | 侧重维度 |
|----------|----------|----------|
| 库 / SDK | [REPORT_TEMPLATE_LIB.md](REPORT_TEMPLATE_LIB.md) | API 设计、扩展性、兼容性、使用示例 |
| 服务 / 后端 | [REPORT_TEMPLATE_SERVICE.md](REPORT_TEMPLATE_SERVICE.md) | 架构、部署、安全、数据流、性能伸缩 |
| CLI / 工具 | [REPORT_TEMPLATE_CLI.md](REPORT_TEMPLATE_CLI.md) | 命令设计、配置系统、使用体验、Shell 集成 |
| 不确定 / 通用 | [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md) | 标准全维度分析 |

**报告格式规则**：
- 默认输出：Markdown（`.md`）
- 若用户要求演示文稿，调用 pptx skill
- 若用户要求表格汇总，调用 xlsx skill
- 引用代码时使用绝对 GitHub URL
- 架构概览用 mermaid 图表呈现
- 所有量化数据（deps/arch/quality/security/perf/api）融入对应章节
- 若某章节无内容（如 CLI 项目无 HTTP 路由），保留标题但标注"本项目不适用"，或根据模板指引跳过该章节

## 并行分析策略

模块数超过 10 个或代码量超过 10 万行时：

1. 先执行步骤 1–5（全局扫描和架构反推）
2. 将核心模块拆分为 3–5 个批次
3. 用 Task 工具并行派生子 agent，每个分析一个批次
4. 汇总输出，检查模块间一致性

## 输出定制

- **快速概览**：跳过步骤 5、7、9–13，基于扫描结果输出摘要
- **深度分析**：扩展步骤 5 和 7，增加代码级走读
- **安全审查**：聚焦步骤 10，增加威胁模型分析
- **性能剖析**：聚焦步骤 11，结合 benchmark 结果做热点分析

## 质量检查清单

- [ ] 本地目录已验证为 git 仓库
- [ ] 已运行全部 6 个分析脚本并消化输出
- [ ] 架构反推五步法已系统执行，结论有代码证据
- [ ] 所有核心模块已识别并映射到源码位置
- [ ] 设计模式已明确命名并对应代码特征
- [ ] 创新点经过验证
- [ ] 代码质量、安全、性能三个维度的量化数据已融入报告
- [ ] Mermaid 依赖图和 API 清单已生成并嵌入
- [ ] 引用的代码/文件已附带 GitHub URL
- [ ] 全文技术术语一致
