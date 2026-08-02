// tlp_ext.cpp — TLP 头序列化与事务字节流编解码
// 字节布局按 PCIe Base Spec 6.0（非 Flit 模式）。
#include "tlp_ext.h"
#include <cstring>

namespace pcie {

// ── header 序列化（3DW=12B / 4DW=16B）──
void tlp_header::serialize(uint8_t* out) const {
    std::memset(out, 0, header_bytes());  // 只清实际头长，避免 3DW 越界
    const bool wd = has_data();
    const bool w4 = (header_bytes() == 16);

    // Byte0: Fmt[7:6] Type[5:0]
    uint8_t fmt_bits = static_cast<uint8_t>(fmt);
    uint8_t type_bits = static_cast<uint8_t>(type);
    // 消息路由位并入 Type 低 3 位（Type 编码 = 1_0rrr，r 位即 route）
    if (type == Type::Msg) {
        type_bits = 0b10000 | static_cast<uint8_t>(msg_route);
    }
    out[0] = (fmt_bits << 6) | (type_bits & 0x3F);
    // Byte1: TC[6:4] TH[0]
    out[1] = (tc << 4) | (th ? 0x01 : 0x00);
    // Byte2: TD[7] EP[6] Attr[5:4] AT[3:2] Length[9:8]
    out[2] = (td ? 0x80 : 0) | (ep ? 0x40 : 0) |
             ((attr & 0x3) << 4) | ((at & 0x3) << 2) |
             ((length >> 8) & 0x3);
    // Byte3: Length[7:0]
    out[3] = length & 0xFF;

    // Byte4-5: Requester ID 或 Completer ID（Cpl 用）
    uint16_t id = is_cpl() ? completer_id : requester_id;
    out[4] = (id >> 8) & 0xFF;
    out[5] = id & 0xFF;
    // Byte6: Tag
    out[6] = tag & 0xFF;

    if (is_cfg()) {
        // Cfg: Byte7 保留；Byte8-9 地址(忽略)；Byte10-11: bus/dev/fn + reg
        out[10] = ((target_bus & 0xFF) << 0) & 0xFF;
        out[11] = ((target_dev & 0x1F) << 3) | (target_fn & 0x07);
        // reg_off 低 12 bit 映射到 ExtReg[3:0]+Reg[7:2]
        out[8] = ((reg_off >> 8) & 0x0F) << 4;  // Ext Register
        out[9] = (reg_off & 0xFF) & 0xFC;       // Register Number
    } else if (is_mem()) {
        // Byte7: LastDW BE[7:4] FirstDW BE[3:0]（3DW 头）；4DW 头 Byte7=地址[39:32]
        if (w4) {
            out[7] = (address >> 32) & 0xFF;
        } else {
            out[7] = ((be_last & 0xF) << 4) | (be_first & 0xF);
        }
        // 3DW: Byte8-11 = addr[31:0]；4DW: Byte8-11 = addr[63:32], Byte12-15 = addr[31:0]
        if (w4) {
            out[8] = (address >> 56) & 0xFF;
            out[9] = (address >> 48) & 0xFF;
            out[10] = (address >> 40) & 0xFF;
            out[11] = (address >> 32) & 0xFF;
            out[12] = (address >> 24) & 0xFF;
            out[13] = (address >> 16) & 0xFF;
            out[14] = (address >> 8) & 0xFF;
            out[15] = address & 0xFF;
        } else {
            out[8] = (address >> 24) & 0xFF;
            out[9] = (address >> 16) & 0xFF;
            out[10] = (address >> 8) & 0xFF;
            out[11] = address & 0xFF;
        }
    } else if (is_cpl()) {
        // Cpl: Byte8-9 = Requester ID
        out[8] = (cpl_requester_id >> 8) & 0xFF;
        out[9] = cpl_requester_id & 0xFF;
        // Byte10-11: ByteCount[11:0] + BCM[12] + Status[15:13]
        uint16_t bc_field = static_cast<uint16_t>(byte_count & 0xFFF) |
                            (bcm ? 0x1000 : 0) |
                            (static_cast<uint16_t>(status) << 13);
        out[10] = (bc_field >> 8) & 0xFF;
        out[11] = bc_field & 0xFF;
    } else if (is_msg()) {
        // Msg: Byte7 = Msg Code
        out[7] = msg_code;
        // Byte8-11: 地址路由时为目标地址，TO_ROOT 时保留 0
    }
    // 其他类型（IO/原子）POC 不生成，序列化保持 0
    (void)wd;
}

// ── 事务字节流编解码 ──
std::vector<uint8_t> tlp_transaction::to_bytes() const {
    size_t hb = header.header_bytes();
    size_t pb = header.has_data() ? header.payload_bytes() : 0;
    std::vector<uint8_t> buf(hb + pb + (header.td ? 4 : 0));
    header.serialize(buf.data());
    if (pb) std::memcpy(buf.data() + hb, payload.data(), pb);
    if (header.td) {
        uint32_t crc = ecrc;
        std::memcpy(buf.data() + hb + pb, &crc, 4);
    }
    return buf;
}

bool tlp_transaction::from_bytes(const uint8_t* buf, size_t n, tlp_transaction& out) {
    if (n < 12) return false;
    const uint8_t* h = buf;
    tlp_header& H = out.header;

    H.fmt = static_cast<Fmt>((h[0] >> 6) & 0x3);
    uint8_t type_bits = h[0] & 0x3F;
    H.tc = (h[1] >> 4) & 0x7;
    H.th = (h[1] & 0x01) != 0;
    H.td = (h[2] & 0x80) != 0;
    H.ep = (h[2] & 0x40) != 0;
    H.attr = (h[2] >> 4) & 0x3;
    H.at = (h[2] >> 2) & 0x3;
    H.length = ((h[2] & 0x3) << 8) | h[3];

    const bool w4 = (H.header_bytes() == 16);
    if (n < H.header_bytes()) return false;

    H.requester_id = (h[4] << 8) | h[5];
    H.tag = h[6];

    // 按类型还原字段
    if (type_bits == static_cast<uint8_t>(Type::Msg) ||
        (type_bits & 0xF8) == 0x80) {  // Msg: 1_0rrr
        H.type = Type::Msg;
        H.msg_route = static_cast<MsgRoute>(type_bits & 0x7);
        H.msg_code = h[7];
    } else if (type_bits == static_cast<uint8_t>(Type::Cpl) ||
               type_bits == static_cast<uint8_t>(Type::CplD)) {
        H.type = H.has_data() ? Type::CplD : Type::Cpl;
        H.cpl_requester_id = (h[8] << 8) | h[9];
        uint16_t bc_field = (h[10] << 8) | h[11];
        H.byte_count = bc_field & 0xFFF;
        H.bcm = (bc_field & 0x1000) != 0;
        H.status = static_cast<CplStatus>((bc_field >> 13) & 0x7);
    } else if ((type_bits & 0x3E) == 0x04) {  // CfgRd/Wr0/1
        H.type = ((type_bits & 0x01) == 0) ?
                 (H.is_write() ? Type::CfgWr0 : Type::CfgRd0) :
                 (H.is_write() ? Type::CfgWr1 : Type::CfgRd1);
        H.reg_off = ((h[8] >> 4) & 0xF) << 8 | (h[9] & 0xFC);
        H.target_bus = h[10];
        H.target_dev = (h[11] >> 3) & 0x1F;
        H.target_fn = h[11] & 0x07;
    } else if ((type_bits & 0x3E) == 0x00) {  // Mem
        H.type = H.is_write() ? Type::MWr : Type::MRd;
        if (w4) {
            H.address = (static_cast<uint64_t>(h[8]) << 56) |
                        (static_cast<uint64_t>(h[9]) << 48) |
                        (static_cast<uint64_t>(h[10]) << 40) |
                        (static_cast<uint64_t>(h[11]) << 32) |
                        (static_cast<uint64_t>(h[12]) << 24) |
                        (static_cast<uint64_t>(h[13]) << 16) |
                        (static_cast<uint64_t>(h[14]) << 8) |
                        h[15];
        } else {
            H.address = (static_cast<uint64_t>(h[8]) << 24) |
                        (static_cast<uint64_t>(h[9]) << 16) |
                        (static_cast<uint64_t>(h[10]) << 8) |
                        h[11];
            H.be_last = (h[7] >> 4) & 0xF;
            H.be_first = h[7] & 0xF;
        }
    } else {
        return false;  // POC 不支持的类型
    }

    // payload
    out.payload.clear();
    if (H.has_data()) {
        size_t pb = H.payload_bytes();
        if (n < H.header_bytes() + pb + (H.td ? 4 : 0)) return false;
        out.payload.assign(buf + H.header_bytes(), buf + H.header_bytes() + pb);
    }
    if (H.td) {
        std::memcpy(&out.ecrc, buf + n - 4, 4);
    }
    return true;
}

}  // namespace pcie
