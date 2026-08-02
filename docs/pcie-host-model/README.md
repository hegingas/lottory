# PCIe Host 行为模型（Virtual PCIe Host Model）

## 项目定位

在**没有真实 SoC/host 芯片**的条件下，验证 PCIe EP 类 DUT（网卡）在真实 host 软件栈下的行为。
用一个 SystemC TLM-2.0 行为模型模拟 host 侧（CPU 软件视角的寄存器/内存/中断语义），
通过 Synopsys PCIe RC VIP 将 TLM 事务转换为 PCIe 协议层事务，与 DUT 交互。

## 目标

| 目标 | 说明 |
|------|------|
| 功能验证 | DUT 在枚举/配置/MMIO/DMA/中断/虚拟化路径下行为正确 |
| 软件栈验证 | 真实 guest 软件（裸机固件 → Linux + 驱动 → 直通虚拟化）驱动 DUT |
| 平台复用 | host 模型独立于 DUT，换 DUT 只需重跑，不改模型 |

## 非目标（POC 阶段明确不做）

- 精确的 CPU 时序建模（QEMU TCG 为准，不做周期级）
- Cache 一致性协议建模（共享内存简化，无 cache 模型）
- 性能/吞吐量化指标（先功能，后性能冒烟）

## 技术栈

| 组件 | 选型 | 备注 |
|------|------|------|
| CPU 核模型 | QEMU（AArch64） | GreenSocs QEMU-SystemC 桥或 QEMU 官方 --enable-systemc |
| 行为建模 | SystemC + TLM-2.0（IEEE 1666） | 独立仿真环境 |
| PCIe 桥接 | Synopsys PCIe RC VIP | TLP 事务接口（格式待 FAE 确认，见 interfaces.md §7） |
| DUT | 网卡 EP（客户 IP） | 被测对象 |
| 构建 | CMake + g++ | 跨平台 |

## 文档索引

| 文档 | 内容 |
|------|------|
| [architecture.md](architecture.md) | 系统架构、模块职责、数据流、部署视图 |
| [interfaces.md](interfaces.md) | TLM-2.0 接口定义、GP 编码规范、地址映射表、协议约定 |
| [host-model-design.md](host-model-design.md) | host 模型各模块详细设计（配置引擎/SMMU/内存/中断/NIC） |
| [roadmap.md](roadmap.md) | 实施路线图（P0~P5）、验收标准、风险登记表 |
| [linux-deployment.md](linux-deployment.md) | Linux 部署指南：环境搭建、VIP 集成、QEMU-SystemC 桥、Linux guest 软件栈 |

## 目录结构（规划）

```
pcie-host-model/
├── docs/                  # 本文档集
├── model/                 # host 行为模型 SystemC 源码
│   ├── include/           # 头文件（模块类、GP 扩展字段、常量定义）
│   ├── src/               # 实现
│   ├── config/            # 地址映射、BAR 分配、参数配置
│   └── tests/             # TLM 级单元测试
├── qemu-bridge/           # QEMU-SystemC 桥接层（若需自维护）
├── guests/                # guest 软件栈（裸机固件 / Linux 配置 / 测试脚本）
├── scripts/               # 构建、运行、回归脚本
└── third_party/           # SystemC / TLM / QEMU-SystemC 版本锁定说明
```

## 术语表

| 术语 | 含义 |
|------|------|
| RC / EP | Root Complex / Endpoint |
| TLM-2.0 | IEEE 1666 事务级建模标准（b_transport/nb_transport/sockets/GP） |
| GP | Generic Payload，TLM-2.0 标准事务负载 |
| CFG | PCIe 配置空间访问（Type0/Type1） |
| MMIO | Memory-Mapped IO（对 EP BAR 空间的访问） |
| BAR | Base Address Register，EP 的地址窗口 |
| MSI / MSI-X | 消息中断（Message Signaled Interrupt） |
| SMMU | System Memory Management Unit（IOMMU），stage-2 地址转换 |
| ATS / ATC | Address Translation Services / Translation Cache |
| ITS | GICv3 Interrupt Translation Service（MSI→LPI） |
| IPA | Intermediate Physical Address（guest 物理地址） |
| DUT | Device Under Test（被测 EP） |

---

*状态：设计评审阶段（2026-08-02）。模型工作层级已定：host 模型构造/解析 **TLP 包**（事务层），经 TLM 承载 TLP 与 VIP 交互。P0 开工前需确认：① VIP 的 TLP 接口格式（interfaces.md §7 七问）② QEMU-SystemC 集成方案选型。*
