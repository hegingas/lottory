// pcie_types.h — PCIe 基础类型与枚举（对齐 PCIe Base Spec 6.0）
// 纯逻辑层：不依赖 SystemC，可独立编译测试。
#pragma once
#include <cstdint>
#include <string>

namespace pcie {

// ── TLP 格式（Fmt）──
enum class Fmt : uint8_t {
    T3DW_NO_DATA   = 0b00,  // 3 DW header, 无数据
    T4DW_NO_DATA   = 0b01,  // 4 DW header, 无数据
    T3DW_WITH_DATA = 0b10,  // 3 DW header, 带数据
    T4DW_WITH_DATA = 0b11,  // 4 DW header, 带数据
};

// ── TLP 类型（Type[4:0]）──
enum class Type : uint8_t {
    MRd      = 0b00000,  // Memory Read
    MWr      = 0b00000,  // Memory Write (与 MRd 同编码, 靠 Fmt 区分)
    IORd     = 0b00010,
    IOWr     = 0b00010,
    CfgRd0   = 0b00100,  // Type0 Config Read
    CfgWr0   = 0b00100,  // Type0 Config Write
    CfgRd1   = 0b00101,  // Type1 Config Read (桥下探)
    CfgWr1   = 0b00101,
    Msg      = 0b10000,  // Message (路由位 r[2:0] 见 msg_route)
    Cpl      = 0b01010,  // Completion
    CplD     = 0b01010,  // Completion with Data
    CplLk    = 0b01011,
    CplDLk   = 0b01011,
    FetchAdd = 0b01100,  // AtomicOp
    Swap     = 0b01101,
    CAS      = 0b01110,
    LPrfx    = 0b10000,  // Local Prefix
    EPrfx    = 0b10000,  // Extended Prefix
};

// ── 完成状态（Cpl Status[2:0]）──
enum class CplStatus : uint8_t {
    SC  = 0b000,  // Successful Completion
    UR  = 0b001,  // Unsupported Request
    CRS = 0b010,  // Configuration Request Retry Status
    CA  = 0b100,  // Completer Abort
};

// ── 消息路由（Type[2:0] 的 r 位）──
enum class MsgRoute : uint8_t {
    TO_ROOT      = 0b000,  // Assert/Deassert INTx 等
    BY_ADDRESS   = 0b100,
    BY_ID        = 0b101,
    FROM_ROOT    = 0b110,
    LOCAL        = 0b111,
    GATHERED     = 0b001,
};

// ── 常用消息编码 ──
enum MsgCode : uint8_t {
    MSG_INTX_ASSERT   = 0x20 | 0,  // INTx Assert (0x20-0x23)
    MSG_INTX_DEASSERT = 0x24 | 0,  // INTx Deassert (0x24-0x27)
    MSG_ERR_COR       = 0x30,      // Correctable Error
    MSG_ERR_NONFATAL  = 0x31,      // Non-Fatal Error
    MSG_ERR_FATAL     = 0x33,      // Fatal Error
    MSG_LATENCY_TOL   = 0x18,      // LTR
    MSG_OBFF          = 0x38,      // OBFF
    MSG_PM_PME        = 0x60,      // PME
    MSG_PM_TURN_OFF   = 0x25,      // PM Turn-Off (From Root)
};

// ── 事务类（模型内部逻辑分流）──
enum class TxnClass : uint8_t {
    CFG_READ,     // CfgRd0/1
    CFG_WRITE,    // CfgWr0/1
    MMIO_READ,    // MRd 下行
    MMIO_WRITE,   // MWr 下行
    DMA_WRITE,    // MWr 上行 (EP 写 host 内存)
    DMA_READ,     // MRd 上行 (EP 读 host 内存)
    MSG_MSI,      // Msg: MSI (作为写事务的别名路径, 见 msi_router)
    MSG_INTX,     // Msg: 传统中断
    MSG_ERR,      // Msg: 错误通知
    CPL,          // Cpl/CplD
    ATS_TRANSLATE,   // 预留: Translation Request
    ATS_INVALIDATE,  // 预留: Invalidation
    UNKNOWN,
};

// ── 辅助 ──
const char* to_string(Fmt f);
const char* to_string(Type t);
const char* to_string(CplStatus s);
const char* to_string(TxnClass c);
std::string format_req_id(uint16_t req_id);          // bbbbbbbbdddddfff
uint16_t make_req_id(uint8_t bus, uint8_t dev, uint8_t fn);
void split_req_id(uint16_t req_id, uint8_t& bus, uint8_t& dev, uint8_t& fn);

}  // namespace pcie
