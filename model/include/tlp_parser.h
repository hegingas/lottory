// tlp_parser.h — TLP 解析器（interfaces.md §6.4）
// 纯逻辑层：接收上行 TLP，提取头字段并分流（Cpl → 挂起表 / DMA → 内存 / Msg → 路由）。
#pragma once
#include "pcie_types.h"
#include "tlp_ext.h"

namespace pcie {

struct parse_result {
    bool ok = false;
    std::string error;
    TxnClass txn_class = TxnClass::UNKNOWN;   // 分流结果
    tlp_transaction tlp;
    // Cpl 时：关联的请求 tag
    uint16_t cpl_tag = 0;
    // DMA 时：目标地址（host 物理地址，未过 SMMU）
    uint64_t dma_addr = 0;
    uint16_t dma_len_bytes = 0;
    // Msg 时
    uint8_t msg_code = 0;
};

class tlp_parser {
public:
    // 解析 TLP → 分流（不执行任何副作用，仅分类+提取）
    parse_result parse(const tlp_transaction& tlp) const;
};

}  // namespace pcie
