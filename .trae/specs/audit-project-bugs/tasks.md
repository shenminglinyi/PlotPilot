# Tasks
- [x] Task 1: 执行静态代码扫描与依赖检查
  - [x] SubTask 1.1: 安装或使用现有的 Python 语法检查工具（如 `flake8`）。
  - [x] SubTask 1.2: 扫描整个 `application`, `domain`, `infrastructure`, `interfaces` 目录，记录并汇总所有发现的语法错误、未定义的变量等问题。
- [x] Task 2: 执行自动化测试套件
  - [x] SubTask 2.1: 使用 `pytest` 运行 `tests/` 目录下的测试用例。
  - [x] SubTask 2.2: 记录所有失败的测试用例及对应的错误堆栈。
- [x] Task 3: 修复发现的 Bug 与代码错误
  - [x] SubTask 3.1: 修复 Task 1 中发现的静态扫描错误（语法错误、未使用的/错误的导入）。
  - [x] SubTask 3.2: 修复 Task 2 中导致测试失败的代码逻辑 Bug（根据堆栈进行排查）。
- [x] Task 4: 最终验证
  - [x] SubTask 4.1: 重新运行静态扫描和测试套件，确认修复完成且未引入新问题。
- [x] Task 5: 二次深度审计
  - [x] SubTask 5.1: 运行 `pytest tests/unit` 进行回归测试，排查剩余未修复的断言错误及其他边界用例失败。
  - [x] SubTask 5.2: 使用类型检查工具（如 `mypy`）扫描核心领域模型与接口层，发现潜在的类型不匹配。
  - [x] SubTask 5.3: 针对扫描和测试发现的新一轮问题进行代码修复。
  - [x] SubTask 5.4: 确保二次修复后无新增崩溃。

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1, Task 2]
- [Task 4] depends on [Task 3]
- [Task 5] depends on [Task 4]
