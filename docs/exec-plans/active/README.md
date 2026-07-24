# Active Execution Plans

## Current Tasks

| ID | Title | Status | Package | Started |
|----|-------|--------|---------|---------|
| — | 完善 Harness 基础设施文件 | in_progress | all | 2026-05-27 |

## Active Plan: Harness 文件完善

**Goal**: 补充完善整个工程的 Harness 结构文件（.ai/, docs/, scripts/, templates/）

**Steps**:
1. [x] 编写 `docs/DEVELOPMENT.md` 开发指南
2. [x] 更新 `docs/exec-plans/` README 文件
3. [x] 更新 `.ai/CURRENT_FOCUS` 项目状态
4. [ ] 补充 `.ai/memory/` 经验教训记录
5. [ ] 运行 `make validate` 验证完整性

## How to Start a New Execution Plan

1. Create a new markdown file in this directory with a descriptive name
2. Use the design doc template from `docs/design-docs/template.md` for reference
3. Update this README to reference the new plan
4. Use `make checkpoint` to save progress checkpoints
