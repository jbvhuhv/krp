# 贡献指南（CONTRIBUTING）

## 1. 环境准备

- Python 3.12+、Node.js 18+。
- 后端：

  ```bash
  cd backend
  cp .env.example .env          # 填入 MAAS_API_KEY 等配置
  python -m pip install -r requirements.txt
  python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
  ```

  > Windows 下若 `python` 是 Microsoft Store 占位程序，请改用 `py` 启动器，或先 `set PYTHON_CMD=<python 绝对路径>`（`scripts\setup.bat` 会按 `PYTHON_CMD` → `py` → `python` 顺序探测）。

- 前端：

  ```bash
  cd frontend
  npm install
  npm run dev
  ```

- 一键 CI（后端 pytest + 前端 build）：`scripts\ci.bat`。

## 2. 测试

- 必须在 `backend/` 目录下运行：`python -m pytest -v`。
- 当前基线：**234 个用例（全通过 / 5 xfail）**，禁止引入新的失败。
- 新增功能需补充对应测试。

## 3. 代码规范

- **Python**：4 空格缩进；命名 `snake_case`；日志统一使用 `app.core.logger.get_logger(__name__)`，禁止裸 `print`。
- **前端**：组合式 API `<script setup>`；2 空格缩进；统一日志使用 `@/utils/logger`，禁止散落的 `console.log`。
- **导入**：Python 使用绝对导入 `from app.xxx import yyy`；前端使用 `@/` 别名。
- **命名一致性**：字段、模型、接口路径在各层保持同名，避免同义不同名。
- 注释仅在必要时添加，不堆砌无意义注释。

## 4. 提交规范

- 提交信息格式：`<type>: <简短描述>`，`type` 取 `feat` / `fix` / `refactor` / `docs` / `test` / `chore`。
- 单次提交聚焦一件事，避免混入无关改动。
- 涉及行为变更时，同步更新测试与相关文档。

## 5. 目录约定

- 后端按业务域组织：`api/deps/`（依赖注入）、`services/`、`models/`、`schemas/`、`prompts/`。
- 前端 `views/` 按业务域分子目录；`api/` 按业务域拆分，并由 `api/index.js` 聚合导出。
- 文档集中存放于 `docs/`，按数字前缀排序（根 `README.md` 除外）。