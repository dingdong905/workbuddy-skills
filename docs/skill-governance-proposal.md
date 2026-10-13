# 已批准的案例迁移记录

2026-10-08 用户批准后，本清单对应补丁已执行；相邻 .patch 保留为审阅记录，不应重复应用。

影响 10 个文件路径。移动保留内容，同步引用并登记 example/index.json。

## 迁移项

- tech-mentor/references/topics/metallb.md → tech-mentor/example/topics/metallb.md
- ctf-solver/references/playbooks.md → ctf-solver/example/playbooks.md

## 需语义审阅的修改

- CTF 入口不再把本机路径、固定槽位与历史失败视为恒定事实；原入口完整保存在 example/historical-entry.md。
- 教学样例与当前用户学习状态分开，当前进度留用户项目。
- 来源许可、平台元数据保留；迁移不声称重新实测。

## 验证与备份

迁移后执行全量严格治理检查、受影响功能检查和 git diff --check。备份保存了源文件和已有未提交变更：D:/skills/audit-backups/skill-governance-approved-20261008-e5cfb637。
