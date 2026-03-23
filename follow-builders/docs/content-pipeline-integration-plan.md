# Follow-Builders 内容采集管线整合方案

> 版本: v1.0  
> 日期: 2026-03-23  
> 目标: 统一采集小红书/公众号/X/YouTube四类内容源

---

## 📌 项目背景

将现有 `follow-builders`（X/YouTube信息雷达）扩展为**统一内容采集管线**，新增公众号和小红书支持，形成四类主流中文内容源的自动化采集与摘要系统。

---

## 🏗️ 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Unified Content Ingestion Layer                   │
├──────────┬──────────┬──────────┬──────────┬────────────────────────┤
│   X/T    │ 公众号    │ 小红书   │ YouTube  │      RSS/Blog          │
│  (已有)  │  (新增)   │  (新增)  │  (已有)  │     (Karpathy List)    │
├──────────┼──────────┼──────────┼──────────┼────────────────────────┤
│ X API v2 │ wechat-  │ xhs-     │ Supadata │   RSS Parser           │
│ Bearer   │ exporter │ crawler  │ API      │   (92 feeds)           │
└──────────┴──────────┴──────────┴──────────┴────────────────────────┘
           │          │          │          │
           └──────────┴──────────┴──────────┘
                        │
                        ▼
           ┌─────────────────────────┐
           │   Content Normalizer    │
           │  统一字段标准化         │
           │  title/content/url/     │
           │  author/platform/date   │
           └─────────────────────────┘
                        │
                        ▼
           ┌─────────────────────────┐
           │   AI Processing Layer   │
           │  - Tier分类 (T0-T3)     │
           │  - 双语摘要 (Kimi)      │
           │  - 关键词标签           │
           │  - 质量评分             │
           └─────────────────────────┘
                        │
                        ▼
           ┌─────────────────────────┐
           │   Output & Routing      │
           │  - 飞书 Wiki            │
           │  - Dashboard更新        │
           │  - Telegram推送         │
           │  - GitHub存档           │
           └─────────────────────────┘
```

---

## 📋 四类内容源对比

| 维度 | X/Twitter | 公众号 | 小红书 | YouTube |
|------|-----------|--------|--------|---------|
| **数据源** | X API v2 | wechat-exporter | 逆向/Web | Supadata API |
| **Auth方式** | Bearer Token | Cookie扫码 | Cookie/Token | API Key |
| **采集频率** | 每6小时 | 每日1次 | 每12小时 | 每24小时 |
| **内容格式** | 短文本+图 | 富文本 | 图文/视频 | 视频+字幕 |
| **反爬强度** | 高 | 极高 | 极高 | 中 |
| **成本** | $0 | $0 (自托管) | 待定 | $0.001/次 |
| **优先级** | P0 | P1 | P2 | P0 |

---

## 🔧 技术方案详解

### 1. X/Twitter (已有)

```javascript
// 配置: config/sources/x.json
{
  "enabled": true,
  "accounts": ["karpathy", "sama", "OpenAI", ...], // 20个
  "api": {
    "bearerToken": "${X_BEARER_TOKEN}",
    "endpoint": "https://api.x.com/2/users/:id/tweets"
  },
  "schedule": "0 */6 * * *", // 每6小时
  "output": "feeds/feed-x.json"
}
```

### 2. 公众号 (新增)

```javascript
// 配置: config/sources/wechat.json
{
  "enabled": true,
  "accounts": [
    { "name": "机器之心", "biz": "MzA3MzI4MjgzMw==" },
    { "name": "量子位", "biz": "MzIzNjc1NzUzMw==" },
    { "name": "极客公园", "biz": "MzAwNDMyMTg2Ng==" }
  ],
  "api": {
    "type": "wechat-exporter",
    "url": "http://localhost:3001/api",
    "credentialRefresh": "weekly" // Cookie每周刷新
  },
  "schedule": "0 8 * * *", // 每日8点
  "output": "feeds/feed-wechat.json",
  "filters": {
    "minReadCount": 1000,
    "maxAgeDays": 7
  }
}
```

**部署方式**:
```yaml
# docker-compose.wechat.yml
version: '3'
services:
  wechat-exporter:
    image: wechat-article/wechat-article-exporter:latest
    ports:
      - "3001:3000"
    volumes:
      - ./data/wechat:/app/data
      - ./downloads:/app/downloads
    environment:
      - NODE_ENV=production
    restart: unless-stopped
```

### 3. 小红书 (新增 - Phase 2)

```javascript
// 配置: config/sources/xiaohongshu.json
{
  "enabled": false, // Phase 2 启用
  "accounts": ["账号1", "账号2"],
  "strategy": {
    "type": "headless-browser", // Playwright/Selenium
    "proxy": true, // 需要代理池
    "delay": "10-30s" // 随机延迟
  },
  "risk": {
    "level": "high",
    "fallback": "manual-queue" // 失败转人工队列
  }
}
```

### 4. YouTube (已有)

```javascript
// 配置: config/sources/youtube.json
{
  "enabled": true,
  "channels": [
    { "id": "UCvqbFHwN-nwalWPjqeGKUFQ", "name": "Andrej Karpathy" },
    { "id": "UCBJycsmDUvSSv-vb", "name": "Yannic Kilcher" }
  ],
  "api": {
    "provider": "supadata",
    "apiKey": "${SUPADATA_API_KEY}",
    "fields": ["transcript", "metadata"]
  },
  "schedule": "0 9 * * *", // 每日9点
  "output": "feeds/feed-youtube.json"
}
```

### 5. RSS/Blog (已有 - Karpathy List)

```javascript
// 配置: config/sources/rss.json
{
  "enabled": true,
  "feeds": "./config/karpathy-rss-92.opml",
  "filter": {
    "keywords": ["AI", "LLM", "agent", ...],
    "minLength": 500
  },
  "schedule": "0 */12 * * *",
  "output": "feeds/feed-rss.json"
}
```

---

## 📁 目录结构

```
follow-builders/
├── config/
│   ├── sources/
│   │   ├── x.json              # X配置
│   │   ├── wechat.json         # 公众号配置
│   │   ├── youtube.json        # YouTube配置
│   │   ├── xiaohongshu.json    # 小红书配置
│   │   └── rss.json            # RSS配置
│   ├── karpathy-rss-92.opml    # RSS订阅列表
│   └── custom-sources.json     # 用户自定义
├── scripts/
│   ├── fetch-x.js              # 已有
│   ├── fetch-wechat.js         # 新增
│   ├── fetch-xhs.js            # 新增(P2)
│   ├── fetch-youtube.js        # 已有
│   ├── fetch-rss.js            # 新增
│   ├── content-pipeline.js     # 统一处理
│   └── processors/
│       ├── x-processor.js
│       ├── wechat-processor.js
│       ├── xhs-processor.js
│       ├── youtube-processor.js
│       └── rss-processor.js
├── services/
│   └── wechat-exporter/
│       ├── docker-compose.yml
│       └── README.md
├── feeds/                      # 输出目录
│   ├── feed-x.json
│   ├── feed-wechat.json
│   ├── feed-youtube.json
│   └── feed-rss.json
├── processors/                 # 内容处理器
│   ├── normalizer.js           # 标准化
│   ├── ai-summarizer.js        # AI摘要
│   └── feishu-writer.js        # 飞书写入
├── .github/
│   └── workflows/
│       └── fetch-all.yml       # 统一GitHub Actions
└── docs/
    ├── karpathy-rss-coldstart-2025.md
    └── content-pipeline-integration-plan.md  # 本文档
```

---

## 🚀 实施路线图

### Phase 1: 基础整合 (本周)

| 任务 | 负责人 | 验收标准 |
|------|--------|---------|
| [ ] 部署 wechat-exporter | Jianan | Docker运行，API可访问 |
| [ ] 创建统一配置结构 | Andrew | 5个source.json文件 |
| [ ] 更新GitHub Actions | - | 统一workflow运行 |
| [ ] 公众号白名单定稿 | Jianan | 确定10-20个公众号 |

### Phase 2: 小红书调研 (下周)

| 任务 | 负责人 | 验收标准 |
|------|--------|---------|
| [ ] 调研开源xhs爬虫 | - | 找到可用方案 |
| [ ] PoC测试 | - | 单条采集成功 |
| [ ] 评估反爬成本 | - | 确定proxy预算 |

### Phase 3: AI摘要优化 (持续)

| 任务 | 负责人 | 验收标准 |
|------|--------|---------|
| [ ] 统一标准化输出 | Andrew | 四类内容统一格式 |
| [ ] 双语摘要模板 | - | 中英对照生成 |
| [ ] 飞书自动写入 | - | 每日摘要推送 |

---

## 💰 成本预估

| 组件 | 月度成本 | 备注 |
|------|---------|------|
| EC2 运行 | $30 | 已有 |
| X API | $0 | Free tier |
| YouTube API | $0.5 | Supadata |
| wechat-exporter | $0 | 自托管 |
| 小红书代理(如有) | $5-10 | 待定 |
| Kimi API | $2-5 | 摘要生成 |
| **总计** | **~$40** | 可控 |

---

## ⚠️ 风险提示

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 公众号Cookie失效 | 高 | 采集中断 | 每周手动刷新，监控告警 |
| 小红书反爬升级 | 中 | 采集失败 | 降低频率，人工兜底队列 |
| X API rate limit | 中 | 延迟 | 降级到缓存数据 |
| 飞书API限流 | 低 | 写入失败 | 批量写入，失败重试 |

---

## ✅ 下一步行动

1. **Jianan**: 提供公众号白名单（10-20个优先监控的账号）
2. **Andrew**: 创建配置文件和基础代码框架
3. **Jianan**: 部署 wechat-exporter Docker
4. **Andrew**: 更新 GitHub Actions 统一调度

---

*文档版本: v1.0*  
*最后更新: 2026-03-23*  
*相关PR: 待创建*
