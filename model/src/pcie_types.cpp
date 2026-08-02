// pcie_types.cpp — 枚举转字符串与 req_id 编解码
#include "pcie_types.h"
#include <cstdio>

namespace pcie {

const char* to_string(Fmt f) {
    switch (f) {
        case Fmt::T3DW_NO_DATA:   return "3DW/NoData";
        case Fmt::T4DW_NO_DATA:   return "4DW/NoData";
        case Fmt::T3DW_WITH_DATA: return "3DW/Data";
        case Fmt::T4DW_WITH_DATA: return "4DW/Data";
    }
    return "?";
}

const char* to_string(Type t) {
    // 注: MRd/MWr、IORd/IOWr、CfgRd0/Wr0、Cpl/CplD 等在规范中编码相同，
    // 靠 Fmt 区分；枚举值重复导致 switch case 唯一，故此处按编码分组。
    switch (t) {
        case Type::MRd:      return "Mem";
        case Type::IORd:     return "IO";
        case Type::CfgRd0:   return "CfgType0";
        case Type::CfgRd1:   return "CfgType1";
        case Type::Msg:      return "Msg";
        case Type::Cpl:      return "Cpl";
        case Type::CplLk:    return "CplLk";
        case Type::FetchAdd: return "FetchAdd";
        case Type::Swap:     return "Swap";
        case Type::CAS:      return "CAS";
        default:             return "?";
    }
}

const char* to_string(CplStatus s) {
    switch (s) {
        case CplStatus::SC:  return "SC";
        case CplStatus::UR:  return "UR";
        case CplStatus::CRS: return "CRS";
        case CplStatus::CA:  return "CA";
    }
    return "?";
}

const char* to_string(TxnClass c) {
    switch (c) {
        case TxnClass::CFG_READ:       return "CFG_READ";
        case TxnClass::CFG_WRITE:      return "CFG_WRITE";
        case TxnClass::MMIO_READ:      return "MMIO_READ";
        case TxnClass::MMIO_WRITE:     return "MMIO_WRITE";
        case TxnClass::DMA_WRITE:      return "DMA_WRITE";
        case TxnClass::DMA_READ:       return "DMA_READ";
        case TxnClass::MSG_MSI:        return "MSG_MSI";
        case TxnClass::MSG_INTX:       return "MSG_INTX";
        case TxnClass::MSG_ERR:        return "MSG_ERR";
        case TxnClass::CPL:            return "CPL";
        case TxnClass::ATS_TRANSLATE:  return "ATS_TRANSLATE";
        case TxnClass::ATS_INVALIDATE: return "ATS_INVALIDATE";
        case TxnClass::UNKNOWN:        return "UNKNOWN";
    }
    return "?";
}

uint16_t make_req_id(uint8_t bus, uint8_t dev, uint8_t fn) {
    return (static_cast<uint16_t>(bus) << 8) |
           (static_cast<uint16_t>(dev & 0x1F) << 3) |
           (fn & 0x07);
}

void split_req_id(uint16_t req_id, uint8_t& bus, uint8_t& dev, uint8_t& fn) {
    bus = (req_id >> 8) & 0xFF;
    dev = (req_id >> 3) & 0x1F;
    fn  = req_id & 0x07;
}

std::string format_req_id(uint16_t req_id) {
    uint8_t b, d, f;
    split_req_id(req_id, b, d, f);
    char buf[16];
    std::snprintf(buf, sizeof(buf), "%02x:%02x.%x", b, d, f);
    return buf;
}

}  // namespace pcie
