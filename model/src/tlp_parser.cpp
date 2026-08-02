// tlp_parser.cpp — TLP 解析器实现
#include "tlp_parser.h"
#include "memory_map.h"

namespace pcie {

parse_result tlp_parser::parse(const tlp_transaction& tlp) const {
    parse_result r;
    const tlp_header& h = tlp.header;
    r.tlp = tlp;

    if (h.is_cpl()) {
        r.txn_class = TxnClass::CPL;
        r.cpl_tag = static_cast<uint16_t>(h.tag);
        r.ok = true;
        return r;
    }
    if (h.is_msg()) {
        r.ok = true;
        r.msg_code = h.msg_code;
        // 消息分流：MSI 消息在 PCIe 上其实是 MemWr 地址窗口（MSI 是写事务）
        // 到达这里的纯 Msg 是 INTx / ERR / 电源管理等
        switch (h.msg_code) {
            case MSG_INTX_ASSERT:
            case MSG_INTX_DEASSERT:
                r.txn_class = TxnClass::MSG_INTX;
                break;
            case MSG_ERR_COR:
            case MSG_ERR_NONFATAL:
            case MSG_ERR_FATAL:
                r.txn_class = TxnClass::MSG_ERR;
                break;
            default:
                r.txn_class = TxnClass::MSG_INTX;  // 其他消息 POC 记日志
                break;
        }
        return r;
    }
    if (h.is_mem()) {
        // 上行 Mem 事务 = DMA（EP 发起）；读写靠 Fmt 区分（type 编码相同）
        r.txn_class = h.is_write() ? TxnClass::DMA_WRITE : TxnClass::DMA_READ;
        r.dma_addr = h.address;
        r.dma_len_bytes = h.payload_bytes();
        r.ok = true;
        return r;
    }
    if (h.is_cfg()) {
        // 上行 Cfg（EP 不该发 Cfg；RC 收到的 Cfg 是完成，走 Cpl）
        r.error = "上行 Cfg 请求非法（EP 不应发起配置请求）";
        return r;
    }

    r.error = "未知 TLP 类型";
    return r;
}

}  // namespace pcie
