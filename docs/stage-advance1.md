# Stage Advance 1：账号池健康守护与自动补号

## 1. 背景

根据 `docs/plan.md` 中“账号池调度升级”和“部署与数据可靠性”的方向，当前系统已经具备账号池管理、限流账号定时刷新、注册机手动启动等能力，但缺少自动化的账号池健康监测与补号触发机制。

本阶段新增“账号池健康守护”能力：系统每 5 分钟监测一次账号池正常情况，当账号池存活率低于 20% 时，自动触发注册机流程，并且该策略可以在系统设置中配置。

## 2. 目标

核心目标：

- 自动发现账号池健康度下降。
- 在存活率过低时自动启动注册机补充账号。
- 让管理员可以在系统设置中配置是否启用、检查间隔、触发阈值和触发后的注册策略。
- 避免重复触发注册机、错误触发注册机或在配置不完整时盲目执行。

不在本阶段处理：

- 不改造注册机底层注册流程。
- 不引入外部任务队列。
- 不实现账号分组级别的健康守护。
- 不实现普通用户维度配额。

## 3. 业务定义

### 3.1 账号池总数

账号池总数指当前账号池中所有账号数量，包含：

- 正常账号
- 限流账号
- 异常账号
- 禁用账号

建议字段：

```text
total_accounts = len(account_service.list_accounts())
```

### 3.2 存活账号数

存活账号指当前可用于图片生成的账号。建议沿用后端现有图片可用性口径：

- 状态不是 `禁用`、`限流`、`异常`
- 如果 `image_quota_unknown=true`，视为可用
- 否则 `quota > 0`

建议字段：

```text
alive_accounts = count(account where image account available)
```

### 3.3 账号池存活率

账号池存活率计算公式：

```text
alive_rate = alive_accounts / total_accounts * 100
```

边界规则：

- 当 `total_accounts = 0` 时，存活率记为 `0%`。
- 当账号池总数低于最小样本数时，默认不触发自动注册，避免新部署空池反复触发。最小样本数应可配置，默认 `5`。
- 管理员可选择是否允许空池触发注册，默认关闭。

## 4. 配置需求

在系统设置页新增“账号池健康守护”配置区，建议归入当前 `ConfigCard`，与“账号刷新间隔”“自动移除异常账号”等账号池配置放在一起。

### 4.1 配置字段

建议后端配置结构：

```json
{
  "account_pool_guard": {
    "enabled": false,
    "check_interval_minutes": 5,
    "alive_rate_threshold": 20,
    "min_total_accounts": 5,
    "trigger_cooldown_minutes": 30,
    "allow_empty_pool_trigger": false,
    "register_mode": "available",
    "register_target_available": 10,
    "register_target_quota": 100
  }
}
```

字段说明：

| 字段 | 类型 | 默认值 | 说明 |
|:--|:--|:--|:--|
| `enabled` | boolean | `false` | 是否启用账号池健康守护 |
| `check_interval_minutes` | integer | `5` | 健康检查间隔，单位分钟 |
| `alive_rate_threshold` | integer | `20` | 触发注册机的存活率阈值，范围 `1-100` |
| `min_total_accounts` | integer | `5` | 最小账号池样本数，低于该数量时默认不触发 |
| `trigger_cooldown_minutes` | integer | `30` | 自动触发冷却时间，避免频繁启动注册机 |
| `allow_empty_pool_trigger` | boolean | `false` | 是否允许账号池为空时触发注册机 |
| `register_mode` | string | `available` | 自动触发时使用的注册机模式，支持 `available`、`quota`、`total` |
| `register_target_available` | integer | `10` | `available` 模式下目标正常账号数 |
| `register_target_quota` | integer | `100` | `quota` 模式下目标剩余额度 |

### 4.2 系统设置页面

系统设置页需要提供以下控件：

- 启用账号池健康守护：开关。
- 检查间隔：数字输入，默认 `5` 分钟。
- 存活率阈值：数字输入，默认 `20%`。
- 最小账号池样本数：数字输入，默认 `5`。
- 自动触发冷却时间：数字输入，默认 `30` 分钟。
- 允许空池触发：复选框，默认关闭。
- 触发后的注册目标：选择 `补充正常账号` 或 `补充剩余额度`。
- 目标正常账号数 / 目标剩余额度：根据模式展示对应输入框。

页面应展示简短说明：

```text
系统会按配置周期检查账号池可用账号占比；低于阈值且注册机未运行时，将自动启动注册流程。
```

## 5. 后端服务需求

### 5.1 新增健康守护线程

应用启动时，在 FastAPI lifespan 中启动账号池健康守护线程，停止应用时关闭线程。

建议新增服务：

```text
services/account_pool_guard_service.py
```

职责：

- 读取 `config.account_pool_guard`。
- 每 `check_interval_minutes` 分钟检查账号池。
- 计算 `total_accounts`、`alive_accounts`、`alive_rate`。
- 判断是否需要触发注册机。
- 写入日志和运行状态。

### 5.2 触发条件

满足以下全部条件时自动触发注册机：

1. `account_pool_guard.enabled = true`
2. 注册机当前未运行
3. 未处于自动触发冷却期
4. 账号池总数满足：
   - `total_accounts >= min_total_accounts`，或
   - `total_accounts = 0` 且 `allow_empty_pool_trigger = true`
5. `alive_rate < alive_rate_threshold`
6. 注册机邮箱 provider、代理等必要配置有效

触发动作：

- 自动更新注册机运行参数。
- 启动 `register_service.start()`。
- 写入系统日志。
- 写入注册机日志，标记来源为账号池健康守护。

### 5.3 不触发条件

以下情况不触发注册机，只记录日志：

- 健康守护未启用。
- 注册机已经运行。
- 处于冷却时间内。
- 账号池总数小于最小样本数，且不允许空池触发。
- 注册机配置不完整。
- 存活率高于或等于阈值。

### 5.4 状态记录

建议在配置或独立状态文件中记录最近一次检查与触发状态：

```json
{
  "last_checked_at": "2026-06-29T10:00:00Z",
  "last_triggered_at": "2026-06-29T10:00:00Z",
  "last_alive_rate": 18.5,
  "last_total_accounts": 27,
  "last_alive_accounts": 5,
  "last_action": "triggered",
  "last_message": "账号池存活率 18.5% 低于阈值 20%，已自动启动注册机"
}
```

建议新增接口或并入 `/api/settings` 返回：

```text
GET /api/account-pool-guard
```

返回当前配置、最近检查状态和是否处于冷却期。

## 6. 注册机联动需求

自动触发注册机时，建议默认使用 `available` 模式：

```json
{
  "mode": "available",
  "target_available": 10
}
```

联动规则：

- 如果配置 `register_mode=available`，自动触发后注册到正常账号数达到 `register_target_available`。
- 如果配置 `register_mode=quota`，自动触发后注册到剩余额度达到 `register_target_quota`。
- 如果配置 `register_mode=total`，建议仅作为高级选项，自动触发时使用注册机已有 `total` 配置。
- 自动触发不应覆盖邮箱 provider 配置、注册代理、线程数等基础注册配置。
- 如果注册机正在运行，健康守护只记录“已跳过，注册机运行中”。

## 7. 日志需求

新增日志类型可以继续使用现有 `LOG_TYPE_ACCOUNT`，也可以新增 `LOG_TYPE_GUARD`。短期建议复用账号日志，降低改动。

日志场景：

- 每次触发注册机。
- 因冷却跳过。
- 因注册机正在运行跳过。
- 因配置不完整跳过。
- 健康检查异常。

触发日志示例：

```json
{
  "type": "account",
  "summary": "账号池健康守护触发注册机",
  "detail": {
    "total_accounts": 27,
    "alive_accounts": 5,
    "alive_rate": 18.5,
    "threshold": 20,
    "register_mode": "available",
    "target_available": 10
  }
}
```

## 8. 前端展示需求

系统设置页新增配置区后，应展示最近一次健康检查状态：

- 最近检查时间
- 账号池总数
- 存活账号数
- 当前存活率
- 当前阈值
- 最近一次自动触发时间
- 冷却剩余时间
- 最近动作说明

建议视觉状态：

- 存活率高于阈值：正常状态。
- 存活率低于阈值但未触发：警告状态，并展示原因。
- 已触发注册机：提示“注册机已自动启动”。
- 注册机运行中：展示当前注册机状态。

## 9. 边界与风控

必须处理以下边界：

- 注册机配置不完整时不能自动启动。
- 注册机正在运行时不能重复启动。
- 存活率持续低于阈值时不能每 5 分钟重复触发，应受冷却时间限制。
- 管理员手动停止注册机后，冷却期内不应立刻再次自动启动。
- 空账号池是否触发必须由配置决定，默认不触发。
- 自动触发产生的注册任务应和手动注册任务使用同一套统计与日志。

## 10. 验收标准

功能验收：

1. 系统设置中可以启用/关闭账号池健康守护。
2. 默认检查间隔为 5 分钟，默认触发阈值为 20%。
3. 当账号池存活率低于 20%，且满足触发条件时，系统会自动启动注册机。
4. 注册机运行中不会重复触发。
5. 冷却期内不会重复触发。
6. 设置页能看到最近一次检查结果和最近一次触发结果。
7. 自动触发会写入系统日志。

测试验收：

- 构造 10 个账号，其中 1 个可用，9 个限流/异常，开启守护后应触发注册机。
- 构造 10 个账号，其中 3 个可用，阈值 20%，不应触发注册机。
- 注册机已运行时，低存活率检查只记录跳过。
- 冷却时间内，连续低存活率检查只触发一次。
- 账号池为空且 `allow_empty_pool_trigger=false` 时不触发。
- 账号池为空且 `allow_empty_pool_trigger=true` 时触发。

## 11. 推荐实施顺序

1. 后端 `ConfigStore` 增加 `account_pool_guard` 配置规范化与校验。
2. `AccountService` 增加账号池健康统计方法，返回总数、存活数、存活率。
3. 新增 `account_pool_guard_service`，实现周期检查、触发判断和日志。
4. 在 FastAPI lifespan 中启动和停止健康守护线程。
5. 扩展 `/api/settings` 或新增接口返回健康守护状态。
6. 设置页新增配置区和状态展示。
7. 补充单元测试和集成测试。

## 12. 与 `docs/plan.md` 的关系

该需求属于 `docs/plan.md` 中阶段三“账号池调度升级”的前置增强，也支撑阶段四“部署与数据可靠性”。它优先解决账号池可用性下降后的自动补救问题，为后续账号能力标签、调度降权、用户配额等能力打基础。
