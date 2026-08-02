// tlp_builder.cpp — TLP 构造器实现
#include "tlp_builder.h"

namespace pcie {

bool is_dw_aligned(uint16_t length_bytes) {
    return length_bytes % 4 == 0;
}

builder_result tlp_builder::build(const req_desc& desc) const {
    builder_result r;
    tlp_header h;

    switch (desc.txn_class) {
        case TxnClass::CFG_READ: {
            h = tlp_header::cfg_read(desc.requester_id, desc.tag,
                                     desc.bus, desc.dev, desc.fn,
                                     desc.reg_off, desc.cfg_type1);
            break;
        }
        case TxnClass::CFG_WRITE: {
            h = tlp_header::cfg_write(desc.requester_id, desc.tag,
                                      desc.bus, desc.dev, desc.fn,
                                      desc.reg_off, desc.cfg_type1);
            if (desc.data.size() < 4) {
                r.error = "CFG_WRITE 需要 4B 数据";
                return r;
            }
            break;
        }
        case TxnClass::MMIO_READ: {
            h = tlp_header::mmio_read(desc.requester_id, desc.tag, desc.address,
                                      (desc.address >> 32) != 0);
            break;
        }
        case TxnClass::MMIO_WRITE: {
            if (!is_dw_aligned(static_cast<uint16_t>(desc.data.size())) ||
                desc.data.empty()) {
                r.error = "MMIO_WRITE 数据长度必须是 4B 倍数";
                return r;
            }
            h = tlp_header::mmio_write(desc.requester_id, desc.tag, desc.address,
                                       static_cast<uint16_t>(desc.data.size() / 4),
                                       (desc.address >> 32) != 0);
            break;
        }
        default:
            r.error = std::string("tlp_builder 不支持事务类: ") +
                      to_string(desc.txn_class);
            return r;
    }

    h.tc = desc.tc;
    h.be_first = desc.be_first;
    h.be_last = desc.be_last;

    tlp_transaction tlp(h);
    if (h.has_data()) {
        tlp.payload = desc.data;
    }
    r.ok = true;
    r.tlp = std::move(tlp);
    return r;
}

}  // namespace pcie
