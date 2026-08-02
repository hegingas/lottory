// pending_table.cpp — 挂起请求表实现
#include "pending_table.h"

namespace pcie {

int pending_table::find_free_tag() {
    // 环形扫描；表满（pending_ >= MAX_TAGS）由 is_full 判断，这里不处理
    for (int i = 0; i < MAX_TAGS; i++) {
        int idx = (next_tag_ + i) % MAX_TAGS;
        if (!entries_[idx].active) {
            next_tag_ = (idx + 1) % MAX_TAGS;  // 下次从下一格开始
            return idx;
        }
    }
    return -1;
}

int pending_table::alloc_tag() {
    int idx = find_free_tag();
    return idx;  // -1 = 表满
}

bool pending_table::register_at(int tag, const tlp_header& req, TxnClass cls,
                                std::vector<uint8_t> data,
                                std::function<void(CplStatus, const std::vector<uint8_t>&)> cb,
                                int64_t now_ns) {
    if (tag < 0 || tag >= MAX_TAGS || entries_[tag].active) return false;

    pending_entry& e = entries_[tag];
    e.tag = static_cast<uint16_t>(tag);
    e.txn_class = cls;
    e.request = req;
    e.data = std::move(data);
    e.on_complete = std::move(cb);
    e.issued_ns = now_ns;
    e.active = true;
    pending_++;
    return true;
}

void pending_table::release_tag(int tag) {
    if (tag < 0 || tag >= MAX_TAGS) return;
    if (entries_[tag].active) pending_--;
    entries_[tag].active = false;
    entries_[tag].on_complete = nullptr;
}

bool pending_table::issue(const tlp_header& req, TxnClass cls,
                          std::vector<uint8_t> data,
                          std::function<void(CplStatus, const std::vector<uint8_t>&)> cb,
                          int64_t now_ns) {
    int idx = alloc_tag();
    if (idx < 0) return false;  // 表满
    return register_at(idx, req, cls, std::move(data), std::move(cb), now_ns);
}

bool pending_table::complete(uint16_t tag, CplStatus st,
                             const std::vector<uint8_t>& cpl_data) {
    if (tag >= MAX_TAGS) return false;
    pending_entry& e = entries_[tag];
    if (!e.active) return false;  // 未命中

    if (e.on_complete) {
        e.on_complete(st, cpl_data);
    }
    e.active = false;
    pending_--;
    return true;
}

std::vector<uint16_t> pending_table::check_timeout(int64_t now_ns, int64_t timeout_ns) const {
    std::vector<uint16_t> expired;
    for (const auto& e : entries_) {
        if (e.active && (now_ns - e.issued_ns) > timeout_ns) {
            expired.push_back(e.tag);
        }
    }
    return expired;
}

bool pending_table::remove(uint16_t tag) {
    if (tag >= MAX_TAGS) return false;
    if (!entries_[tag].active) return false;
    entries_[tag].active = false;
    pending_--;
    return true;
}

}  // namespace pcie
