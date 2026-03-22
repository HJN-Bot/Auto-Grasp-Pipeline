# 路由配置文件

## 来源识别规则
- `mp.weixin.qq.com` → source=公众号
- `xiaohongshu.com` → source=小红书
- `xhslink.com` → source=小红书（先 resolve redirect）
- `youtube.com` / `youtu.be` → source=YouTube
- `x.com` / `twitter.com` → source=Twitter
- `follow-builders-feed` → source=订阅源

## 内容类型分类规则
优先检查标题和前200字，命中关键词即判定类型。

### A类 技术深度
- 中文：架构、实验、评测、论文、模型、部署、工程、方法、框架
- 英文：architecture, benchmark, paper, experiment, model, deploy, method

### B类 产品动态
- 中文：发布、上线、融资、收购、宣布、推出、合作
- 英文：launch, raises, funding, acquisition, announces, releases

### C类 观点思维
- 中文：我认为、我觉得、未来、反思、复盘、洞察、判断、预测
- 英文：I think, in my view, future of, prediction, reflection, lessons

### D类 工具资源
- 中文：工具、教程、开源、模板、资源、怎么用、手把手
- 英文：tool, tutorial, open source, how to, template, resource

## 冲突处理规则
- A+B → 选 A
- B+C → 选 B
- C+D → 选 C
- 都没命中 → 默认 C

## Token 路由规则
- 字数 < 3,000 → 完整处理
- 字数 3,000~10,000 → 分段处理（每段 ≤ 3,000字）
- 字数 > 10,000 → 轻量化模式（首尾 + 关键词扫描）
