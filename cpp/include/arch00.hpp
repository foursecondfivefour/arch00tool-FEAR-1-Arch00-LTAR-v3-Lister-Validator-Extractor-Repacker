#pragma once
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

namespace arch00 {
struct Error : std::runtime_error { using std::runtime_error::runtime_error; };
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
void test(const std::filesystem::path& path, const Archive& archive, bool raw_mode = false, bool verbose = false, unsigned jobs = 1);
// Extracts all entries; files are created exclusively and are not rolled back on error.
void extract(const std::filesystem::path& path, const Archive& archive,
             const std::filesystem::path& output, bool raw_mode = false, bool verbose = false, unsigned jobs = 1);
}

namespace arch00 {
struct RepackResult { std::size_t files, replaced; std::uint64_t payload_bytes; };
RepackResult repack(const std::filesystem::path& source, const std::filesystem::path& output,
                    const std::filesystem::path& replacements = {});
}
