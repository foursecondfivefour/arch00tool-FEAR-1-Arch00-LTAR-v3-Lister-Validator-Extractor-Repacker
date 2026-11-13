#pragma once
#include <cstdint>
#include <atomic>
#include <mutex>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

namespace arch00 {
struct Error : std::runtime_error { using std::runtime_error::runtime_error; };
struct Cancelled : Error { Cancelled() : Error("operation cancelled") {} };
// Optional cooperative control, owned by the caller for the operation lifetime.
struct Control {
    std::atomic<bool> cancelled{false};
    std::atomic<std::size_t> completed{0}, total{0};
    mutable std::mutex mutex;
    std::string phase = "Preparing";
    bool publishing = false;
    void check() const { if (cancelled.load()) throw Cancelled(); }
    void start_phase(const std::string& name, std::size_t count) {
        std::lock_guard<std::mutex> lock(mutex); phase=name; completed=0; total=count;
    }
    bool request_cancel() {
        std::lock_guard<std::mutex> lock(mutex);
        if (publishing) return false;
        cancelled.store(true); return true;
    }
};
struct Header {
    std::uint32_t version, names_size, folder_count, file_count, retail, download, crc_enabled;
    std::vector<unsigned char> guid;
};
struct Entry {
    std::string name;
    std::uint64_t offset, stored_size, unpacked_size;
    std::uint32_t compression;
};
struct Archive { Header header; std::vector<Entry> entries; std::vector<std::string> folders; };
Archive parse(const std::filesystem::path& path);
}

namespace arch00 {
// Validates stored payloads; raw_mode copies stored bytes without decompression.
void test(const std::filesystem::path& path, const Archive& archive, bool raw_mode = false, bool verbose = false, unsigned jobs = 1, Control* control = nullptr);
// Extracts all entries; files are created exclusively and are not rolled back on error.
void extract(const std::filesystem::path& path, const Archive& archive,
             const std::filesystem::path& output, bool raw_mode = false, bool verbose = false, unsigned jobs = 1, Control* control = nullptr);
}

namespace arch00 {
struct RepackResult { std::size_t files, replaced; std::uint64_t payload_bytes; };
RepackResult repack(const std::filesystem::path& source, const std::filesystem::path& output,
                    const std::filesystem::path& replacements = {}, unsigned jobs = 1, Control* control = nullptr);
}
