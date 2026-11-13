#include "arch00.hpp"
#include <algorithm>
#include <array>
#include <fstream>
#include <limits>

namespace arch00 {
namespace {
using Bytes = std::vector<unsigned char>;
constexpr std::uint64_t header_size = 48, max_names = 512ULL * 1024 * 1024, max_entries = 2000000;
void read_exact(std::istream& in, unsigned char* out, std::size_t n, const char* what) {
    if (n && (!in.read(reinterpret_cast<char*>(out), static_cast<std::streamsize>(n))))
        throw Error(std::string("truncated ") + what);
}
std::uint32_t u32(const unsigned char* p) {
    return std::uint32_t(p[0]) | (std::uint32_t(p[1]) << 8) | (std::uint32_t(p[2]) << 16) | (std::uint32_t(p[3]) << 24);
}
std::uint64_t u64(const unsigned char* p) { return std::uint64_t(u32(p)) | (std::uint64_t(u32(p + 4)) << 32); }
bool valid_utf8(const std::string& s) {
    for (std::size_t i = 0; i < s.size();) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        if (c < 0x80) { ++i; continue; }
        int n; std::uint32_t cp;
        if (c >= 0xc2 && c <= 0xdf) { n=2; cp=c & 31; }
        else if (c >= 0xe0 && c <= 0xef) { n=3; cp=c & 15; }
        else if (c >= 0xf0 && c <= 0xf4) { n=4; cp=c & 7; }
        else return false;
        if (i + n > s.size()) return false;
        for (int j=1; j<n; ++j) { unsigned char t=static_cast<unsigned char>(s[i+j]); if ((t & 0xc0) != 0x80) return false; cp=(cp << 6) | (t & 63); }
        if ((n==3 && cp<0x800) || (n==4 && cp<0x10000) || (cp>=0xd800 && cp<=0xdfff) || cp>0x10ffff) return false;
        i += n;
    }
    return true;
}
void append_utf8(std::string& s, unsigned cp) {
    if (cp < 0x80) s.push_back(static_cast<char>(cp));
    else if (cp < 0x800) { s.push_back(static_cast<char>(0xc0 | (cp >> 6))); s.push_back(static_cast<char>(0x80 | (cp & 63))); }
    else { s.push_back(static_cast<char>(0xe0 | (cp >> 12))); s.push_back(static_cast<char>(0x80 | ((cp >> 6) & 63))); s.push_back(static_cast<char>(0x80 | (cp & 63))); }
}
std::string name_at(const Bytes& names, std::uint32_t offset) {
    if (offset >= names.size()) throw Error("string offset outside name table");
    auto begin=names.begin()+offset, end=std::find(begin,names.end(),0);
    if (end==names.end()) throw Error("string is not NUL-terminated");
    std::string s(begin,end); if (valid_utf8(s)) return s;
    static constexpr unsigned map[32]={0x20ac,0xfffd,0x201a,0x192,0x201e,0x2026,0x2020,0x2021,0x2c6,0x2030,0x160,0x2039,0x152,0xfffd,0x17d,0xfffd,0xfffd,0x2018,0x2019,0x201c,0x201d,0x2022,0x2013,0x2014,0x2dc,0x2122,0x161,0x203a,0x153,0xfffd,0x17e,0x178};
    std::string out; for (unsigned char c : s) append_utf8(out, c>=0x80 && c<=0x9f ? map[c-0x80] : c); return out;
}
}
Archive parse(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    if (!in) throw Error("cannot open archive");
    auto pos=in.tellg(); if (pos<0) throw Error("cannot determine archive size");
    auto size=static_cast<std::uint64_t>(pos); in.seekg(0);
    std::array<unsigned char,48> h{}; read_exact(in,h.data(),h.size(),"header");
    if (u32(h.data()) != 0x5241544c) throw Error("invalid signature (expected LTAR)");
    Archive a; auto& hd=a.header;
    hd.version=u32(h.data()+4); hd.names_size=u32(h.data()+8); hd.folder_count=u32(h.data()+12); hd.file_count=u32(h.data()+16);
    hd.retail=u32(h.data()+20); hd.download=u32(h.data()+24); hd.crc_enabled=u32(h.data()+28); hd.guid.assign(h.begin()+32,h.end());
    if (hd.version!=3) throw Error("unsupported LTAR version");
    if (hd.names_size>max_names || hd.folder_count>max_entries || hd.file_count>max_entries) throw Error("metadata exceeds safety limit");
    auto metadata_end=header_size + hd.names_size + std::uint64_t(hd.file_count)*32 + std::uint64_t(hd.folder_count)*16;
    if (metadata_end>size) throw Error("metadata tables exceed archive size");
    Bytes names(hd.names_size); read_exact(in,names.data(),names.size(),"name table");
    a.entries.reserve(hd.file_count);
    std::array<unsigned char,32> rec{};
    for (std::uint32_t i=0;i<hd.file_count;++i) {
        read_exact(in,rec.data(),rec.size(),"file table");
        Entry e{name_at(names,u32(rec.data())),u64(rec.data()+4),u64(rec.data()+12),u64(rec.data()+20),u32(rec.data()+28)};
        if (e.offset>size || e.stored_size>size-e.offset) throw Error("file data range exceeds archive size");
        a.entries.push_back(std::move(e));
    }
    std::array<unsigned char,16> folder{}; std::size_t current=0;
    a.folders.reserve(hd.folder_count);
    for (std::uint32_t i=0;i<hd.folder_count;++i) {
        read_exact(in,folder.data(),folder.size(),"folder table");
        auto name=name_at(names,u32(folder.data())); auto count=u32(folder.data()+12);
        if (count>hd.file_count || count>a.entries.size()-current) throw Error("folder extends past file table");
        if (!name.empty()) for (std::size_t j=current;j<current+count;++j) a.entries[j].name=name+"\\"+a.entries[j].name;
        current+=count; a.folders.push_back(std::move(name));
    }
    if (current!=a.entries.size()) throw Error("folder records do not account for all files");
    return a;
}
}
