# 实施路线图与风险登记

## 1. 阶段总览

```
P0 骨架 ──► P1 枚举配置 ──► P2 MMIO+DMA ──► P3 中断 ──► P4 SMMU/虚拟化 ──► P5 NIC 全路径
(连通)      (能看到DUT)     (数据通路)      (中断闭环)    (Linux直通)      (收发包)
```

每阶段含：**目标 / 交付物 / 验收标准 / 前置依赖**。

---

## 2. P0 —— 骨架与连通性

**目标**：工具链全通——QEMU 软件栈、SystemC 模型、VIP 三方握手成功，
一个 TLM 事务从 QEMU 走到 VIP 再回来。

**交付物**：
- 工程骨架：CMake + SystemC/TLM 环境 + VIP 库链接（版本锁定说明）
- QEMU-SystemC 桥接通（GreenSocs qbox 或 QEMU 官方 --enable-systemc）
- host 模型空壳：rc_bus_ctrl 最小实现 + 4 个 socket 全接（cpu_target 只回 OK）
- 冒烟测试：QEMU 裸机 guest 写 host 模型寄存器 → 日志确认事务到达

**验收标准**：
- [ ] `cmake + build` 零告警通过
- [ ] QEMU 启动裸机镜像，guest 写 `0x0901_0000` → 模型日志打印 TLM 事务
- [ ] VIP 链路训练完成事件能被 host 模型感知（待确认项 #5）
- [ ] 共享内存：guest 写共享页 → host 模型读同一值

**前置确认**：VIP TLP 接口格式（见 interfaces.md §7 待确认清单七问）。

---

## 3. P1 —— 枚举与配置

**目标**：host 模型能完成对 DUT 的枚举、BAR 分配、MSI-X 配置。

**交付物**：
- 配置引擎完整实现（简化枚举 → 真实枚举）
- 设备表 + BAR 分配表
- guest 裸机枚举代码（P0 用写寄存器触发，P1 改为软件读 ECAM 语义）

**验收标准**：
- [ ] guest 软件枚举到 DUT 的 vendor/device ID（lspci 语义）
- [ ] BAR 分配正确写回 DUT（DUT 侧可读 BAR 值验证）
- [ ] MSI-X 表配置完成，vector→SPI 映射正确
- [ ] 配置错误路径：写无效 BAR → UR 响应（日志+报告）

---

## 4. P2 —— MMIO 与 DMA

**目标**：数据通路打通——guest 访问 DUT 寄存器；DUT DMA 到 host 内存。

**交付物**：
- MMIO 地址解码 + BAR 反查（rc_bus_ctrl）
- 内存模型 + 共享内存接通
- SMMU 旁路模式（identity）下 DMA 通路
- 测试：DUT 发起 DMA 写（VIP 注入）→ guest 读到数据

**验收标准**：
- [ ] guest MMIO 写/读 DUT 寄存器往返正确（含非对齐边界用例）
- [ ] DMA 写：EP 写共享内存 → guest 立即可见（无刷新操作）
- [ ] DMA 读：guest 写数据 → EP 读回一致
- [ ] 超长事务（>256B）拆分或报错行为明确（记录决策）

---

## 5. P3 —— 中断闭环

**目标**：DUT 发 MSI → host 模型 → QEMU GIC → guest 中断 handler 完整链路。

**交付物**：
- MSI 路由（SPI 直连模式）
- guest 中断 handler（裸机：统计中断次数）
- 测试：DUT 周期性发 MSI-X，guest 计数递增

**验收标准**：
- [ ] guest 每收一个 MSI 中断计数 +1（连续 100 次无丢失）
- [ ] 未使能 MSI 收到消息 → WARN 日志 + 不触发中断（模拟软件 bug 场景）
- [ ] 中断聚合：N 包触发一次（NIC 行为模块联调）

---

## 6. P4 —— SMMU 与虚拟化

**目标**：完整虚拟化路径——SMMUv3 stage-2 转换 + Linux 直通。

**交付物**：
- SMMUv3 模型：流表/CMD/EVENT/转换缓存（先模型寄存器直写，后真实驱动）
- Linux guest：`arm-smmu-v3` 驱动使能 + 设备直通（vfio-pci）
- ATS/ATC（依赖 VIP 能力确认 #2，若不支持则降级为模型内自测）

**验收标准**：
- [ ] 模型寄存器直写模式：转换表写入 → DMA 走转换 → 正确落点
- [ ] Linux `arm-smmu-v3` 驱动识别模型寄存器并正常初始化
- [ ] 直通 VM 内驱动 DUT（SMMU 转换 + MSI 直通）
- [ ] 转换故障：非法 IPA → EVENTQ 记录 → guest 软件可见

**风险**：Linux 驱动对 SMMU 寄存器语义的兼容性是最大工作量所在（见风险 R2）。

---

## 7. P5 —— NIC 全路径

**目标**：网卡真实交互——多队列收发包、中断聚合、流量模型驱动。

**交付物**：
- NIC 行为模块完整（队列管理/收发包/聚合）
- 流量模型配置 + 包校验（端到端比对）
- 性能冒烟：吞吐、中断频率统计

**验收标准**：
- [ ] TX 方向：guest 软件发包 → DUT 收包 → 校验载荷一致
- [ ] RX 方向：注入 N 包 → DUT DMA + MSI → guest 软件完整回收（无丢包）
- [ ] 多队列（4 队列）并发：各队列独立计数正确
- [ ] 中断聚合生效：N 包/次 配置可调，统计符合预期
- [ ] 性能冒烟报告：包/秒、中断频率（记录数据，不做量化目标）

---

## 8. 风险登记表

| # | 风险 | 等级 | 缓解措施 |
|---|------|:---:|----------|
| R1 | **VIP TLP 接口格式不匹配**（字段命名/封装形式与 tlp_ext 定义不同） | 🔴 高 | host 模型按 TLP 头字段设计（规范对齐），适配层（薄封装）吸收差异；开工前 FAE 确认 interfaces.md §7 七问 |
| R2 | **SMMU 模型与 Linux 驱动语义不兼容**（寄存器细节、中断/错误路径） | 🔴 高 | P4 前先做「寄存器直写」模式兜底；与 Linux 源码逐项对齐（arm-smmu-v3.c 寄存器访问清单） |
| R3 | QEMU-SystemC 版本 API 漂移 | 🟡 中 | 锁定版本组合（README 记录）；qbox 优先，退路 QEMU 官方桥 |
| R4 | TCG 仿真速度慢（Linux 启动分钟级） | 🟡 中 | P1-P3 用裸机 guest；P4 才上 Linux；并行跑多场景 |
| R5 | 共享内存一致性假设被 DUT 行为打破（如 DUT 依赖 fence 语义） | 🟡 中 | rc_bus_ctrl 预留 flush 事件；P2 测试覆盖 DMA+读序列 |
| R6 | 32k token 类输出超限/agent 失败（团队流程风险） | 🟢 低 | 工作流已有收敛+防御机制（本 repo 教训） |
| R7 | MSI-X 表与 DUT 实际实现不一致 | 🟢 低 | 配置引擎表与 DUT spec 对照评审；测试覆盖多 vector |

## 9. 里程碑时间表（人力：1 人，参考）

| 阶段 | 预计周期 | 依赖 |
|------|----------|------|
| P0 | 1~2 周 | VIP 确认（R1） |
| P1 | 1~2 周 | P0 |
| P2 | 1 周 | P1 |
| P3 | 1 周 | P2 |
| P4 | 3~4 周 | P3 + VIP ATS 确认 |
| P5 | 2~3 周 | P4（或 P3 后并行裸机版） |

> 时间仅为数量级参考；P4 的 Linux 对齐是主要不确定项。

## 10. 开工前 check-list

- [ ] Synopsys FAE 确认：VIP TLP 接口格式、ATS 透传、ECRC 处理、Cpl 返回通道（interfaces.md §7 七问）
- [ ] QEMU-SystemC 集成方案选型拍板（qbox vs 官方桥）
- [ ] DUT 网卡 spec 到手（BAR 布局、队列寄存器、MSI-X vector 数、DMA 语义）
- [ ] SystemC/VIP 许可与版本确认
- [ ] 本设计文档评审通过（地址映射表 v0.1 冻结）
