// tlp_builder.h — TLP 构造器（interfaces.md §6.1/6.2）
// 纯逻辑层：从高层请求构造 TLP 事务；字段校验 + 默认值填充。
#pragma once
#include <optional>
#include "pcie_types.h"
#include "tlp_ext.h"

namespace pcie {

struct builder_result {
    bool ok = false;
    std::string error;
    tlp_transaction tlp;
};

// 高层请求（模型内部统一表达）
struct req_desc {
    TxnClass txn_class = TxnClass::UNKNOWN;
    uint64_t address = 0;        // Mem 请求: 总线地址；Cfg 请求: 忽略
    uint16_t length_bytes = 0;   // 数据长度（字节）
    uint8_t  be_first = 0xFF;
    uint8_t  be_last = 0xFF;
    // Cfg 专用
    uint8_t  bus = 0, dev = 0, fn = 0;
    uint16_t reg_off = 0;
    bool     cfg_type1 = false;
    // 归属
    uint16_t requester_id = 0;   // 默认 0:0:0（rc_bus_ctrl 覆盖）
    uint16_t tag = 0;            // 由引擎分配，调用方可不填
    uint8_t  tc = 0;
    // 数据（写请求）
    std::vector<uint8_t> data;
};

class tlp_builder {
public:
    // 按 txn_class 构造 TLP；tag 由调用方通过 desc.tag 提供
    builder_result build(const req_desc& desc) const;
};

// 校验辅助：MMIO 长度必须是 4B 倍数（PCIe DW 对齐）
bool is_dw_aligned(uint16_t length_bytes);

}  // namespace pcie
