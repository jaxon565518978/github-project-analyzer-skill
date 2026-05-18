# 设计模式代码特征库

识别设计模式时，不要凭感觉，而是对照以下代码特征进行验证。

## 架构模式

### 分层架构
- **特征**：目录严格分为 `controller/service/repository/dao` 或 `api/biz/data` 等层级
- **验证**：高层目录（controller）只依赖低层目录（service），不允许反向依赖
- **反例**：controller 直接调用 dao，跳过 service 层

### 微服务
- **特征**：存在服务注册（registry/discovery）、RPC 调用（grpc/thrift）、独立部署配置
- **验证**：代码中存在 `client.NewXxxClient()` 或 `grpc.Dial()` 等远程调用痕迹
- **反例**：单体应用内用 interface 模拟的服务拆分

### 事件驱动
- **特征**：大量 `Event`/`EventHandler`/`Publish`/`Subscribe`/`EventBus` 类或函数
- **验证**：一个模块生产事件，另一个模块消费事件，二者无直接调用关系
- **常见库**：Go 的 watermill、Python 的 celery、kafka、rabbitmq

### 插件化
- **特征**：存在 `plugin/`、`extension/` 目录，或动态加载 `.so`/`.dll`/`.wasm` 的机制
- **验证**：核心系统定义接口，外部模块实现该接口并通过注册表加载
- **代码特征**：`Register("name", func(...))`、`LoadPlugin("path")`、`plugin.Open()`

### 六边形架构（端口与适配器）
- **特征**：核心业务逻辑不依赖框架，通过 adapter/ports 与外界交互
- **验证**：核心业务包不 import 任何框架（gin、spring、django 等），框架依赖仅在 adapter 层
- **目录特征**：`internal/core/` 或 `domain/` 纯业务逻辑，`adapter/http/`、`adapter/db/` 纯适配

## 结构模式

### 适配器（Adapter）
- **特征**：类名含 `Adapter`，或包装第三方库提供统一接口
- **代码特征**：`type XxxAdapter struct { inner *thirdparty.Client }`，方法转发到 inner
- **验证**：适配器的存在使调用方无需感知第三方接口的变化

### 装饰器（Decorator）
- **特征**：函数/方法接收同类型参数并返回同类型，层层包裹
- **代码特征**：`func (d *LoggingDecorator) Do() { log(); d.inner.Do() }`
- **验证**：装饰器与被装饰者实现同一接口

### 外观（Facade）
- **特征**：一个类/函数提供简化的 API，内部转发到多个子系统
- **代码特征**：`func DoEverything() { step1(); step2(); step3() }`
- **验证**：外观的存在简化了复杂子系统的使用

### 代理（Proxy）
- **特征**：类名含 `Proxy`，或拦截方法调用的中间层
- **代码特征**：`func (p *Proxy) Call() { before(); p.real.Call(); after() }`
- **与装饰器的区别**：代理控制访问，装饰器增强功能

## 行为模式

### 策略（Strategy）
- **特征**：存在 `Strategy` 接口和多个实现，运行时选择
- **代码特征**：
  ```go
  type Strategy interface { Execute() }
  type StrategyA struct{} // 实现
  type StrategyB struct{} // 实现
  func NewStrategy(name string) Strategy { ... }
  ```
- **验证**：调用方通过接口调用，不知道具体实现

### 观察者（Observer）
- **特征**：存在 `Observer`/`Listener`/`Subscriber` 和 `Notify`/`Emit`/`Broadcast` 方法
- **代码特征**：`RegisterListener(l)`、`Notify(event)`、遍历 listeners 逐一调用
- **与事件驱动的区别**：观察者是一对多通知，事件驱动是消息队列解耦

### 命令（Command）
- **特征**：存在 `Command` 接口，带 `Execute`/`Undo`/`Redo` 方法
- **代码特征**：`type Command interface { Execute() error }`，每个操作封装为一个 struct
- **验证**：命令可以被序列化、排队、撤销

### 状态机（State）
- **特征**：存在 `State` 接口和多个状态实现，上下文根据条件切换状态
- **代码特征**：`context.SetState(newState)`，状态对象处理行为委托
- **验证**：状态转换由状态对象自身或上下文管理，而非大量 switch/case

## 并发模式

### Actor 模型
- **特征**：`Actor`/`Mailbox`/`Message` 类型，异步消息传递
- **代码特征**：`actor.Tell(msg)`、`actor.Ask(msg)`、每个 actor 有独立邮箱
- **常见库**：Go 的 protoactor-go、Java 的 Akka、Rust 的 actix

### CSP（通信顺序进程）
- **特征**：大量使用 channel/queue 进行 goroutine/task 间通信
- **代码特征**：`ch := make(chan T)`、`go func() { ch <- data }()`、`<-ch`
- **验证**：共享状态通过 channel 传递，而非共享内存加锁

### 线程池 / Worker Pool
- **特征**：存在 `Pool`/`Worker`/`Executor` 类型，任务提交到队列
- **代码特征**：`pool.Submit(task)`、`worker.process()`、固定数量的 worker goroutine
- **验证**：任务数量远大于 worker 数量，避免无限制创建线程

## 各语言特定架构特征

### Go
- **接口隐含实现**：只要实现了方法集即满足接口，无需显式声明
- **Context 传播**：`ctx context.Context` 作为第一个参数贯穿调用链
- **Error 处理**：函数返回 `(result, error)`，调用方必须处理 error
- **Channel 关闭语义**：`close(ch)` 用于通知读取方结束，不用于传递数据

### Python
- **鸭子类型**：不检查类型，检查行为（`hasattr(obj, 'method')`）
- **装饰器语法**：`@decorator` 本质是函数组合
- **Mixin 模式**：通过多重继承组合功能
- **上下文管理器**：`with` 语句管理资源生命周期

### Rust
- **所有权系统**：`&T`（不可变借用）、`&mut T`（可变借用）、`Box<T>`（所有权转移）
- **Trait 作为接口**：`trait` 定义契约，`impl Trait for Type` 实现
- **生命周期标注**：`'a` 标注引用有效性范围
- **Result/Option**：错误处理通过类型系统强制处理

### Java
- **Spring 依赖注入**：`@Autowired`、`@Component`、`@Service` 标记
- **接口默认方法**：Java 8+ 接口可带默认实现
- **泛型擦除**：运行时泛型信息丢失，编译期检查
- **匿名内部类 / Lambda**：`new Interface() { ... }` 或 `(x) -> x + 1`
