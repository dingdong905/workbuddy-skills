---
name: bk-ce-deploy-fix
description: 蓝鲸智云社区版（BKCE 7.x）在 K8s（helm/helmfile）部署的排障方法论："部署材料留空待初始化"模式识别、helm release failed 误判与 no-diff 跳过陷阱、job 依赖链 rerun、镜像离线供应链验证、bk-apigateway/ESB 404 分层排查、SaaS 未注册 iam 与网关资源未导入排查修复、apiserver [::1] crash 循环修复、JVM 无界增长封顶与内存安全滚动、paramiko 远程操作标准模式、部署前四维评估（安全基线/资源画像/版本兼容/文档深读）。当蓝鲸 SaaS 部署卡住、job/pod 起不来、ESB compapi 404、bkrepo/bkjob 认证失败、CMDB authorize 1199046、apiserver CrashLoopBackOff、节点内存挤压 etcd 慢/OOM 连环、平台落地前评估时使用。
---

# 蓝鲸 K8s 部署排障（bk-ce-deploy-fix）

2026-10-10 bk7219 项目（V7.2 六核心 + bk-job，6 节点 K8s，无公网）20 小时攻坚实证沉淀。

## 铁律 1：优先排查"部署材料留空待初始化"

蓝鲸 chart 有一类系统性缺陷：**官方要求部署方自生成并填入 values/初始化的项，chart 里留空且不校验**，服务起来就炸。遇到认证失败/初始化失败，先扫 values 里"注释说部署时生成填入 + 值为空字符串"的键：

| 组件 | 留空项 | 症状 | 修复 |
|---|---|---|---|
| bk-repo | admin 用户（chart 无任何初始化 job/hook） | `admin:blueking` Basic 401，mongo user 表空 | 自签 JWT（secretKey 默认 `secret@key`，HS512，key padEnd 64 字节，头 `X-BKREPO-SECURITY-TOKEN`，payload 仅 iat/exp）调 `POST /service/user/create` |
| bk-job | `job.security.privateKeyBase64/publicKeyBase64` | gateway/file-worker/assemble 崩溃：`rsaPrivateKeyBase64.len=0` | openssl 生成 RSA2048，**PKCS8 私钥/SubjectPublicKeyInfo 公钥的 PEM 全文（含头尾换行）整体 base64**，写入 `bkjob-custom-values.yaml.gotmpl`（不存在则创建，missingFileHandler=Warn 不报错）后重新 helmfile apply |
| bk-job | `job.encrypt.password`（必填） | 服务启动失败 | 部署模板已含默认值则跳过；空则必须显式设置 |

排查命令模式：`grep -n -B4 -A8 "security\|jwt\|password" charts-product/<chart>-*.tgz` 解出的 values.yaml 中找空值+注释对。

## 铁律 2：helm release failed ≠ 资源没部署

`helm --wait --timeout 600s` 超时即标 failed，但**资源实际已建出**。看到 `failed` 先 `kubectl get deploy,sts,job,pod -l app.kubernetes.io/instance=<name>` 看实际状态，再决定是 upgrade 还是只修单个资源。修复 values 后 rerun：`helmfile -f base-blueking-local.yaml.gotmpl -l seq=<nth> apply`（147 上 root 跑，部署资产在 `/root/bkce7.2-install/blueking`）。

## 铁律 3：job 依赖链——init 容器在等谁

蓝鲸 job 的 init 容器是 `k8s-wait-for job/<前置job>`（镜像 groundnuty/k8s-wait-for）。job 卡 Pending/Init 时：
1. `kubectl get pod <job-pod> -o jsonpath="{.spec.initContainers[*].args}"` 拿前置 job 名
2. 前置 job 失败 → 看其日志修根因
3. rerun job：删 job 后从 helm 模板重建（`kubectl get job <name> -o yaml > j.yaml` 清理 status/ownerReference/selector 后 `kubectl apply`），或用 /tmp/rerun_job.py 工具

**Init:Error 的 pod 可能只是重试残骸**：job 有 backoffLimit，失败 pod 留着但 job 整体 Complete。判定以 `kubectl get job` 的 COMPLETIONS 为准，别被残留 pod 带偏。etcd leader 切换（`etcdserver: leader changed`）会产生这类瞬时 Init:Error。

## 铁律 4：镜像离线供应链三层验证

无公网集群 pod ImagePullBackOff 时按序验证：
1. 本地 registry 有没有：`curl http://147:5000/v2/_catalog` + tags
2. 节点 containerd mirror 配置：`/etc/containerd/certs.d/<registry>/hosts.toml` 指向本地 registry（hub.bktencent.com → 147:5000）
3. 三层都通才 helmfile apply，否则先把镜像推入 registry（batch_pull 流程）

## 铁律 5：ESB/apigateway 404 分层排查（管理面 vs 数据面 vs 微网关同步）

症状：`/api/c/compapi/**` 或 `/api/bk-<gw>/prod/**` 404。

1. **辨层**：响应头 `X-Bkapi-Error-Code: 1640401` = apigateway 应用层 404（路由缺失）；html 404 = ingress 层。
2. **管理面**（dashboard pod，`kubectl exec ... -- python manage.py shell`，nohup 落盘跑）：
   ```python
   from apigateway.core.models import Gateway, Resource, Release, ResourceVersion
   gw = Gateway.objects.get(name="bk-esb")  # Resource 定义数、Release 是否存在
   ```
   定义在（如 bk-esb Resource 2255 条）→ 问题在数据面。
3. **数据面**：APISIX + etcd（prefix `/bk-gateway-apisix`，root 凭据在 secret `bk-etcd/etcd-root-password`）：
   ```bash
   etcdctl --user root:$PASS get /bk-gateway-apisix/routes --prefix --keys-only | grep -c <关键词>
   ```
   路由数 < Resource 数 → 同步不完整。
4. **修复**：共享微网关（bk-esb/bk-cmdb 等都是）的 Release→etcd 同步用专用命令：
   ```
   python manage.py sync_releases_to_shared_micro_gateway_parallel --gateway-names <gw>
   ```
   `diff_and_make_new_release --run --pub` 只管"标准网关"（会报"不能发布的环境=N"——那是共享微网关，此命令对它们无效）。
   **慢 etcd 幂等收敛规律**：bk-etcd-0 磁盘慢（health 提交 835ms）时大批量 put（2000+ 资源）必超时丢一批——同步命令幂等，**每重跑一遍多收敛一批**（实测 bk-esb 三轮：路由 165→403→515、usermanage 0→18、v2/cc 183→198=ORM 定义 100%）。重跑是正解，别去修 etcd。
5. ESB compapi 流量路径：`/api/c/compapi/*` → `_bk-esb-compapi-legacy-route`（etcd）→ proxy-rewrite → localhost:6006 内部二次匹配 bk-esb 正式路由 → 缺路由即 404。

## 铁律 6：paramiko 远程操作标准模式（防挂起/防转义）

- **长命令一律 nohup 落盘 + 轮询**：paramiko exec >30s 会 socket.timeout。落盘文件 + done 标记 + 轮询间隔 10s。
- **启动命令防挂起写法（v3 定稿）**：nohup 后台进程持有 stdout 会让 channel 不 EOF。标准姿势：sftp 上传 launcher（内含 `nohup ... > /tmp/x.out 2>&1`，done 标记写 `echo "EXIT=$?" > /tmp/x.done` 带退出码），远端先 `sudo rm` 旧输出/done 文件，再 `sudo -n bash -c 'nohup bash /tmp/launch.sh > /dev/null 2>&1 &'`，容忍启动命令超时，轮询落盘。**勿用双引号包 payload、勿预创建输出文件、勿 `>>` 追加**（root bash 打不开 it 属主文件 → Permission denied 假失败）。
- **严禁 python -c 嵌复杂 shell**（`$()`/引号嵌套必翻车）：一律写本地 .py 文件。docker exec/kubectl exec 里的多行脚本用 base64 注入。
- **输出收敛**：远端输出先 grep/awk 过滤再回传，禁止全量 dump 本地 head。
- kubectl 需 `sudo`（it 用户无 ~/.kube/config 时）。
- **本地 run_in_background 禁止 paramiko**：后台沙箱读 SSH 私钥报 PermissionError: [Errno 13]——轮询一律前台周期跑。
- **跳板链路姿势**：paramiko 连 A 机后中转 B 机，必须以登录用户直接 `ssh -o BatchMode=yes it@B '...'`；写 `sudo -n bash -c 'ssh ...'` 是 root 在执行 ssh——root 没有对 B 的免密钥 → `Permission denied (publickey)`，表象像网络故障实为身份错误。

## 铁律 7：SaaS 未注册 iam 的排查与修复

症状：SaaS 调 CMDB/iam 报 authorize 失败——CMDB 侧 `1199046 Authorize request failed`、iam DB `sql: no rows in result set`（查无 bk_cmdb 行）、adminserver 周期同步报 `get system info error: Not Found`。**注意 CMDB/iam 日志只记失败不记成功，静默即成功**。

根因模式（"留空待初始化"的变体）：各 SaaS chart 自带 iam 注册 job（helm post-install hook），但 **values 开关默认 false + hook `ttlSecondsAfterFinished: 600` 跑完自删**——release failed 后想补跑也查不到 job。bk-cmdb 的注册 job 是 `templates/auth-job.yaml`，受 `iam.job.enabled` 控制（默认 false）。

修复（手动补调注册接口，以 bk-cmdb 为例）：
```bash
kubectl exec -n blueking deploy/bk-cmdb-adminserver-pod -- curl -s -m 60 -X POST \
  -H "Content-Type:application/json" -H "X-Bkcmdb-User:migrate" -H "X-Bkcmdb-Supplier-Account:0" \
  --data '{"host": "http://bk-cmdb-auth.blueking.svc.cluster.local"}' \
  http://bk-cmdb-admin.blueking.svc.cluster.local/migrate/v3/authcenter/init
# 期望 {"result": true, "bk_error_code": 0}
```
然后删受影响 SaaS 的 pod 重建。host 参数填该 SaaS 自己的 authserver ingress 地址（chart values `authserver.ingress.host`）。

命名坑：iam 工作负载叫 `bkiam-*`（无横杠，grep 'bk-iam' 搜不到）；`bkiam-migrate-1` 只做 schema 迁移（Applied 32 migrations）不种子系统；SaaS→iam 直连 `http://bkiam-web` 不经网关（路由同步不背锅）。可参照成功范式：bk-user 的 migrate-iam job 日志 `upsert_system id=bk_usermgr success!`。

**同款模式第三例——SaaS 网关资源未导入**：某网关 etcd 路由 0 且 ORM res=0 rel=0 rv=0（Gateway 记录和 prod Stage 却存在）=资源定义从未导入，不是同步失败（同步命令报 success 是空操作）。bk-user 根因：chart values `apigwSync.enabled` 默认 false，`migrate-apigateway.yaml` job 从未生成。修复：`kubectl exec <bk-user-api-web-pod> -- bash /app/sync_apigateway.sh`（幂等：config/stage/resources/docs + create_version_and_release，自动发布 Release 到 prod）。注意：apigateway ORM 的 FK 字段叫 `gateway` 不是 `api`（`Resource.objects.filter(gateway=gw)`）；冒烟路径必须先查 Resource 真实定义（如 bk-user v1 只有 login、profiles 在 v2），猜路径必 404。bcs-api-gateway/bcs-app 网关是预置空壳（BCS 未部署），预期空不修；bk-auth chart 无同步机制（底层直连服务）预期空。

## 铁律 9：apiserver 重启后 crash 循环（[::1]:6443 refused）

症状：kube-apiserver CrashLoopBackOff（每 ~3 分钟一轮），日志 `PostStartHook "rbac/bootstrap-roles" failed`，底层错误 `dial tcp [::1]:6443: connect: connection refused`；kubectl 全挂（websocket close 1006 abnormal closure）。**apiserver 自建集群起持续运行不重启则不爆，任一次重启即触发**。

根因：节点 IPv6 启用（lo 有 ::1）→ kubelet 给 pod 生成的 /etc/hosts 含 `::1 localhost` → apiserver self-check 连 `[::1]:6443`，但 apiserver 无 `--bind-address` 参数时默认只绑 0.0.0.0（IPv4）→ refused → PostStartHook fatal。

修复（一行，kubelet 自动重建）：
```bash
cp /etc/kubernetes/manifests/kube-apiserver.yaml /etc/kubernetes/manifests/kube-apiserver.yaml.bak
sed -i '/--secure-port=6443/a\    - --bind-address=::' /etc/kubernetes/manifests/kube-apiserver.yaml
# ~2 分钟后验证：crictl ps | grep apiserver（attempt 不再递增）+ ss -tlnp | grep 6443 + kubectl get --raw /readyz
```
`--bind-address=::` 是 IPv6 双栈通配（v4 连接照常），对现有客户端无影响。**多 master 集群所有节点是同款炸弹，修复一台验证后应立即批量加固其余 master**。抢修过程中 kubectl 不可用时用 `crictl ps/logs` + `/var/log/pods/` 直查。

## 铁律 8：release failed→deployed 翻转（helmfile no-diff 跳过陷阱）

`helmfile apply` 对 **failed 但资源全在** 的 release：渲染 diff 无变化 → **8 秒正常退出、日志仅一行 "Comparing release=..."（~71 字节）** → 不执行 upgrade → release 永远停在 failed。别误判为 OOM/崩溃（先查 done 标记里的退出码）。

正解：直接 helm 强制 upgrade，复用旧渲染 values 免重拼密钥链：
```bash
helm upgrade <release> charts-product/<chart>-<ver>.tgz -n blueking --reuse-values --wait --timeout 20m
```
已完成的 migration hook job 不会重跑（无扰动），成功即翻 deployed。

## 铁律 10：JVM 无界增长的封顶修复（防内存挤压 etcd / OOM 连环）

症状与危害链：多 java 服务共存节点内存持续爬升（pod RSS 无上限增长，直到 cgroup limit OOMKilled"自愈"）。节点同时承载 etcd 时更危险：内存挤压 page cache → etcd apply 从 10ms 级劣化到秒级 → raft quorum 抖动 → **全集群 API 半瘫十余分钟**（多 master 冗余救不了共享短板节点，2026-10-12 实证）。根因：JVM 无 `-Xmx` 时默认 maxHeapSize=物理内存 1/4，RSS 无界。

修复三件套（以 bk-repo 为例，`BK_REPO_JVM_OPTION` env 统一控制微服务 JVM 参数）：
1. **封顶**：`kubectl set env deployment/<d> -n blueking BK_REPO_JVM_OPTION="-Xms128m -Xmx768m"`（Xms 小值利启动；heap+metaspace+堆外合计要给 cgroup limit 留 ~30% 余量）
2. **内存安全滚动**：先 `kubectl patch deployment <d> --type merge -p '{"spec":{"strategy":{"rollingUpdate":{"maxSurge":0,"maxUnavailable":1}}}}'`（先杀旧释放内存再起新；代价是单副本服务滚动中断 ~5 分钟）。分批执行（3-4 个/批、批间等全 ready），最重的服务放第一批验证堆够用，OOMKilled 就单独调大该服务
3. **防回冲**：同步写 helmfile values——chart 传参链 `.Values.common.jvmOption` → env。**幂等先行**：先 `grep -n '^common:'` 查顶层键，已存在则段内 sed 插入（`sed -i '/^common:/a\  jvmOption: "-Xms128m -Xmx768m"'` 纯追加无分组），盲目 `>>` 追加会 yaml duplicate key。写入前 `cp` 备份

认知要点（2026-10-12 实测）：Xms 只是初始 committed，G1 自适应扩张，启动 10 分钟 RSS 已爬到 480-866M——**别期待 RSS 停在低位，封顶才是核心价值**（旧实例无界涨到 2Gi limit 被杀）。堆封顶后 etcd 恢复 9-13ms。

两个伴生发现：**滚动=重新调度机会**——无 PV 依赖的 pod 滚动重建时 scheduler 按实时负载重新放置（gateway/auth 从内存紧张的 148 自动疏散到 147/149），紧张节点滚动前可预期此行为；**ps 辨服务类型**——bk-repo gateway 是 nginx 非 java，`grep app.jar` 统计 java 进程会漏它，java 数对不上先查镜像。

## 铁律 11：部署前深度评估（成本远低于事后补救，用户终局定案）

平台落地前先做四维评估（bk7219 全周期教训提炼，2026-10-12）：
1. **安全基线**：查目标版本官方安全更新/CVE 公告 + chart 默认凭据与密钥逐项盘点（实证：bk-repo 2026-08-24 安全更新已要求 `common.config.security.auth.jwt.secretKey` 随机化（`openssl rand -hex 32`），部署时未查 → 默认 secretKey 可伪造 admin JWT，事后轮换代价=已签发 JWT 全失效；铁律 1 的"留空待初始化"各案例部署前 grep values 皆可发现）
2. **资源画像**：组件资源行为模式 + 容量总账（实证：java 无 Xmx RSS 无界涨 → OOM 挤压 etcd 全集群 API 瘫——铁律 10 的封顶本可以是初始部署参数；组件稳态 RSS 之和 vs 节点容量逐节点核算，etcd 所在节点单独评估）
3. **版本兼容**：平台与基座支持矩阵（实证：K8s 1.35.8 与 cilium/kubeadm 不兼容，重建 1.30.9 耗四天）
4. **文档深读**：release notes/已知问题/security advisory（实证：多个坑官方文档可查，部署时没读）

事后攻坚 20 小时中，过半问题落在可预先评估范畴。

## 关键坐标（147 环境，跨会话有效）

- 部署资产：`/root/bkce7.2-install/blueking`（helmfile 主文件 base-blueking-local.yaml.gotmpl，seq=first..sixth）
- 本地 registry：147:5000；分析工具脚本库归档路径：见 example/local-coordinates.md
- bkrepo JWT：`POST /service/user/create`，body `{"userId","name","pwd","admin":true}`，密码服务端 MD5
- K8s etcd 与蓝鲸 bk-etcd 是两套：bk-etcd 单节点（blueking ns），APISIX 专用
- static pod（etcd/kube-apiserver）日志在 `/var/log/pods/<ns>_<pod>_<uid>/`，`journalctl -u etcd` 查不到——计数 0 是日志源错了，不是真没有慢操作；判定 etcd 健康用 `endpoint health/status --cluster` 实时探测
- 长链路下钻每 3 跳设中断检查点向用户小结（防静默超 5 分钟）
