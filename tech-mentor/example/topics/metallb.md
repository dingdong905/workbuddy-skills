# MetalLB 主题包

## 主题类型

知识型为主（机制理解 + 5 章实验验证），第 5 章排障含技能型成分（排障手感靠练）。生产隔离红线适用：教学实验仅限测试环境，生产集群只读。

## 五维评分（2026-09-07 评定）

| 维度 | 分 | 理由 |
|---|---|---|
| 工作相关性 | 5 | 用户维护生产 K8s + 3 台裸金属集群，LoadBalancer 是裸金属环境刚需 |
| 知识半衰期 | 4 | ARP/BGP 是 30 年协议（5 分）；CRD/Helm 配置随版本变（3 分），综合 4 |
| 学习杠杆 | 5 | Service 机制是 K8s 网络地基，直通 Ingress / Gateway API / CNI / 网络排障 |
| 认知密度 | 4 | 核心就 2 组件 + 3 个 CRD，心智模型集中；官方文档较长需提炼 |
| 复用频率 | 4 | 裸金属集群长期运行，部署/排障周期性接触 |

**总分 22/25，无单项 ≤2 → 正式开包，完整教学循环。**

## 三层结论

### 深学层（心智模型）

1. K8s 流量两段论：集群内转发（kube-proxy iptables/IPVS）vs 集群外入口（NodePort / LoadBalancer）
2. type=LoadBalancer 在裸金属上 pending 的根因：云厂商 CCP 缺位，谁写 status 谁是 LoadBalancer
3. MetalLB 双组件架构：controller（IP 分配，写 svc status）与 speaker（流量宣告，DaemonSet）的解耦
4. L2 模式：ARP/免费 ARP 宣告、speaker leader 选举、单节点入口瓶颈、failover 行为
5. BGP 模式：BGP 会话建立、路由宣告、ECMP per-flow 哈希分流
6. IP 分配链路：IPAddressPool → svc 的 EXTERNAL-IP 状态机

### 会用层（操作能力）

1. Helm / manifest 部署 MetalLB
2. CRD 配置：IPAddressPool / L2Advertisement / BGPAdvertisement / BGPPeer
3. kube-proxy strict ARP（IPVS 模式）配合设置
4. 三大常见故障排障：svc pending、有 IP 不通、间歇性断连

### 略过层（不学，用到再搜）

1. FRR（容器路由守护进程）内部实现
2. speaker / controller 源码逐行
3. 版本 release notes 差异、CRD 字段全量枚举
4. BGP 高级特性调优：route reflector、community 属性、多 AS 设计
5. MetalLB 企业版 / 商业支持特性

## 学习路径（5 章）

### 第 1 章：为什么需要 MetalLB——Service 全景与 pending 之谜

- **心智模型**：流量两段论。kube-proxy 只管集群内（ClusterIP 转发规则），外部入口是另一段；云上由云厂商控制器填 EXTERNAL-IP，裸金属没人填 → 永远 `<pending>`。
- **实验 1.1**：创建一个 `type=LoadBalancer` 的 svc（或找现有 svc），`kubectl get svc` 观察 EXTERNAL-IP pending
- **实验 1.2**：`ipvsadm -Ln` 或 `iptables-save | grep <svc名>` 观察该 svc 的 ClusterIP 转发规则已存在 → 证明 kube-proxy 正常，缺的是外部入口段
- **预测点**：1.2 的规则存不存在？（存在——很多人以为 pending = 整条链路都没建）
- **检验题**：①kube-proxy 和 LoadBalancer 各负责哪段流量？②裸金属上 pending 的直接原因是什么？
- **预期误解**：以为 pending = 整条链路都没建（实际 ClusterIP 转发规则已存在，缺的只是外部入口段）；以为 LoadBalancer 是 kube-proxy 的功能（实际是外部组件的职责）
- **迁移题**：「功能已在、外部入口缺位」——这种「内部已通、入口缺失」的现象，在你排障过的其他场景出现过吗？（参考方向：内网 DNS 解析正常但公网不通、进程监听 localhost 而非 0.0.0.0）
- **可迁移模式**：分段定位——排障先切「这段流量归谁管」，再查该段责任人

### 第 2 章：MetalLB 架构——controller 与 speaker 分工

- **心智模型**：分配与宣告解耦。controller（单副本 Deployment）= IP 分配者，watch svc 从池里挑 IP 写 status；speaker（DaemonSet，每节点一个）= 宣告者，把「VIP 在我这」告诉外界。类比：物业（controller）发门牌号，保安（speaker）对外指路。
- **实验 2.1**：部署 MetalLB（helm install 或官方 manifest，严师模式下用户自己跑，AI 盯输出）
- **实验 2.2**：`kubectl -n metallb-system get pods -o wide` → 观察 speaker 每节点一个、controller 单副本
- **实验 2.3**：`kubectl -n metallb-system logs deploy/controller --tail=20` → 观察 watch/分配行为
- **预测点**：speaker pod 数量 = ？为什么是 DaemonSet 而不是 Deployment？
- **检验题**：①EXTERNAL-IP 是谁写进去的？②为什么拆成两个组件而不是一个？（提示：分配是集中决策，宣告需要每节点在场）
- **预期误解**：以为 IP 是 speaker 分配的（实际 controller 分配、speaker 只宣告）；以为 speaker 是单副本 Deployment（实际 DaemonSet 每节点一个——宣告必须在场）
- **迁移题**：集中决策 + 分散在场的解耦架构，你觉得还出现在哪些你已知的系统里？（参考方向：SDN 控制器与交换机、DNS 权威与递归、调度器与工作节点）
- **可迁移模式**：控制面/数据面分离——决策收敛到一处保证一致性，执行下沉到每处保证在场

### 第 3 章：L2 模式——ARP 宣告与 leader 节点

- **心智模型**：speaker 们通过 leader 选举出一个节点，由它对局域网应答 ARP「VIP 的 MAC 是我」。全部流量进这一个节点，再经 kube-proxy 二次转发到 pod。类比：小区唯一代收点，所有快递都进它家再分发。反直觉点：**不是轮询负载均衡**。
- **实验 3.1**：配置 IPAddressPool + L2Advertisement → 创建 LoadBalancer svc → EXTERNAL-IP 从池中分配
- **实验 3.2**：集群外 `curl http://<VIP>:<port>` 验证通
- **实验 3.3**：客户端 `ip neigh`（或 `arp -n`）查 VIP 的 MAC → 到 leader 节点 `ip link` 对照网卡 MAC，确认流量入口是单节点
- **实验 3.4**（破坏性，需确认）：停 leader 节点 speaker → 观察重新选举 + 客户端 ARP 表更新 + 短暂中断窗口
- **预测点**：3.2 的流量会到哪个节点？为什么不是所有节点轮询接收？
- **检验题**：①L2 模式的负载均衡能力边界在哪？②leader 挂掉后客户端要等多久恢复，这段时间卡在哪个环节？（ARP 缓存老化/重宣告）
- **预期误解**：以为 L2 模式会把流量负载均衡到所有节点（实际全部进 leader 单节点）；以为 leader 故障切换无感知（实际有 ARP 老化/重宣告窗口，短暂中断）
- **迁移题**：为了避免多方冲突而选出一个代表应答——这个模式还在哪出现？（参考方向：keepalived/VRRP、Redis Sentinel 主从切换、会议室里指定一个发言人）
- **可迁移模式**：选主 + 故障转移——一致性优先的分布式协调，代价是单点与切换窗口

### 第 4 章：BGP 模式——路由宣告与 ECMP

- **心智模型**：每个 speaker 与上游路由器建 BGP 会话，宣告「到 VIP 的下一跳是我」。多节点同时宣告 → 路由器 ECMP 按 flow 哈希分流。类比：多个代收点同时向快递总部注册，总部按单号哈希分派。与 L2 根本差异：宣告对象是路由器（L3）不是交换机（L2），天然多路径。
- **实验 4.0**（环境准备）：环境无 BGP 路由器时，先在集群内/旁路跑一个 FRR 容器模拟上游路由器（教学时现场指导，属于会用层）
- **实验 4.1**：配置 BGPPeer + BGPAdvertisement → 观察 speaker 日志中会话 Established
- **实验 4.2**：FRR 侧 `vtysh -c "show bgp summary"` + `show ip route` → 看 VIP 路由多下一跳
- **实验 4.3**：外部多次 curl，在多个 speaker 节点观察连接分布（ECMP per-flow：同一源固定走同一路径）
- **预测点**：两条并发连接会分散到几个节点？同一客户端的重复连接呢？
- **检验题**：①L2 vs BGP 的宣告对象和流量模型差异？②BGP failover 比 L2 快还是慢，为什么？（路由收敛 vs ARP 老化）③为什么生产推荐 BGP？
- **预期误解**：以为 ECMP 会把单个连接的包分散到多个节点（实际 per-flow 哈希，同一连接固定走一条路径）；以为 BGP 故障切换更慢（实际路由收敛通常快于 ARP 老化）
- **迁移题**：多节点同时宣告、上游按流哈希分流——这个思想还出现在哪？per-flow 与 per-packet 分流各自会踩什么坑？（参考方向：LACP 链路聚合、anycast、DNS 轮询的本质差异）
- **可迁移模式**：宣告式多路径 + per-flow 哈希——去中心化扩展流量的标准姿势

### 第 5 章：排障实战——制造故障与恢复

- **心智模型**：排障链路 = 客户端 → (ARP/路由表) → 入口节点 → kube-proxy 规则 → endpoint → pod，逐段验证。三大故障族：pending（池耗尽/CRD 配错）、不通（宣告缺失/ARP 缓存陈旧）、间歇断（leader 抖动/BGP session 振荡）。
- **实验 5.1**（破坏性）：IPAddressPool 范围改到只剩 1 个 IP 且已占用 → 再建 svc → 预测现象 → `kubectl describe svc` 看事件定位
- **实验 5.2**（破坏性）：删 L2Advertisement → 预测：老客户端还通吗？新客户端呢？（ARP 缓存差异）
- **实验 5.3**（破坏性）：模拟 speaker 故障，观察 L2/BGP 各自的 failover 表现
- **预测点**：每个故障制造前先预测现象与恢复时间
- **检验题**：场景「svc 有 EXTERNAL-IP 但 curl 不通」——说出你排查顺序的前三步和每步看的证据。
- **预期误解**：一上来就查 pod 日志（应先沿路径分段验证：客户端 ARP/路由表 → 入口节点 → kube-proxy 规则 → endpoint → pod）；只查 svc 事件不看 ARP 层（不通 ≠ 分配问题）
- **迁移题**：把「沿路径逐段验证、每段找证据」的方法，套到你最近一次生产排障——你的分段点在哪、每段看什么证据？
- **可迁移模式**：链路逐段验证——任何「端到端不通」类问题，先画出完整路径，再逐段问「这段有证据说它通吗」

## 复习卡

（教学过程中每章通过后追加。示范：理解型出题——只收因果与推导，不收背诵）

```
[第1章] Q: 为什么裸金属上 type=LoadBalancer 的 svc 会一直 pending？（从流量两段推起）
A: 流量分两段：集群内转发由 kube-proxy 负责（规则已建好）；EXTERNAL-IP 需要集群外控制器来写——云上有云厂商组件，裸金属没有 → 没人写 → pending。I: 3

[第1章] Q: 已知 svc 的 ClusterIP 在集群内 curl 得通、外部访问 LoadBalancer IP 不通——中间断在哪一段？为什么？
A: 断在外部入口段。集群内规则存在证明 kube-proxy 正常；缺的是把 VIP 宣告给外部网络的角色（MetalLB 的 speaker）。I: 1

[第1章·迁移] Q: 「内部路径已通、外部入口缺位」的故障模式，你已知的其他系统里还有哪些实例？
A: 例：服务监听 127.0.0.1 而非 0.0.0.0（进程在、入口没开）；内网 DNS 正常但公网解析未配置。评判：能说出「功能在但入口未暴露」的因果结构即对。I: 7
```

## 学习状态

- 环境信息：58环境，多节点 K8s 集群，SSH + kubectl 访问。**具体地址/凭据待用户提供**；网络插件、已有组件待第 0 步环境接入时探测填写
- 摸底诊断：待做（建议诊断点：kube-proxy 转发机制、ARP 基础、BGP 是否接触过）
- 当前进度：未开始
- 未验证章节：无
- 卡点：无
