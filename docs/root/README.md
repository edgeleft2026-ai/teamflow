# TeamFlow AI

TeamFlow AI 是一个 AI 驱动的项目管理助手。它通过感知项目事件、做出规则/策略/LLM 决策，并调用飞书动作来完成提醒、同步、审批和日程协作。

## 快速验证

```bash
python -m pip install -r requirements.txt
python -m pip check
python -m pytest tests/ -q
python run.py
```

服务启动后访问：

- `http://localhost:8000/health`
- `http://localhost:8000/health/detailed`
- `http://localhost:8000/docs`

## 文档

- `DESIGN.md`：架构和实现边界。
- `USAGE.md`：配置、API 和运行方式。
- `TODO.md`：当前完成状态和后续增强。
