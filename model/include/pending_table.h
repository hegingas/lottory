// pending_table.h — 挂起请求表（split-transaction 语义，interfaces.md §6.5）
// 纯逻辑层：tag 分配/复用、请求登记、Cpl 匹配、超时判定。
#pragma once
#include <cstdint>
#include <functional>
#include <unordered_map>
#include <vector>
#include <chrono>
#include "pcie_types.h"
#include "tlp_ext.h"

namespace pcie {

struct pending_entry {
    uint16_t tag = 0;
    TxnClass txn_class = TxnClass::UNKNOWN;   // 期望的完成类型
    tlp_header request;                        // 原请求（复用以回填）
    std::vector<uint8_t> data;                 // 读请求的目标缓冲
    // 完成回调: (status, data) -> void
    std::function<void(CplStatus, const std::vector<uint8_t>&)> on_complete;
    // 时间戳（仿真时间，ns；由外部时钟驱动）
    int64_t issued_ns = 0;
    bool active = false;
};

// 挂起请求表：环形 tag 复用，128 深度
class pending_table {
public:
    static constexpr int MAX_TAGS = 128;

    pending_table() : entries_(MAX_TAGS) {}

    // 登记请求，分配 tag（返回 false = 表满，需等待）
    bool issue(const tlp_header& req, TxnClass cls,
               std::vector<uint8_t> data,
               std::function<void(CplStatus, const std::vector<uint8_t>&)> cb,
               int64_t now_ns);

    // ── tag 预分配接口（tlp_engine 需要先拿 tag 填 TLP 头再登记）──
    // 分配 tag（-1 = 表满）
    int alloc_tag();
    // 在指定 tag 上登记（供 alloc_tag 后使用）；返回 false = tag 非法/占用
    bool register_at(int tag, const tlp_header& req, TxnClass cls,
                     std::vector<uint8_t> data,
                     std::function<void(CplStatus, const std::vector<uint8_t>&)> cb,
                     int64_t now_ns);
    // 释放 tag（构造失败/请求废弃时）
    void release_tag(int tag);

    // 按 tag 匹配完成（返回 false = 未命中，协议违例）
    bool complete(uint16_t tag, CplStatus st, const std::vector<uint8_t>& cpl_data);

    // 超时检查：返回超时的 tag 列表（由调用方上报错误后 remove）
    std::vector<uint16_t> check_timeout(int64_t now_ns, int64_t timeout_ns) const;

    // 取消（tag 无效/请求被废弃时）
    bool remove(uint16_t tag);

    size_t pending_count() const { return pending_; }
    bool   is_full() const { return pending_ >= MAX_TAGS; }

private:
    std::vector<pending_entry> entries_;
    int  next_tag_ = 0;   // 环形分配游标
    int  pending_ = 0;

    int find_free_tag();
};

}  // namespace pcie
