// memory_map.h — host 地址映射表（对齐 interfaces.md §3.1/§3.2）
// 纯逻辑层：窗口常量 + 解码规则（ECAM / MMIO / SMMU 寄存器 / RC 配置）。
#pragma once
#include <cstdint>
#include <optional>
#include "pcie_types.h"

namespace pcie {

// ── 地址窗口（v0.1 草案，与 interfaces.md §3.1 一致）──
struct addr_window {
    uint64_t base;
    uint64_t size;
};

namespace map {

// host 物理地址布局
inline constexpr uint64_t DDR0_BASE    = 0x0000'0000ULL;   // guest RAM（共享）
inline constexpr uint64_t DDR0_SIZE    = 0x4000'0000ULL;   // 1 GiB
inline constexpr uint64_t SMMU_BASE    = 0x0900'0000ULL;   // SMMUv3 寄存器
inline constexpr uint64_t SMMU_SIZE    = 0x0001'0000ULL;   // 64 KiB
inline constexpr uint64_t RC_CFG_BASE  = 0x0901'0000ULL;   // 配置引擎/总线控制器
inline constexpr uint64_t RC_CFG_SIZE  = 0x0001'0000ULL;   // 64 KiB
inline constexpr uint64_t ECAM_BASE    = 0x4000'0000ULL;   // PCIe 配置空间
inline constexpr uint64_t ECAM_SIZE    = 0x0080'0000ULL;   // 8 MiB (bus0~7, 对齐 roadmap P1 深度≤8)
inline constexpr uint64_t MMIO_BASE    = 0x5000'0000ULL;   // DUT BAR 窗口
inline constexpr uint64_t MMIO_SIZE    = 0x1000'0000ULL;   // 256 MiB
inline constexpr uint64_t MMIO64_BASE  = 0x80'0000'0000ULL;// 64-bit BAR 高窗口
inline constexpr uint64_t MMIO64_SIZE  = 0x10'0000'0000ULL;// 64 GiB

// MSI 地址窗口（host-model-design.md §4）：EP 写该窗口 = MSI 中断
// 地址布局: base + vector*4（POC 简化，每 vector 一个 4B 写）
inline constexpr uint64_t MSI_ADDR_BASE = 0xFEE0'0000ULL;
inline constexpr uint64_t MSI_ADDR_SIZE = 0x1'0000ULL;   // 64 KB

// ECAM 编码: [bus(8)][dev(5)][fn(3)][off(12)]
inline constexpr uint32_t ECAM_OFFSET(uint8_t bus, uint8_t dev,
                                      uint8_t fn, uint16_t off) {
    return (static_cast<uint32_t>(bus) << 20) |
           (static_cast<uint32_t>(dev) << 15) |
           (static_cast<uint32_t>(fn)  << 12) |
           (off & 0xFFF);
}

// ── 解码结果 ──
struct decode_result {
    enum class Kind { SMMU_REG, RC_CFG_REG, ECAM, MMIO, MMIO64, DDR, UNKNOWN } kind;
    // ECAM 时
    uint8_t bus = 0, dev = 0, fn = 0;
    uint16_t reg_off = 0;
    // MMIO 时（BAR 映射地址，低偏移）
    uint64_t offset = 0;
    // DDR / 共享内存时
    uint64_t ddr_off = 0;
};

// 解码 host 物理地址（SMMU 转换前，CPU 视角）
decode_result decode_host_addr(uint64_t addr);

// ECAM 解码（bus/dev/fn/off 拆分，供 CFG TLP 构造）
inline void decode_ecam(uint32_t ecam_addr, uint8_t& bus, uint8_t& dev,
                        uint8_t& fn, uint16_t& off) {
    bus = (ecam_addr >> 20) & 0xFF;
    dev = (ecam_addr >> 15) & 0x1F;
    fn  = (ecam_addr >> 12) & 0x07;
    off = ecam_addr & 0xFFF;
}

}  // namespace map
}  // namespace pcie
