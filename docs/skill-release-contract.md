# 内容版本与验收契约

维护入口为 `scripts/skill_release.py`，只用 Python 标准库。两平台分别保留独立副本，不链接运行时；参数必须明确平台、source checkout 和 runtime 根。

## 内容版本

内容版本采用完整技能目录的路径与原始字节 SHA-256，包括 SKILL.md、references、scripts、schema、agents、许可及案例；仅排除 .git 和 Python 缓存。换行差异也算漂移。Git 根、分支、HEAD、远端、仓库及技能脏状态另记，提交号不能代表未提交内容。审计将链接或 junction 标为 unverifiable，不跟随哈希；安装拒绝这些对象，避免跨平台共享。

审计区分 same_version、drift、not_installed、runtime_only。未安装可为有意选择；漂移不判断哪一边正确。审计不执行安装或平台重载。

## 报告与失效

`verify` 在命令前后核对技能内容及 `--input` 指定的评分、脚本和测试文件。报告包含原命令、输出、退出码、耗时、输入指纹及 Git 状态。验证运行中变化判失败，之后任何 subjects 或 inputs 变化使整份集成报告 applicable=false。维护者须列齐会影响结论的仓库级输入；技能目录内部已整体覆盖。

四类证据分别记 structure、unit、model_behavior、platform_native；缺报告为 not_run。关键词分数、命令成功、模型生成完成与语义通过互不替代。模型行为须保存固定配置、输入、原始输出、语义审阅及限制；通过原生 CLI 执行的模型场景也只证明该显式上下文，不能证明桌面自动发现。WorkBuddy 经 DSH 的跨模型运行不算 WorkBuddy 原生验收。

## 参数化用法

在平台仓库根运行，尖括号替换为实际路径：

```text
python -X utf8 -B scripts/skill_release.py --source <source> --platform codex audit --runtime <runtime> --output <new-audit.json>
python -X utf8 -B scripts/skill_release.py --source <source> --platform codex verify --skill <name> --input scripts/lint_skill_governance.py --kind structure --output <new-report.json> -- python -X utf8 -B scripts/lint_skill_governance.py
python -X utf8 -B scripts/skill_release.py --source <source> --platform codex install --runtime <runtime> --backup-root <backup-root> --skill <name> --expected-runtime-sha256 <audited-hash-or-absent> --report <current-report.json>
```

WorkBuddy 改 platform，并使用其独立源库和已核对的运行时路径。

只选择本次需要且已验收的技能。漂移先复核内容与来源，再传入审计的精确旧指纹；状态改变即停止。安装要求本版结构通过且所提供适用报告无失败；其他必要验收由交付者检查，结构通过不是充分的发布批准。先完整 staging，并复制校验持久备份（可跨卷），再将旧目标退让到运行时根以外的同卷恢复目录，换入 staging，验证实际字节；按实际完成阶段回滚，旧目标退让失败时保持原位。恢复副本不在 skills 扫描根内。不用覆盖复制合并旧文件。根许可和来源声明随备份凭证保存，技能内原生元数据原样保留。

所有报告用新文件名保留历史；清理备份需另行决定。外部评测依赖/服务版本及人工断言的真实性不由本脚本证明，报告不具密码学签名。
