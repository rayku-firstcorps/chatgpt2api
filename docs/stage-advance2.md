# Stage Advance 2：账号池事件飞书卡片告警

## 1. 背景

`docs/stage-advance1.md` 已经定义了“账号池健康守护与自动补号”能力：系统按配置周期检查账号池存活率，在低于阈值且满足条件时自动触发注册机，并记录最近一次检查与触发状态。

Stage Advance 2 在此基础上补充“企业协作告警”能力：当账号池健康守护发现关键事件时，通过飞书自定义机器人 Webhook 推送飞书卡片，让管理员不需要持续打开后台页面，也能及时知道账号池风险、自动补号结果和需要人工处理的异常。

本阶段关注“告警能被看见、能被理解、不会刷屏、能指导下一步动作”。

## 2. 目标

核心目标：

- 将账号池健康守护中的关键事件推送到飞书群。
- 使用飞书卡片承载结构化信息，而不是只发纯文本。
- 管理员可以在系统设置中配置飞书 Webhook、签名密钥、告警事件范围和告警冷却策略。
- 对高频事件做去重和限频，避免每 5 分钟重复刷屏。
- 告警卡片能清楚展示账号池状态、触发原因、自动补号状态和建议动作。
- 飞书推送失败不影响账号池健康守护主流程。

不在本阶段处理：

- 不接入飞书应用机器人 OAuth，不调用飞书开放平台鉴权接口。
- 不实现飞书卡片按钮回调、审批、二次确认或双向交互。
- 不实现多租户、多群组、多账号池分组级告警。
- 不引入外部消息队列。
- 不把敏感 token、邮箱密码、Webhook 明文暴露到前端。

## 3. 用户与场景

### 3.1 目标用户

- 系统管理员：负责维护账号池、注册机、代理、邮箱 provider 等基础配置。
- 运维值班人员：需要在飞书群里及时收到风险提示，并判断是否需要人工介入。
- 业务负责人：关心账号池是否会影响图片生成服务稳定性。

### 3.2 核心场景

1. 账号池存活率低于阈值，系统已自动启动注册机。
2. 账号池存活率低于阈值，但因为注册机配置不完整无法补号。
3. 账号池持续低存活率，但处于自动触发冷却期，系统没有重复启动注册机。
4. 注册机已经运行，健康守护跳过重复触发。
5. 账号池恢复健康，系统发送恢复通知。
6. 健康检查任务自身异常，系统发送异常告警。

## 4. 产品原则

### 4.1 告警必须可行动

每条告警至少回答四个问题：

- 发生了什么？
- 当前影响有多大？
- 系统自动做了什么？
- 管理员下一步应该做什么？

### 4.2 默认降噪

默认只推送需要关注的事件，不推送每一次正常健康检查。

默认策略：

- `triggered`、`skipped_register_config`、`error`：立即推送。
- `skipped_register_running`、`skipped_cooldown`：受冷却限制后推送。
- `healthy`：默认不推送，仅在从异常恢复到健康时推送恢复通知。
- `disabled`、`skipped_min_sample`：默认不推送，可配置开启。

### 4.3 告警状态可追溯

系统应记录最近一次飞书告警状态，包括推送时间、事件类型、是否成功、失败原因、飞书返回码，方便排查 Webhook 配置问题。

### 4.4 告警失败不阻塞主流程

飞书 Webhook 推送失败时：

- 不阻塞账号池健康检查。
- 不阻塞注册机自动启动。
- 记录系统日志。
- 更新飞书告警状态。

## 5. 事件定义

### 5.1 事件来源

本阶段以 `account_pool_guard_service` 的健康检查结果为主要事件来源。

建议复用 Stage Advance 1 中的 `last_action`：

| 事件编码 | 事件名称 | 默认告警 | 严重级别 | 说明 |
|:--|:--|:--|:--|:--|
| `triggered` | 已自动触发补号 | 是 | warning | 存活率低于阈值，且已自动启动注册机 |
| `skipped_register_config` | 注册机配置不完整 | 是 | critical | 存活率低但无法自动补号，需要人工处理 |
| `error` | 健康检查异常 | 是 | critical | 守护线程检查过程异常 |
| `skipped_register_running` | 注册机运行中跳过 | 可配置 | info | 注册机已运行，系统不重复启动 |
| `skipped_cooldown` | 冷却期跳过 | 可配置 | warning | 持续低存活率，但受冷却限制 |
| `healthy_recovered` | 账号池恢复健康 | 是 | success | 从异常/低存活状态恢复到阈值以上 |
| `healthy` | 健康检查正常 | 否 | success | 存活率高于或等于阈值 |
| `skipped_min_sample` | 样本数不足跳过 | 否 | info | 账号池低于最小样本数且未允许空池触发 |
| `disabled` | 健康守护未启用 | 否 | info | 守护关闭，不推送告警 |

### 5.2 事件载荷

每个可告警事件应统一封装为 `AccountPoolGuardEvent`：

```json
{
  "event_id": "account_pool_guard:triggered:2026-06-29T10:00:00Z",
  "event_type": "triggered",
  "severity": "warning",
  "occurred_at": "2026-06-29T10:00:00Z",
  "title": "账号池健康守护触发注册机",
  "message": "账号池存活率 18.5% 低于阈值 20%，已自动启动注册机",
  "total_accounts": 27,
  "alive_accounts": 5,
  "alive_rate": 18.5,
  "threshold": 20,
  "register_running": true,
  "register_mode": "available",
  "register_target_available": 10,
  "register_target_quota": 100,
  "cooldown_remaining_seconds": 1800,
  "suggestion": "观察注册机运行结果；如果失败数持续上升，请检查邮箱 provider、代理和上游风控。"
}
```

## 6. 飞书告警配置需求

### 6.1 后端配置结构

建议在 `config.json` 中新增：

```json
{
  "feishu_alert": {
    "enabled": false,
    "webhook_url": "",
    "secret": "",
    "keyword": "账号池告警",
    "notify_events": [
      "triggered",
      "skipped_register_config",
      "error",
      "healthy_recovered"
    ],
    "alert_cooldown_minutes": 30,
    "recovery_notify": true,
    "include_register_status": true,
    "include_manage_link": true
  }
}
```

字段说明：

| 字段 | 类型 | 默认值 | 说明 |
|:--|:--|:--|:--|
| `enabled` | boolean | `false` | 是否启用飞书告警 |
| `webhook_url` | string | `""` | 飞书自定义机器人 Webhook 地址 |
| `secret` | string | `""` | 飞书机器人签名密钥；为空时不签名 |
| `keyword` | string | `账号池告警` | 用于匹配飞书机器人关键词安全策略，也作为卡片标题前缀 |
| `notify_events` | string[] | 见上方默认值 | 允许推送的事件类型 |
| `alert_cooldown_minutes` | integer | `30` | 同类事件告警冷却时间 |
| `recovery_notify` | boolean | `true` | 从异常恢复健康时是否推送恢复通知 |
| `include_register_status` | boolean | `true` | 卡片中是否展示注册机运行状态 |
| `include_manage_link` | boolean | `true` | 卡片中是否展示后台管理入口 |

### 6.2 配置校验

保存配置时应执行：

- `enabled=true` 时，`webhook_url` 必须非空。
- `webhook_url` 必须以 `https://open.feishu.cn/open-apis/bot/v2/hook/` 或飞书兼容域名开头。
- `alert_cooldown_minutes >= 0`。
- `notify_events` 只能包含系统支持的事件编码。
- `keyword` 最多 30 个字符，默认 `账号池告警`。

敏感字段处理：

- `/api/settings` 返回时不返回完整 `webhook_url` 和 `secret`。
- 前端展示为脱敏文本，例如 `https://open.feishu.cn/.../hook/****abcd`。
- 保存时如果字段为空，表示沿用原值；如需清空，前端应提供明确“清空”动作或发送专用标记。

## 7. 飞书卡片设计

### 7.1 卡片层级

卡片信息优先级：

1. 标题：事件结论。
2. 状态条：严重级别与当前动作。
3. 关键指标：总账号数、存活账号数、存活率、阈值。
4. 注册机状态：是否运行、注册模式、目标值。
5. 时间信息：检查时间、触发时间、冷却剩余。
6. 建议动作：管理员下一步处理建议。
7. 管理入口：后台设置页或注册机页链接。

### 7.2 颜色规范

| 严重级别 | 飞书卡片模板色 | 适用事件 |
|:--|:--|:--|
| `critical` | `red` | 注册机配置不完整、健康检查异常 |
| `warning` | `orange` / `yellow` | 自动触发补号、冷却期跳过 |
| `info` | `blue` | 注册机运行中、样本数不足 |
| `success` | `green` | 账号池恢复健康 |

### 7.3 卡片标题规范

标题格式：

```text
[账号池告警] {事件结论}
```

示例：

- `[账号池告警] 存活率低，已自动启动注册机`
- `[账号池告警] 存活率低，但注册机配置不完整`
- `[账号池告警] 账号池已恢复健康`

### 7.4 卡片正文示例

```text
事件：账号池健康守护触发注册机
状态：已自动启动补号

账号池：
- 总账号数：27
- 存活账号数：5
- 存活率：18.5%
- 触发阈值：20%

注册机：
- 状态：运行中
- 模式：补充正常账号
- 目标正常账号数：10

建议：
观察注册机运行结果；如果失败数持续上升，请检查邮箱 provider、代理和上游风控。
```

### 7.5 Webhook 请求示例

飞书自定义机器人发送卡片时使用 `msg_type=interactive`。卡片可先采用静态 JSON 卡片，不依赖回调。

```json
{
  "msg_type": "interactive",
  "card": {
    "config": {
      "wide_screen_mode": true
    },
    "header": {
      "template": "orange",
      "title": {
        "tag": "plain_text",
        "content": "[账号池告警] 存活率低，已自动启动注册机"
      }
    },
    "elements": [
      {
        "tag": "div",
        "text": {
          "tag": "lark_md",
          "content": "**事件**：账号池健康守护触发注册机\n**状态**：已自动启动补号"
        }
      },
      {
        "tag": "hr"
      },
      {
        "tag": "div",
        "fields": [
          {
            "is_short": true,
            "text": {
              "tag": "lark_md",
              "content": "**总账号数**\n27"
            }
          },
          {
            "is_short": true,
            "text": {
              "tag": "lark_md",
              "content": "**存活账号数**\n5"
            }
          },
          {
            "is_short": true,
            "text": {
              "tag": "lark_md",
              "content": "**存活率**\n18.5%"
            }
          },
          {
            "is_short": true,
            "text": {
              "tag": "lark_md",
              "content": "**阈值**\n20%"
            }
          }
        ]
      },
      {
        "tag": "div",
        "text": {
          "tag": "lark_md",
          "content": "**建议**：观察注册机运行结果；如果失败数持续上升，请检查邮箱 provider、代理和上游风控。"
        }
      }
    ]
  }
}
```

## 8. 告警策略

### 8.1 触发规则

满足以下条件时发送飞书告警：

1. `feishu_alert.enabled = true`
2. Webhook 配置有效
3. 事件类型在 `notify_events` 中
4. 未命中同类事件告警冷却
5. 当前事件不是与上一条完全相同且未过冷却期的重复事件

### 8.2 恢复通知规则

当上一条可告警状态为异常类事件，且当前健康检查结果为 `healthy`，并满足：

- `recovery_notify = true`
- `alive_rate >= alive_rate_threshold`

则生成 `healthy_recovered` 事件并推送恢复卡片。

异常类事件包括：

- `triggered`
- `skipped_register_config`
- `skipped_cooldown`
- `error`

### 8.3 去重规则

建议使用以下维度生成告警指纹：

```text
fingerprint = event_type + severity + threshold + register_mode + rounded_alive_rate_bucket
```

其中 `rounded_alive_rate_bucket` 可按 5% 桶归类，例如：

- `0-5`
- `5-10`
- `10-15`
- `15-20`

同一指纹在 `alert_cooldown_minutes` 内只推送一次。

### 8.4 失败重试

本阶段不做后台重试队列。

Webhook 请求失败时：

- 当前检查周期只发送一次。
- 记录失败原因。
- 下一次健康检查如果仍满足告警条件，可再次尝试，但仍受冷却策略限制。

## 9. 状态记录

建议新增独立状态文件：

```text
data/feishu_alert_state.json
```

状态结构：

```json
{
  "last_sent_at": "2026-06-29T10:00:00Z",
  "last_event_type": "triggered",
  "last_fingerprint": "triggered:warning:20:available:15-20",
  "last_status": "success",
  "last_error": "",
  "last_response_code": 0,
  "last_response_message": "success",
  "last_recovered_at": "2026-06-29T10:30:00Z",
  "recent_events": [
    {
      "sent_at": "2026-06-29T10:00:00Z",
      "event_type": "triggered",
      "status": "success",
      "fingerprint": "triggered:warning:20:available:15-20"
    }
  ]
}
```

`recent_events` 最多保留最近 50 条。

## 10. 后端服务需求

### 10.1 新增服务

建议新增：

```text
services/feishu_alert_service.py
```

职责：

- 读取 `config.feishu_alert`。
- 将账号池事件转换为飞书卡片 payload。
- 根据飞书机器人安全配置生成签名参数。
- 发送 Webhook HTTP POST 请求。
- 执行告警去重、冷却、恢复通知判断。
- 记录推送状态与系统日志。

### 10.2 与账号池守护服务集成

建议在 `account_pool_guard_service.run_once()` 完成状态判断后，构造事件并调用：

```python
feishu_alert_service.notify_account_pool_event(event)
```

调用要求：

- 必须放在账号池主逻辑之后。
- 必须捕获飞书服务异常。
- 不允许飞书失败影响 `run_once()` 返回。

### 10.3 请求签名

当配置了 `feishu_alert.secret` 时，发送请求应携带：

```json
{
  "timestamp": "1710000000",
  "sign": "generated_sign",
  "msg_type": "interactive",
  "card": {}
}
```

签名算法按飞书自定义机器人安全设置要求实现。

### 10.4 HTTP 行为

请求要求：

- Method：`POST`
- Header：`Content-Type: application/json`
- Timeout：默认 5 秒，可在代码中固定，不在本阶段暴露配置。
- 成功判断：飞书返回 `code = 0` 视为成功。
- 失败判断：HTTP 非 2xx、JSON 解析失败、`code != 0` 均视为失败。

### 10.5 系统日志

继续复用 `LOG_TYPE_ACCOUNT` 或新增 `LOG_TYPE_ALERT`。短期建议新增：

```text
LOG_TYPE_ALERT = "alert"
```

日志场景：

- 飞书告警发送成功。
- 飞书告警发送失败。
- 飞书告警因冷却跳过。
- 飞书告警因事件未订阅跳过。
- 飞书告警配置不完整。

日志示例：

```json
{
  "type": "alert",
  "summary": "飞书账号池告警发送成功",
  "detail": {
    "event_type": "triggered",
    "severity": "warning",
    "fingerprint": "triggered:warning:20:available:15-20",
    "response_code": 0
  }
}
```

## 11. API 需求

### 11.1 并入系统设置

`GET /api/settings` 返回：

```json
{
  "config": {
    "feishu_alert": {
      "enabled": false,
      "webhook_url": "https://open.feishu.cn/.../hook/****abcd",
      "secret_configured": false,
      "keyword": "账号池告警",
      "notify_events": ["triggered", "skipped_register_config", "error", "healthy_recovered"],
      "alert_cooldown_minutes": 30,
      "recovery_notify": true,
      "include_register_status": true,
      "include_manage_link": true
    }
  },
  "feishu_alert": {
    "state": {}
  }
}
```

`POST /api/settings` 支持保存 `feishu_alert` 配置。

### 11.2 测试 Webhook

新增接口：

```text
POST /api/feishu-alert/test
```

行为：

- 管理员权限。
- 使用当前待保存或已保存配置发送一张测试卡片。
- 不触发账号池事件。
- 返回飞书响应摘要。

请求示例：

```json
{
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
  "secret": "xxx",
  "keyword": "账号池告警"
}
```

响应示例：

```json
{
  "result": {
    "ok": true,
    "status": 200,
    "code": 0,
    "message": "success"
  }
}
```

## 12. 前端需求

### 12.1 设置页新增配置区

在系统设置页新增“飞书告警”配置区，建议放在“账号池健康守护”配置下方。

控件：

- 启用飞书告警：开关。
- Webhook 地址：密码输入或可隐藏输入。
- 签名密钥：密码输入；显示“已配置”状态。
- 安全关键词：文本输入，默认 `账号池告警`。
- 告警事件：多选复选框。
- 同类事件冷却时间：数字输入，默认 `30` 分钟。
- 恢复健康通知：开关。
- 卡片包含注册机状态：开关。
- 卡片包含管理入口：开关。
- 测试发送：按钮。

### 12.2 状态展示

配置区展示最近一次推送状态：

- 最近发送时间。
- 最近事件类型。
- 最近发送结果。
- 飞书返回码。
- 最近失败原因。

视觉状态：

- 未启用：灰色提示。
- 已启用且最近成功：绿色提示。
- 已启用但最近失败：红色提示。
- Webhook 未配置：黄色提示。

### 12.3 交互要求

- 点击“测试发送”前先校验 Webhook 地址非空。
- 测试发送不会自动保存配置，除非前端明确提示并执行保存。
- 密钥字段为空时不覆盖后端已保存密钥。
- 提供“清空密钥”动作，避免误清空。

## 13. 安全与合规

必须处理：

- Webhook URL 和 secret 不写入前端日志。
- 后端返回配置时脱敏。
- 系统日志中不记录完整 Webhook URL 和 secret。
- 飞书请求超时不能拖慢健康守护线程。
- 飞书推送内容不得包含账号 token、refresh token、id token、邮箱密码、代理账号密码。

建议：

- 推荐管理员在飞书机器人中开启关键词或签名安全设置。
- 卡片中的管理入口只使用系统 `base_url` 拼接相对路径，不包含鉴权 token。

## 14. 边界与风控

- Webhook 配置错误：不影响健康守护，只记录失败。
- 飞书限流或网络异常：本阶段不重试队列，下一轮检查可再次尝试。
- 高频低存活率：受同类事件冷却控制。
- 存活率在阈值上下波动：只有从异常恢复到健康时发送恢复通知，避免正常状态反复推送。
- 管理后台未配置 `base_url`：卡片不展示管理入口。
- 飞书卡片 payload 过大：只展示摘要指标，不展示账号明细列表。

## 15. 验收标准

功能验收：

1. 系统设置中可以启用/关闭飞书告警。
2. 可以配置 Webhook、签名密钥、关键词、告警事件和告警冷却时间。
3. 可以点击“测试发送”向飞书群发送测试卡片。
4. 当账号池健康守护触发注册机时，飞书群收到告警卡片。
5. 当注册机配置不完整导致无法自动补号时，飞书群收到 critical 告警卡片。
6. 同类事件在冷却期内不会重复刷屏。
7. 账号池从异常恢复健康时，可以收到恢复通知。
8. Webhook 推送失败时，健康守护和注册机流程不受影响。
9. 设置页能看到最近一次飞书告警发送状态。
10. 系统日志能记录飞书告警成功、失败和跳过原因。

测试验收：

- 配置有效 Webhook，手动测试发送应返回成功并在飞书群出现测试卡片。
- 构造 10 个账号，其中 1 个可用、9 个限流/异常，启用健康守护和飞书告警后，应自动触发注册机并发送 `triggered` 卡片。
- 注册机邮箱 provider 缺失时，低存活率检查应发送 `skipped_register_config` 卡片。
- 冷却期内重复触发同类事件，只发送一次卡片。
- 将账号池恢复到 10 个账号中 3 个可用，阈值 20%，应发送一次恢复通知。
- Webhook URL 错误时，应记录发送失败，账号池健康检查返回正常。
- 后端 `/api/settings` 不返回完整 Webhook 和 secret。

## 16. 推荐实施顺序

1. `ConfigStore` 增加 `feishu_alert` 配置规范化、脱敏返回和保存校验。
2. 新增 `feishu_alert_service`，实现卡片构造、签名、发送、状态记录。
3. 在 `account_pool_guard_service` 中构造账号池事件并调用飞书告警服务。
4. 新增 `POST /api/feishu-alert/test`。
5. 设置页新增“飞书告警”配置区、测试按钮和最近推送状态。
6. 补充单元测试：配置规范化、事件过滤、冷却去重、卡片构造、签名。
7. 补充集成测试：低存活率触发告警、恢复通知、Webhook 失败不阻塞。

## 17. 与 Stage Advance 1 的关系

Stage Advance 1 解决“系统能自动发现并处理账号池低存活率”的问题。

Stage Advance 2 解决“团队能及时知道系统发生了什么，以及是否需要人工介入”的问题。

两者关系：

- Stage Advance 1 产生账号池健康事件。
- Stage Advance 2 订阅这些事件并发送飞书卡片告警。
- Stage Advance 2 不改变 Stage Advance 1 的触发判断和补号流程，只增加通知、状态记录和可观测性。

## 18. 参考资料

- 飞书开放平台：自定义机器人使用指南  
  https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot?lang=zh-CN
- 飞书开放平台：使用自定义机器人发送卡片消息  
  https://open.feishu.cn/document/common-capabilities/message-card/getting-started/send-message-cards-with-a-custom-bot?lang=zh-CN
- 飞书开放平台：使用自定义机器人发送飞书卡片  
  https://open.feishu.cn/document/feishu-cards/quick-start/send-message-cards-with-custom-bot?lang=zh-CN
