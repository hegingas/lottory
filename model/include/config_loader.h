// config_loader.h — 极简 KV 配置加载（无外部依赖，防 SystemC 环境未就绪阻塞）
// 格式: "key=value"，# 注释；POC 覆盖 delays/bars 等数值配置。
// SystemC 环境就绪后可替换为 JSON (nlohmann) 实现，接口不变。
//
// 注意: 不用 std::ifstream —— MinGW GCC 16.1.0 在 Windows 上 O1+ 优化下
// ifstream 构造/使用会段错误（工具链 bug），改用 C 风格 FILE* 规避。
#pragma once
#include <cstdint>
#include <cstdio>
#include <string>
#include <unordered_map>

namespace pcie {

class config_loader {
public:
    bool load(const std::string& path) {
        FILE* f = std::fopen(path.c_str(), "r");
        if (!f) return false;
        char buf[1024];
        while (std::fgets(buf, sizeof(buf), f)) {
            std::string line(buf);
            // 去注释与空白
            auto hash = line.find('#');
            if (hash != std::string::npos) line = line.substr(0, hash);
            auto eq = line.find('=');
            if (eq == std::string::npos) continue;
            std::string k = trim(line.substr(0, eq));
            std::string v = trim(line.substr(eq + 1));
            if (!k.empty()) kv_[k] = v;
        }
        std::fclose(f);
        return true;
    }

    bool get_u64(const std::string& key, uint64_t& out) const {
        auto it = kv_.find(key);
        if (it == kv_.end()) return false;
        out = std::stoull(it->second);
        return true;
    }
    bool get_i64(const std::string& key, int64_t& out) const {
        auto it = kv_.find(key);
        if (it == kv_.end()) return false;
        out = std::stoll(it->second);
        return true;
    }
    bool get_str(const std::string& key, std::string& out) const {
        auto it = kv_.find(key);
        if (it == kv_.end()) return false;
        out = it->second;
        return true;
    }

private:
    static std::string trim(const std::string& s) {
        size_t b = s.find_first_not_of(" \t\r\n");
        if (b == std::string::npos) return "";
        size_t e = s.find_last_not_of(" \t\r\n");
        return s.substr(b, e - b + 1);
    }

    std::unordered_map<std::string, std::string> kv_;
};

}  // namespace pcie
