# Linux 部署指南

Windows 上验证完成的 host 模型（132 断言全绿）移植到 Linux 的完整路径：
环境搭建 → 项目验证 → 接真 VIP → QEMU-SystemC 桥 → Linux guest 完整软件栈。

> 模型本体是纯 C++/SystemC，无平台依赖（Windows 特例仅 config_loader 用 FILE* 规避
> MinGW ifstream bug，Linux 上无害）。移植零代码修改。

## 1. 环境搭建（L1，约半天）

```bash
# Ubuntu/Debian 基础工具链
sudo apt update && sudo apt install -y build-essential cmake ninja-build git

# SystemC（推荐 3.0.1 源码编译；apt 的 libsystemc-dev 为 2.3.x 亦可）
wget https://www.accellera.org/images/downloads/standards/systemc/systemc-3.0.1.tar.gz
tar xzf systemc-3.0.1.tar.gz && cd systemc-3.0.1
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/systemc-3.0.1
make -j$(nproc) && make install
```

**项目构建与验证**：
```bash
cd model
cmake -B build -DCMAKE_BUILD_TYPE=Release -DSYSTEMC_HOME=/opt/systemc-3.0.1
cmake --build build -j$(nproc)
ctest --test-dir build
# 预期: 2/2 测试通过（core 63 + sc 69 断言）
```

**L1 验收**：
- [ ] ctest 100% 通过
- [ ] `./build/test_sc` 69 断言全绿（功能与 Windows 一致）

## 2. 接真 Synopsys VIP（L3，Linux + VCS 环境）

### 2.1 前置：FAE 确认（interfaces.md §7 七问）

| # | 确认项 | 影响 |
|---|--------|------|
| 1 | VIP TLP 事务接口形式（TLM socket / DPI / 队列 API）与字段命名 | 桥接层设计 |
| 2 | 是否透传原始 TLP 头字段 | 生成器自由度 |
| 3 | ATS Translation 透传 | P4 ATS 可验性 |
| 4 | 错误注入（UR/CA/poisoned） | 错误路径范围 |
| 5 | link 事件通知方式 | 启动时序 |
| 6 | ECRC 生成/校验归属 | TD 位处理 |
| 7 | Cpl 返回通道（同 socket 或独立） | 挂起表接线 |

### 2.2 集成方案（推荐）

```
┌─ UVM testbench ──────────────────────────────┐
│  ┌──────────────┐   DPI/TLM 桥   ┌─────────┐ │
│  │ Synopsys VIP │◄──────────────►│ host 模型│ │
│  │ (TLP 事务对象)│                │ (tlp_engine)│
│  └──────────────┘                └─────────┘ │
└──────────────────────────────────────────────┘
```

1. **传输格式**：`tlp_transaction::to_bytes()/from_bytes()`（header+payload 字节流）
   作为桥的线上格式——VIP 的 TLP 事务对象 ↔ 字节流，写薄转换层
2. **mock 保留**：mock_vip_tgt/init 继续做单元测试；真 VIP 场景做回归
3. **接线点**：替换 `tlp_engine` 的 `s_vip_tx/s_vip_rx/s_resp_tx` 三个 socket
   的目标端（TLM 桥或 DPI 封装）
4. **回归策略**：mock 场景与 VIP 场景共享同一套测试驱动（test_driver 结构）

### 2.3 风险

- VIP 字段命名/封装差异 → 转换层吸收（R1 风险预案）
- 仿真器集成（VCS + UVM + SystemC 混仿）需要工具链支持：VCS 的 SystemC 支持需许可证

## 3. QEMU-SystemC 桥（L2，跑真实 guest 软件）

### 3.1 QEMU 编译（官方集成方案）

```bash
git clone https://gitlab.com/qemu-project/qemu
cd qemu
./configure --target-list=aarch64-softmmu \
    --enable-systemc --with-systemc=/opt/systemc-3.0.1
make -j$(nproc)
```

### 3.2 桥接点（对齐 interfaces.md §5 契约）

| 项 | 实现 |
|----|------|
| MMIO 映射 | QEMU virt machine 注册自定义设备，MMIO 窗口转 TLM `s_cpu` 事务 |
| 共享内存 | guest RAM 与 host 模型 mem_model mmap 同一物理页（免拷贝） |
| 中断 | host 模型 `irq_out[]` → QEMU GIC GPIO（SPI 段） |
| 时钟 | 无独立时钟域，host 模型纯 event 驱动 |

### 3.3 guest 软件栈（递进）

```
阶段 1: 裸机固件（枚举 → BAR → MMIO → 中断）—— 对应 P1~P3 软件视角
阶段 2: U-Boot / 最小 Linux（lspci 看到 DUT）—— 对应 L4
阶段 3: Linux + arm-smmu-v3 + vfio-pci 直通 —— 对应 L5（SMMU 对齐）
```

## 4. Linux guest 完整软件栈（L4/L5）

### 4.1 SMMU 对齐（最大工作量）

当前模型：测试窗口直写 TLB（`REG_TEST_TLB_*`）。
Linux `arm-smmu-v3` 驱动会按真实寄存器语义配置，需补：

| 项 | 现状 | 对齐内容 |
|----|------|----------|
| STE 布局 | 无（仅记录 STRTAB_BASE） | 线性流表解析（POC 单 STE 线性表） |
| CMDQ | 未消费 | TLBI/CFGI 命令消费（POC：CFGI 清缓存，TLBI 记日志） |
| 页表遍历 | 无 | stage-2 最小遍历（4KB 页表）或缓存命中 + TLBI 全清兜底 |
| EVENTQ | 简化故障记录 | 对齐 SMMUv3 EVENTQ 格式 |

**策略**：先「缓存命中路径 + TLBI 全清兜底」让 Linux 驱动跑通，再补页表遍历——
别一上来全实现。

### 4.2 直通验证路径

```
Linux guest ── arm-smmu-v3 驱动配置 SMMU 模型
          ── vfio-pci 直通 → VM 内驱动 DUT
          ── SMMU 转换 + MSI 直通验证
```

## 5. 里程碑与决策点

| 里程碑 | 内容 | 预估 | 依赖 |
|--------|------|------|------|
| L1 | Linux 环境 + ctest 全绿 | 半天 | 无 |
| L2 | QEMU-SystemC 桥 + 裸机 guest 枚举 DUT | 1-2 周 | L1 |
| L3 | VIP 集成 + 回归 | 1-2 周 | L1 + FAE 确认 |
| L4 | Linux guest + lspci + 驱动加载 | 1-2 周 | L2 |
| L5 | SMMU Linux 对齐 + vfio 直通 | 2-4 周 | L4 |

**决策点（先想清楚再动工）**：
1. VIP 桥接方式——FAE 七问确认前不写桥代码（interfaces.md §7 是开工令）
2. QEMU 集成——QEMU 官方 `--enable-systemc` 优先（API 稳定），qbox 备选
3. SMMU 对齐——缓存命中 + TLBI 全清先跑通，页表遍历后补

## 6. 已知 Windows 特例（Linux 无需处理）

| 项 | Windows 情况 | Linux |
|----|-------------|-------|
| config_loader | FILE* 规避 MinGW ifstream O1+ 段错误 bug | 正常 |
| pthread 链接 | CMake 显式 `pthread` | 系统库，无需特殊处理 |
| 编译器 | MinGW GCC 16.1.0（含工具链 bug） | 系统 GCC（无该 bug） |
| ninja 启动崩溃 | git bash 下 MSYS2 编译器崩溃（用 MinGW-Builds） | 不适用 |
