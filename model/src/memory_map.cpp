// memory_map.cpp — host 地址解码实现
#include "memory_map.h"

namespace pcie {
namespace map {

decode_result decode_host_addr(uint64_t addr) {
    decode_result r;
    if (addr >= SMMU_BASE && addr < SMMU_BASE + SMMU_SIZE) {
        r.kind = decode_result::Kind::SMMU_REG;
        r.offset = addr - SMMU_BASE;
    } else if (addr >= RC_CFG_BASE && addr < RC_CFG_BASE + RC_CFG_SIZE) {
        r.kind = decode_result::Kind::RC_CFG_REG;
        r.offset = addr - RC_CFG_BASE;
    } else if (addr >= ECAM_BASE && addr < ECAM_BASE + ECAM_SIZE) {
        r.kind = decode_result::Kind::ECAM;
        uint32_t ecam = static_cast<uint32_t>(addr - ECAM_BASE);
        decode_ecam(ecam, r.bus, r.dev, r.fn, r.reg_off);
    } else if (addr >= MMIO_BASE && addr < MMIO_BASE + MMIO_SIZE) {
        r.kind = decode_result::Kind::MMIO;
        r.offset = addr - MMIO_BASE;
    } else if (addr >= MMIO64_BASE && addr < MMIO64_BASE + MMIO64_SIZE) {
        r.kind = decode_result::Kind::MMIO64;
        r.offset = addr - MMIO64_BASE;
    } else if (addr >= DDR0_BASE && addr < DDR0_BASE + DDR0_SIZE) {  // NOLINT
        r.kind = decode_result::Kind::DDR;
        r.ddr_off = addr - DDR0_BASE;
    } else {
        r.kind = decode_result::Kind::UNKNOWN;
    }
    return r;
}

}  // namespace map
}  // namespace pcie
