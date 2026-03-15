# 本地部署 Dify（Docker Compose）

```bash
git clone https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
docker compose up -d
```

访问：`http://localhost`

## 导入 DSL
- Dify Workflow -> Import DSL
- 选择 `dify/link-harvest-v1.dsl.yml`

## 建议
- 把抓取步骤放在 n8n（执行层）
- 把总结步骤放在 Dify（提示词层）
