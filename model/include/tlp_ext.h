// tlp_ext.h — TLP 事务结构（对齐 PCIe Base Spec 6.0 头字段）
// 纯逻辑层：结构化 TLP 表示。将来经 TLM 扩展字段 (tlp_ext) 挂载到 GP，
// 或作为 payload 内嵌传输；字段命名与 interfaces.md §6.1 一一对应。
#pragma once
#include <cstdint>
#include <vector>
#include <cstring>
#include "pcie_types.h"

namespace pcie {

// ── TLP 头（显式字段，非位打包；serialize() 负责字节布局）──
struct tlp_header {
    // 通用字段（Byte0-3）
    Fmt      fmt        = Fmt::T3DW_NO_DATA;
    Type     type       = Type::MRd;
    uint8_t  tc         = 0;   // Traffic Class
    bool     th         = false;  // TLP Processing Hints
    bool     td         = false;  // 带 ECRC (TD=1)
    bool     ep         = false;  // Poisoned
    uint8_t  attr       = 0;   // [1]=No Snoop [0]=Relaxed Ordering
    uint8_t  at         = 0;   // Address Type (1=转换后地址)
    uint16_t length     = 0;   // 数据长度（DW 单位；0 表示 128B）

    // 请求 TLP（Byte4+）
    uint16_t requester_id = 0;   // bus:dev:fn
    uint16_t tag          = 0;   // 事务标签
    // Mem 请求
    uint64_t address      = 0;   // 64 位地址（低 2 bit 恒 0；3DW 头用低 32 位）
    uint8_t  be_first     = 0xFF;  // First DW Byte Enable
    uint8_t  be_last      = 0xFF;  // Last DW Byte Enable
    // Cfg 请求
    uint8_t  target_bus   = 0;   // 目标 bus
    uint8_t  target_dev   = 0;
    uint8_t  target_fn    = 0;
    uint16_t reg_off      = 0;   // 配置寄存器偏移 (低 12 bit)
    // Cpl 响应
    uint16_t completer_id = 0;
    CplStatus status      = CplStatus::SC;
    uint16_t byte_count   = 0;
    bool     bcm          = false;  // Byte Count Modifier
    // Msg
    uint8_t  msg_code     = 0;
    MsgRoute msg_route    = MsgRoute::TO_ROOT;
    // 请求-完成关联
    uint16_t cpl_requester_id = 0;  // Cpl 里的 Requester ID（=请求方）

    // ── 便捷构造 ──
    static tlp_header cfg_read(uint16_t req_id, uint16_t tag,
                               uint8_t bus, uint8_t dev, uint8_t fn,
                               uint16_t reg_off, bool type1 = false) {
        tlp_header h;
        h.fmt = Fmt::T3DW_NO_DATA;
        h.type = type1 ? Type::CfgRd1 : Type::CfgRd0;
        h.requester_id = req_id;
        h.tag = tag;
        h.target_bus = bus; h.target_dev = dev; h.target_fn = fn;
        h.reg_off = reg_off & 0xFFF;
        h.length = 0;
        return h;
    }

    static tlp_header cfg_write(uint16_t req_id, uint16_t tag,
                                uint8_t bus, uint8_t dev, uint8_t fn,
                                uint16_t reg_off, bool type1 = false) {
        auto h = cfg_read(req_id, tag, bus, dev, fn, reg_off, type1);
        h.type = type1 ? Type::CfgWr1 : Type::CfgWr0;
        h.fmt = Fmt::T3DW_WITH_DATA;
        h.length = 1;
        return h;
    }

    static tlp_header mmio_read(uint16_t req_id, uint16_t tag,
                                uint64_t addr, bool wide64 = false) {
        tlp_header h;
        h.fmt = wide64 ? Fmt::T4DW_NO_DATA : Fmt::T3DW_NO_DATA;
        h.type = Type::MRd;
        h.requester_id = req_id;
        h.tag = tag;
        h.address = addr & ~0x3ULL;
        h.length = 1;
        return h;
    }

    static tlp_header mmio_write(uint16_t req_id, uint16_t tag,
                                 uint64_t addr, uint16_t dw_len,
                                 bool wide64 = false) {
        auto h = mmio_read(req_id, tag, addr, wide64);
        h.type = Type::MWr;
        h.fmt = wide64 ? Fmt::T4DW_WITH_DATA : Fmt::T3DW_WITH_DATA;
        h.length = (dw_len == 0) ? 0 : dw_len;  // 0 = 128B 语义
        return h;
    }

    static tlp_header completion(uint16_t cpl_id, uint16_t tag,
                                 uint16_t req_id, CplStatus st,
                                 uint16_t byte_count, bool with_data,
                                 uint16_t data_dw = 1) {
        tlp_header h;
        h.fmt = with_data ? Fmt::T3DW_WITH_DATA : Fmt::T3DW_NO_DATA;
        h.type = Type::CplD;  // Cpl 与 CplD 编码相同, 靠 Fmt 区分
        h.completer_id = cpl_id;
        h.tag = tag;
        h.cpl_requester_id = req_id;
        h.status = st;
        h.byte_count = byte_count;
        // 注意: length=0 表示 128B(512B), 必须显式设置——否则 to_bytes 会
        // 按 payload_bytes() 越界读取实际更短的 payload
        h.length = with_data ? data_dw : 0;
        return h;
    }

    static tlp_header message(uint16_t req_id, uint8_t code,
                              MsgRoute route = MsgRoute::TO_ROOT) {
        tlp_header h;
        h.fmt = Fmt::T3DW_NO_DATA;
        h.type = Type::Msg;
        h.requester_id = req_id;
        h.msg_code = code;
        h.msg_route = route;
        return h;
    }

    // ── 头字节布局（3DW=12B / 4DW=16B，供校验与字节流调试）──
    size_t header_bytes() const {
        return (fmt == Fmt::T4DW_NO_DATA || fmt == Fmt::T4DW_WITH_DATA) ? 16 : 12;
    }
    void serialize(uint8_t* out) const;   // 实现于 tlp_parser.cpp

    bool has_data() const {
        return (fmt == Fmt::T3DW_WITH_DATA || fmt == Fmt::T4DW_WITH_DATA);
    }
    uint16_t payload_bytes() const {
        uint16_t dw = (length == 0) ? 128 : length;  // 0 表示 128B
        return dw * 4;
    }

    // 逻辑类型判定
    // 注意: MRd/MWr、CfgRd0/CfgWr0 在规范中 Type 编码相同，读/写必须靠
    // Fmt（是否带数据）区分——不能只比较 type！
    bool is_cfg() const { return type == Type::CfgRd0 || type == Type::CfgRd1; }
    bool is_mem() const { return type == Type::MRd; }
    bool is_cpl() const { return type == Type::Cpl || type == Type::CplLk; }
    bool is_msg() const { return type == Type::Msg; }
    bool is_write() const { return (is_mem() || is_cfg()) && has_data(); }
    bool is_read() const { return (is_mem() || is_cfg()) && !has_data(); }
};

// ── 完整 TLP 事务（header + payload + ECRC 预留）──
struct tlp_transaction {
    tlp_header header;
    std::vector<uint8_t> payload;  // 长度 = header.payload_bytes()
    uint32_t ecrc = 0;             // TD=1 时有效（生成/校验默认交 VIP，见设计假设 #7）

    tlp_transaction() = default;
    explicit tlp_transaction(const tlp_header& h, std::vector<uint8_t> data = {})
        : header(h), payload(std::move(data)) {}

    // 将 TLP 序列化为连续字节流 (header + payload + ecrc)
    std::vector<uint8_t> to_bytes() const;
    // 从字节流解析（返回 false 表示长度不匹配）
    static bool from_bytes(const uint8_t* buf, size_t n, tlp_transaction& out);
};

}  // namespace pcie
