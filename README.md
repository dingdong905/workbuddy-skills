# WorkBuddy Skills 中文增强集

面向 WorkBuddy 维护的个人 Skill 仓库。内容采用 WorkBuddy 的 frontmatter 格式，保留 triggers 与 agent_created 字段。

## Skills

| Skill | 用途 |
| --- | --- |
| concise-output | 控制输出规模，避免长回复被截断 |
| context-budget | 审计并减少上下文与 Token 浪费 |
| evidence-research | 多来源检索、证据分级与交叉核验 |
| grafana-pie-chart | Grafana 饼图（piechart）面板创建/修改的标准化流程，基于 ClickHouse 数据源 |
| memory-curator | 管理 WorkBuddy 的持久记忆和任务交接 |
| stock-deep-research | A 股基本面、财报、估值和深度研究 |
| tech-mentor | 面向知识、技能与修养主题的学以致用教学流程 |

tech-mentor 附带 MetalLB 教学主题，可作为构建其他课程的样板。

## 安装

把所需 Skill 的完整目录复制到当前 WorkBuddy 版本可识别的 Skills 目录，然后重新加载 WorkBuddy。请保留目录名、SKILL.md 以及 references 子目录的相对结构。

不同 WorkBuddy 版本的安装位置可能不同，以对应版本的官方说明为准。

## 使用注意

- 这些文件是 WorkBuddy Skill，不是 Codex 原生 Skill。Codex 校验器不接受 WorkBuddy 使用的 triggers 和 agent_created 字段。
- stock-deep-research 与 evidence-research 中提到的 growth-swing-trading 是可选协作 Skill，本仓库当前未包含；缺失时仍可独立完成研究，但不应假装已执行交易判断流程。
- 深度研究和股票分析必须核验实际来源、日期和数据口径，不得把模板当成事实。
- 不要把密码、API Key、Cookie、私钥、账号数据或真实个人记忆提交到仓库。
- dist 目录中的本地打包文件默认不纳入版本控制；使用仓库源文件作为可信版本。

## 来源与许可

仓库以 MIT License 发布。部分 Skill 基于既有开源 Skill 进行 WorkBuddy 适配，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

