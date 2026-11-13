#include "arch00.hpp"
#include <algorithm>
#include <array>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <numeric>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#include <sys/stat.h>
#else
#include <fcntl.h>
#include <unistd.h>
#endif
namespace arch00 {
namespace {
namespace fs = std::filesystem;
using Bytes = std::vector<unsigned char>;
constexpr std::size_t chunk = 256 * 1024;
using File = std::unique_ptr<std::FILE, int(*)(std::FILE*)>;
std::uint64_t get64(const unsigned char* p) { std::uint64_t n=0; for (int i=7;i>=0;--i) n=(n<<8)|p[i]; return n; }
void put64(unsigned char* p, std::uint64_t n) { for(int i=0;i<8;++i) { p[i]=static_cast<unsigned char>(n); n>>=8; } }
void put32(unsigned char* p, std::uint32_t n) { for(int i=0;i<4;++i) { p[i]=static_cast<unsigned char>(n); n>>=8; } }
void read_exact(std::ifstream& file, unsigned char* dest, std::size_t size) {
    if (size && !file.read(reinterpret_cast<char*>(dest),static_cast<std::streamsize>(size))) throw Error("truncated input while repacking");
}
void seek(std::ifstream& file, std::uint64_t offset) {
    if (offset>static_cast<std::uint64_t>(std::numeric_limits<std::streamoff>::max())) throw Error("offset too large");
    file.clear(); file.seekg(static_cast<std::streamoff>(offset)); if (!file) throw Error("seek failed");
}
void write(std::FILE* file, const unsigned char* data, std::size_t size) {
    if (size && std::fwrite(data,1,size,file)!=size) throw Error("failed writing temporary archive");
}
File exclusive_file(const fs::path& path) {
#ifdef _WIN32
    int fd=_wopen(path.c_str(),_O_WRONLY|_O_CREAT|_O_EXCL|_O_BINARY,_S_IREAD|_S_IWRITE);
    if (fd<0) throw Error("cannot create temporary archive exclusively");
    auto* f=_fdopen(fd,"wb"); if (!f) { _close(fd); throw Error("cannot open temporary stream"); }
#else
    int fd=::open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0666);
    if (fd<0) throw Error("cannot create temporary archive exclusively");
    auto* f=fdopen(fd,"wb"); if (!f) { ::close(fd); throw Error("cannot open temporary stream"); }
#endif
    return File(f,&std::fclose);
}
fs::path replacement_path(const fs::path& root, std::string name) {
    std::replace(name.begin(),name.end(),'\\','/');
    if (name.empty() || name.front()=='/') throw Error("unsafe archive path: " + name);
    fs::path result=root; bool any=false; std::size_t begin=0;
    while(begin<=name.size()) {
        auto end=name.find('/',begin); auto part=name.substr(begin,end==std::string::npos ? end : end-begin);
        if(part==".." || part.find(':')!=std::string::npos) throw Error("unsafe archive path: " + name);
        if(!part.empty() && part!=".") { result/=fs::u8path(part); any=true; }
        if(end==std::string::npos) break; begin=end+1;
    }
    if(!any) throw Error("unsafe archive path: " + name); return result;
}
void copy_range(std::ifstream& src, std::FILE* dst, std::uint64_t offset, std::uint64_t size) {
    seek(src,offset); std::array<unsigned char,chunk> buffer{};
    while(size) { auto n=static_cast<std::size_t>(std::min<std::uint64_t>(size,buffer.size())); read_exact(src,buffer.data(),n); write(dst,buffer.data(),n); size-=n; }
}
void compare_range(std::ifstream& a, std::uint64_t offset_a, std::ifstream& b, std::uint64_t offset_b, std::uint64_t size) {
    seek(a,offset_a); seek(b,offset_b); std::array<unsigned char,chunk> x{},y{};
    while(size) { auto n=static_cast<std::size_t>(std::min<std::uint64_t>(size,chunk)); read_exact(a,x.data(),n); read_exact(b,y.data(),n); if(!std::equal(x.begin(),x.begin()+n,y.begin())) throw Error("payload verification failed"); size-=n; }
}
struct Item { std::uint64_t old_offset, old_size, size, new_offset; fs::path replacement; };
}
RepackResult repack(const fs::path& source, const fs::path& output, const fs::path& replacements) {
    if (fs::weakly_canonical(source)==fs::weakly_canonical(output)) throw Error("output path must differ from source archive");
    if (fs::exists(output) || fs::is_symlink(output)) throw Error("output already exists");
    auto parsed=parse(source); auto& h=parsed.header;
    std::uint64_t metadata_size=48ULL+h.names_size+std::uint64_t(h.file_count)*32+std::uint64_t(h.folder_count)*16;
    std::ifstream src(source,std::ios::binary); if(!src) throw Error("cannot open source archive");
    Bytes metadata(static_cast<std::size_t>(metadata_size)); read_exact(src,metadata.data(),metadata.size());
    auto original_metadata=metadata; std::vector<Item> items; items.reserve(parsed.entries.size()); std::size_t replaced=0;
    for (std::size_t i=0;i<parsed.entries.size();++i) {
        const auto& e=parsed.entries[i]; if(e.offset<metadata_size) throw Error("file record points into metadata");
        Item item{e.offset,e.stored_size,e.stored_size,0,{}};
        if(!replacements.empty()) {
            auto candidate=replacement_path(replacements,e.name);
            if(fs::is_regular_file(candidate)) { item.replacement=candidate; item.size=fs::file_size(candidate); ++replaced; }
        }
        items.push_back(std::move(item));
    }
    std::vector<std::size_t> order(items.size()); std::iota(order.begin(),order.end(),0);
    std::sort(order.begin(),order.end(),[&](auto a,auto b){ return items[a].old_offset!=items[b].old_offset ? items[a].old_offset<items[b].old_offset : a<b; });
    std::uint64_t next=metadata_size, payload_bytes=0;
    for(auto index:order) {
        auto& item=items[index]; if(item.size>std::numeric_limits<std::uint64_t>::max()-next) throw Error("archive size overflow");
        item.new_offset=next; next+=item.size; payload_bytes+=item.size;
        auto* record=metadata.data()+48+h.names_size+index*32; put64(record+4,item.new_offset);
        if(!item.replacement.empty()) { put64(record+12,item.size); put64(record+20,item.size); put32(record+28,0); }
    }
    if(!output.parent_path().empty()) fs::create_directories(output.parent_path());
    auto temp=output; temp += ".partial";
    bool owns_temp=false;
    try {
        auto out=exclusive_file(temp); owns_temp=true;
        write(out.get(),metadata.data(),metadata.size());
        for(auto index:order) {
            auto& item=items[index];
            if(item.replacement.empty()) copy_range(src,out.get(),item.old_offset,item.old_size);
            else { std::ifstream replacement(item.replacement,std::ios::binary); if(!replacement) throw Error("cannot open replacement"); copy_range(replacement,out.get(),0,item.size); }
        }
        if(std::fflush(out.get())!=0) throw Error("failed flushing temporary archive");
#ifdef _WIN32
        if(_commit(_fileno(out.get()))!=0) throw Error("failed syncing temporary archive");
#else
        if(::fsync(fileno(out.get()))!=0) throw Error("failed syncing temporary archive");
#endif
        if(std::fclose(out.release())!=0) throw Error("failed closing temporary archive");
        auto rebuilt=parse(temp);
        if(rebuilt.entries.size()!=items.size() || fs::file_size(temp)!=next) throw Error("rebuilt archive size or entry count mismatch");
        std::ifstream verify(temp,std::ios::binary); if(!verify) throw Error("cannot reopen temporary archive");
        Bytes actual(metadata.size()); read_exact(verify,actual.data(),actual.size()); if(actual!=metadata) throw Error("rebuilt metadata mismatch");
        // Re-read the original metadata as well, detecting changes during the build.
        seek(src,0); Bytes source_now(original_metadata.size()); read_exact(src,source_now.data(),source_now.size());
        if(source_now!=original_metadata) throw Error("source metadata changed during repack");
        for(const auto& item:items) {
            if(item.replacement.empty()) compare_range(src,item.old_offset,verify,item.new_offset,item.size);
            else { if(fs::file_size(item.replacement)!=item.size) throw Error("replacement size changed during repack"); std::ifstream replacement(item.replacement,std::ios::binary); if(!replacement) throw Error("cannot reopen replacement"); compare_range(replacement,0,verify,item.new_offset,item.size); }
        }
        // An atomic hard-link creation fails if the destination already exists.
        fs::create_hard_link(temp,output);
        std::error_code cleanup_error; fs::remove(temp,cleanup_error); owns_temp=false;
        return {items.size(),replaced,payload_bytes};
    } catch (...) { if(owns_temp) { std::error_code ec; fs::remove(temp,ec); } throw; }
}
}
