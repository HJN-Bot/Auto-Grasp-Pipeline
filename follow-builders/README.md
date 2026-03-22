# Follow Builders - X信息雷达

X(Twitter)账号内容自动抓取与飞书同步Pipeline。

## 架构

```
GitHub Actions (每6小时)
    ↓
generate-feed.js ——→ feed-x.json
    ↓
follow_builders_bi2d.py ——→ 飞书Wiki
```

## 配置

### X白名单 (20人)
- **AI核心(8)**: karpathy, OpenAI, AnthropicAI, claudeai, GoogleDeepMind, GeminiApp, sama, demishassabis
- **Builder/创业(7)**: levelsio, natfriedman, garrytan, amasad, simonw, openclaw, trq212
- **中文KOL(5)**: dotey(宝玉), bozhou_ai(泊舟), WaytoAGI, Red_Xiao_, manateelazycat

配置位置: `config/default-sources.json`

### GitHub Actions Secrets
在 repo Settings → Secrets → Actions 中添加:
- `X_BEARER_TOKEN`: X API v2 Bearer Token (从 https://developer.x.com/ 申请)
- `SUPADATA_API_KEY`: Supadata API Key (可选,用于YouTube播客)

## 文件说明

| 文件 | 用途 |
|------|------|
| `config/default-sources.json` | X账号白名单配置 |
| `config/custom-x-sources.json` | 带分类的白名单元数据 |
| `scripts/generate-feed.js` | GitHub Actions主脚本,抓取X内容 |
| `feed-x.json` | 生成的feed数据 (自动更新) |
| `state-feed.json` | 去重状态 (自动更新) |
| `prompts/router-config.md` | 内容分类路由规则 |

## 本地测试

```bash
cd scripts
npm install
X_BEARER_TOKEN=xxx node generate-feed.js
```

## 依赖

- X API v2 (Bearer Token)
- Supadata API (可选,用于YouTube)
