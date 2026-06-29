# PRD: 图片生成与编辑接口请求体规范

本文档整理当前项目中所有与图片生成、图片编辑、参考图输入相关的请求体格式。除特别说明外，请求都需要携带：

```http
Authorization: Bearer <auth-key>
```

## 1. 文生图

接口：

```http
POST /v1/images/generations
Content-Type: application/json
```

完整请求体：

```json
{
  "model": "gpt-image-2",
  "prompt": "一只漂浮在太空里的猫，电影感，高清细节",
  "n": 1,
  "size": "1:1",
  "response_format": "b64_json",
  "stream": false,
  "history_disabled": true
}
```

最小请求体：

```json
{
  "prompt": "一只漂浮在太空里的猫"
}
```

字段说明：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|:--|:--|:--:|:--|:--|
| `model` | string | 否 | `gpt-image-2` | 图片模型，支持 `gpt-image-2`、`codex-gpt-image-2` |
| `prompt` | string | 是 | - | 生图提示词 |
| `n` | integer | 否 | `1` | 生成数量，范围 `1-4` |
| `size` | string/null | 否 | `null` | 图片比例，常用值：`1:1`、`16:9`、`9:16`、`4:3`、`3:4` |
| `response_format` | string | 否 | `b64_json` | `b64_json` 时返回 base64，同时也会保存并返回 `url`；其他值主要返回 `url` |
| `stream` | boolean/null | 否 | `null` | 是否流式返回 |
| `history_disabled` | boolean | 否 | `true` | 接口模型接受该字段，当前文生图处理逻辑基本不使用 |

## 2. 图片编辑：multipart 上传

接口：

```http
POST /v1/images/edits
Content-Type: multipart/form-data
```

表单请求体：

```text
model=gpt-image-2
prompt=把这张图改成赛博朋克夜景风格
n=1
size=1:1
response_format=b64_json
stream=false
image=@./input.png
```

多参考图：

```text
model=gpt-image-2
prompt=融合这些参考图的风格重新生成一张海报
n=1
size=16:9
image=@./input-1.png
image=@./input-2.png
```

multipart 图片字段支持以下名称，且可重复：

```text
image
image[]
images
images[]
image_url
image_url[]
```

普通字段说明：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|:--|:--|:--:|:--|:--|
| `model` | string | 否 | `gpt-image-2` | 图片模型 |
| `prompt` | string | 是 | - | 编辑提示词 |
| `n` | integer/string | 否 | `1` | 生成数量，范围 `1-4` |
| `size` | string/null | 否 | `null` | 图片比例 |
| `response_format` | string | 否 | `b64_json` | 返回格式 |
| `stream` | boolean/string/null | 否 | `null` | 支持 `true/false`、`1/0`、`yes/no`、`on/off` |
| `client_task_id` | string | 否 | - | 同步编辑接口可传但不要求；异步任务接口必填 |

## 3. 图片编辑：JSON 图片 URL

接口：

```http
POST /v1/images/edits
Content-Type: application/json
```

使用 `images` 数组：

```json
{
  "model": "gpt-image-2",
  "prompt": "把这张图改成赛博朋克夜景风格",
  "n": 1,
  "size": "1:1",
  "response_format": "b64_json",
  "stream": false,
  "images": [
    {
      "image_url": "https://example.com/input.png"
    }
  ]
}
```

使用单个 `image_url`：

```json
{
  "model": "gpt-image-2",
  "prompt": "参考这张图生成同风格头像",
  "image_url": "https://example.com/input.png"
}
```

使用单个 `image`：

```json
{
  "model": "gpt-image-2",
  "prompt": "参考这张图生成同风格头像",
  "image": "https://example.com/input.png"
}
```

支持的 URL 类型：

```text
https://example.com/input.png
http://example.com/input.png
data:image/png;base64,<base64>
```

远程图片下载限制：

```text
最大 50MB
响应 Content-Type 需要是 image/*，或可从 URL 后缀推断为图片
```

## 4. 图片编辑：JSON data URL

请求体：

```json
{
  "model": "gpt-image-2",
  "prompt": "把图片背景换成白色",
  "images": [
    {
      "image_url": "data:image/png;base64,<base64>"
    }
  ]
}
```

也支持：

```json
{
  "model": "gpt-image-2",
  "prompt": "把图片背景换成白色",
  "image": "data:image/png;base64,<base64>"
}
```

## 5. 图片编辑：JSON 纯 base64

对象写法：

```json
{
  "model": "gpt-image-2",
  "prompt": "把图片背景换成白色",
  "images": [
    {
      "b64_json": "<base64>",
      "filename": "input.png",
      "mime_type": "image/png"
    }
  ]
}
```

兼容字段写法：

```json
{
  "model": "gpt-image-2",
  "prompt": "把图片背景换成白色",
  "images": [
    {
      "base64": "<base64>",
      "file_name": "input.png",
      "mimeType": "image/png"
    }
  ]
}
```

直接字符串写法：

```json
{
  "model": "gpt-image-2",
  "prompt": "把图片背景换成白色",
  "image": "<base64>"
}
```

## 6. 异步文生图任务

接口：

```http
POST /api/image-tasks/generations
Content-Type: application/json
```

请求体：

```json
{
  "client_task_id": "task-001",
  "prompt": "一张未来城市天际线海报",
  "model": "gpt-image-2",
  "size": "16:9"
}
```

字段说明：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|:--|:--|:--:|:--|:--|
| `client_task_id` | string | 是 | - | 客户端任务 ID，用于轮询和前端状态关联 |
| `prompt` | string | 是 | - | 生图提示词 |
| `model` | string | 否 | `gpt-image-2` | 图片模型 |
| `size` | string/null | 否 | `null` | 图片比例 |

## 7. 异步编辑图任务

接口：

```http
POST /api/image-tasks/edits
```

multipart 请求体：

```text
client_task_id=task-002
model=gpt-image-2
prompt=把这张图改成水彩插画风格
size=1:1
image=@./input.png
```

JSON 请求体：

```json
{
  "client_task_id": "task-002",
  "model": "gpt-image-2",
  "prompt": "把这张图改成水彩插画风格",
  "size": "1:1",
  "images": [
    {
      "image_url": "https://example.com/input.png"
    }
  ]
}
```

异步编辑图复用 `/v1/images/edits` 的图片输入格式，但 `client_task_id` 为必填。

## 8. 查询异步图片任务

接口：

```http
GET /api/image-tasks?ids=task-001,task-002
```

该接口没有请求 body。`ids` 为空时返回当前身份下的任务列表；传入逗号分隔 ID 时按任务 ID 过滤。

## 9. Chat Completions 触发生图

接口：

```http
POST /v1/chat/completions
Content-Type: application/json
```

当 `model` 是 `gpt-image-2`、`codex-gpt-image-2`，或 `modalities` 包含 `image` 时，会走图片生成逻辑。

纯文生图：

```json
{
  "model": "gpt-image-2",
  "messages": [
    {
      "role": "user",
      "content": "生成一张雨夜东京街头的赛博朋克猫"
    }
  ],
  "n": 1,
  "stream": false
}
```

使用 `modalities` 触发生图：

```json
{
  "model": "auto",
  "modalities": ["image"],
  "messages": [
    {
      "role": "user",
      "content": "生成一张产品宣传海报"
    }
  ],
  "n": 1
}
```

带参考图：

```json
{
  "model": "gpt-image-2",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "参考这张图，把人物改成油画风格"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,<base64>"
          }
        }
      ]
    }
  ],
  "n": 1
}
```

Chat Completions 图片字段限制：

```text
参考图只解析 data:image/...;base64,... 格式
不会下载 http/https 远程图片 URL
```

## 10. Responses 触发生图

接口：

```http
POST /v1/responses
Content-Type: application/json
```

必须包含 `tools: [{"type": "image_generation"}]`，或使用 `tool_choice` 指定 `image_generation`。

字符串输入：

```json
{
  "model": "gpt-image-2",
  "input": "生成一张未来城市天际线海报",
  "tools": [
    {
      "type": "image_generation"
    }
  ],
  "stream": false
}
```

标准 input 数组：

```json
{
  "model": "gpt-image-2",
  "input": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "生成一张南京城市宣传海报"
        }
      ]
    }
  ],
  "tools": [
    {
      "type": "image_generation"
    }
  ]
}
```

使用 `tool_choice`：

```json
{
  "model": "gpt-image-2",
  "input": "生成一张未来感城市海报",
  "tool_choice": {
    "type": "image_generation"
  }
}
```

带参考图：

```json
{
  "model": "gpt-image-2",
  "input": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "参考这张图生成同风格海报"
        },
        {
          "type": "input_image",
          "image_url": "data:image/png;base64,<base64>"
        }
      ]
    }
  ],
  "tools": [
    {
      "type": "image_generation"
    }
  ]
}
```

Responses 图片字段限制：

```text
参考图只解析 data:image/...;base64,... 格式
不会下载 http/https 远程图片 URL
未传参考图时，当前实现会默认给生图请求附加 size=1:1
```

## 11. 不属于当前生图链路的接口

`POST /v1/messages` 当前实现是 Anthropic Messages 兼容的文本与工具适配入口，没有接入图片生成后端。因此本文档不把它列为生图或编辑图请求体。
