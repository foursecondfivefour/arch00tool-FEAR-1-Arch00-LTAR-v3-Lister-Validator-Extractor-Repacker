#include "arch00.hpp"
#include <zlib.h>
#include <algorithm>
#include <array>
#include <cstdio>
#include <fstream>
#include <memory>
#include <limits>
#include <iostream>
#include <system_error>
#include <atomic>
#include <exception>
#include <mutex>
#include <thread>
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
constexpr std::size_t chunk_size = 256 * 1024;
using File = std::unique_ptr<std::FILE, int(*)(std::FILE*)>;
File create_exclusive(const std::filesystem::path& path) {
#ifdef _WIN32
    int fd = _wopen(path.c_str(), _O_WRONLY | _O_CREAT | _O_EXCL | _O_BINARY, _S_IREAD | _S_IWRITE);
    if (fd < 0) throw Error("cannot exclusively create output file: " + path.u8string());
    auto* f = _fdopen(fd, "wb");
    if (!f) { _close(fd); throw Error("cannot open output stream"); }
#else
    int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0666);
    if (fd < 0) throw Error("cannot exclusively create output file: " + path.u8string());
    auto* f = fdopen(fd, "wb");
    if (!f) { ::close(fd); throw Error("cannot open output stream"); }
#endif
    return File(f, &std::fclose);
}
void write_data(std::FILE* file, const unsigned char* data, std::size_t size) {
    if (file && size && std::fwrite(data, 1, size, file) != size) throw Error("failed writing output file");
}
void process(std::ifstream& in, const Entry& e, std::FILE* out, bool force_raw) {
    if (e.stored_size == 0) {
        if (e.unpacked_size != 0) throw Error(e.name + ": empty stored data with nonzero unpacked size");
        return;
    }
    if (!force_raw && e.compression > 9) throw Error(e.name + ": unrecognized compression field");
    if (e.offset > static_cast<std::uint64_t>(std::numeric_limits<std::streamoff>::max())) throw Error("file offset too large");
    in.clear(); in.seekg(static_cast<std::streamoff>(e.offset));
    if (!in) throw Error("seek failed");
    std::array<unsigned char, chunk_size> input{}, output{};
    std::uint64_t remaining=e.stored_size, total=0;
    if (force_raw || e.compression == 0) {
        while (remaining) {
            auto n=static_cast<std::size_t>(std::min<std::uint64_t>(remaining,input.size()));
            if (!in.read(reinterpret_cast<char*>(input.data()),n)) throw Error("truncated payload: " + e.name);
            write_data(out,input.data(),n); remaining-=n;
        }
        return;
    }
    z_stream stream{};
    if (inflateInit(&stream)!=Z_OK) throw Error("zlib initialization failed");
    struct Guard { z_stream* s; ~Guard(){ inflateEnd(s); } } guard{&stream};
    bool done=false;
    while (remaining && !done) {
        auto n=static_cast<std::size_t>(std::min<std::uint64_t>(remaining,input.size()));
        if (!in.read(reinterpret_cast<char*>(input.data()),n)) throw Error("truncated payload: " + e.name);
        remaining-=n; stream.next_in=input.data(); stream.avail_in=static_cast<uInt>(n);
        do {
            stream.next_out=output.data(); stream.avail_out=static_cast<uInt>(output.size());
            int result=inflate(&stream,Z_NO_FLUSH);
            auto produced=output.size()-stream.avail_out;
            if (produced > e.unpacked_size-total) throw Error(e.name + ": decompressed beyond declared size");
            total+=produced; write_data(out,output.data(),produced);
            if (result==Z_STREAM_END) { done=true; break; }
            if (result==Z_BUF_ERROR && stream.avail_in==0 && produced==0) break;
            if (result!=Z_OK) throw Error(e.name + ": invalid zlib stream");
        } while (stream.avail_in || stream.avail_out == 0);
    }
    if (!done) throw Error(e.name + ": compressed stream ended before zlib end marker");
    if (remaining || stream.avail_in) throw Error(e.name + ": trailing bytes after zlib stream");
    if (total != e.unpacked_size) throw Error(e.name + ": unpacked size mismatch");
}
std::filesystem::path destination(const std::filesystem::path& root, std::string name) {
    std::replace(name.begin(),name.end(),'\\','/');
    if (name.empty() || name.front()=='/') throw Error("unsafe archive path: " + name);
    auto result=root; std::size_t begin=0; bool any=false;
    while (begin<=name.size()) {
        auto end=name.find('/',begin); auto part=name.substr(begin,end==std::string::npos ? end : end-begin);
        if (part==".." || part.find(':')!=std::string::npos) throw Error("unsafe archive path: " + name);
        if (!part.empty() && part!=".") { result/=std::filesystem::u8path(part); any=true; }
        if (end==std::string::npos) break; begin=end+1;
    }
    if (!any) throw Error("unsafe archive path: " + name);
    return result;
}
}
void test(const std::filesystem::path& path, const Archive& archive, bool raw_mode, bool verbose, unsigned jobs) {
    if (jobs < 1 || jobs > 64) throw Error("jobs must be between 1 and 64");
    if (jobs == 1 || archive.entries.size() < 2) {
        std::ifstream in(path,std::ios::binary); if (!in) throw Error("cannot open archive");
        std::size_t count=0;
        for (const auto& entry:archive.entries) { process(in,entry,nullptr,raw_mode); ++count; if (verbose && entry.stored_size && count%1000==0) std::cerr << "validated " << count << "/" << archive.entries.size() << " entries\n"; }
        return;
    }
    const auto workers=std::min<std::size_t>(jobs,archive.entries.size());
    std::atomic<std::size_t> next{0}, completed{0};
    std::atomic<bool> stop{false};
    std::mutex mutex;
    std::exception_ptr failure;
    auto work = [&] {
        try {
            std::ifstream in(path,std::ios::binary); if (!in) throw Error("cannot open archive");
            while (!stop.load(std::memory_order_relaxed)) {
                auto index=next.fetch_add(1,std::memory_order_relaxed);
                if (index>=archive.entries.size()) break;
                process(in,archive.entries[index],nullptr,raw_mode);
                auto count=completed.fetch_add(1,std::memory_order_relaxed)+1;
                if (verbose && count%1000==0) {
                    std::lock_guard<std::mutex> lock(mutex);
                    std::cerr << "validated " << count << "/" << archive.entries.size() << " entries\n";
                }
            }
        } catch (...) {
            std::lock_guard<std::mutex> lock(mutex);
            if (!failure) failure=std::current_exception();
            stop.store(true,std::memory_order_relaxed);
        }
    };
    std::vector<std::thread> threads;
    try { for (std::size_t i=0;i<workers;++i) threads.emplace_back(work); }
    catch (...) { stop.store(true,std::memory_order_relaxed); for (auto& t:threads) t.join(); throw; }
    for (auto& t:threads) t.join();
    if (failure) std::rethrow_exception(failure);
}

void extract(const std::filesystem::path& path, const Archive& archive, const std::filesystem::path& output, bool raw_mode, bool verbose, unsigned jobs) {
    if (jobs < 1 || jobs > 64) throw Error("jobs must be between 1 and 64");
    std::vector<const Entry*> order; for (const auto& e:archive.entries) order.push_back(&e);
    std::stable_sort(order.begin(),order.end(),[](auto a, auto b){ return a->offset<b->offset; });
    if (jobs==1 || order.size()<2) {
        std::filesystem::create_directories(output);
        std::ifstream in(path,std::ios::binary); if (!in) throw Error("cannot open archive");
        std::size_t index=0;
        for (auto entry:order) {
            auto target=destination(output,entry->name);
            std::filesystem::create_directories(target.parent_path());
            auto file=create_exclusive(target);
            process(in,*entry,file.get(),raw_mode);
            if (std::fflush(file.get()) != 0) throw Error("failed flushing output file");
            ++index; if (verbose && (index%1000==0 || index==order.size())) std::cerr << "[" << index << "/" << order.size() << "] " << entry->name << '\n';
        }
        return;
    }
    // Reject duplicate normalized targets and file/directory conflicts before any writes.
    std::vector<std::filesystem::path> targets; targets.reserve(order.size());
    for (auto entry:order) targets.push_back(destination(output,entry->name).lexically_normal());
    auto sorted=targets; std::sort(sorted.begin(),sorted.end());
    for (std::size_t i=1;i<sorted.size();++i) {
        if (sorted[i]==sorted[i-1]) throw Error("duplicate extraction target: " + sorted[i].u8string());
    }
    // A target's parent cannot itself be a file target. Check all parents, not
    // adjacent strings, because path sort order does not guarantee adjacency.
    for (const auto& target:sorted) {
        for (auto parent=target.parent_path(); !parent.empty() && parent!=output && parent!=parent.root_path(); parent=parent.parent_path()) {
            if (std::binary_search(sorted.begin(),sorted.end(),parent)) throw Error("file and directory target conflict: " + parent.u8string());
        }
    }
    std::filesystem::create_directories(output);
    std::atomic<std::size_t> next{0}, completed{0};
    std::atomic<bool> stop{false}; std::mutex mutex; std::exception_ptr failure;
    auto work=[&] {
        try {
            std::ifstream in(path,std::ios::binary); if (!in) throw Error("cannot open archive");
            while (!stop.load(std::memory_order_relaxed)) {
                auto i=next.fetch_add(1,std::memory_order_relaxed); if (i>=order.size()) break;
                std::filesystem::create_directories(targets[i].parent_path());
                auto file=create_exclusive(targets[i]);
                process(in,*order[i],file.get(),raw_mode);
                if (std::fflush(file.get())!=0) throw Error("failed flushing output file");
                auto count=completed.fetch_add(1,std::memory_order_relaxed)+1;
                if (verbose && (count%1000==0 || count==order.size())) {
                    std::lock_guard<std::mutex> lock(mutex);
                    std::cerr << "[" << count << "/" << order.size() << "] " << order[i]->name << '\n';
                }
            }
        } catch (...) {
            std::lock_guard<std::mutex> lock(mutex);
            if (!failure) failure=std::current_exception();
            stop.store(true,std::memory_order_relaxed);
        }
    };
    std::vector<std::thread> threads;
    try { for (std::size_t i=0;i<std::min<std::size_t>(jobs,order.size());++i) threads.emplace_back(work); }
    catch (...) { stop.store(true,std::memory_order_relaxed); for (auto& t:threads) t.join(); throw; }
    for (auto& t:threads) t.join();
    if (failure) std::rethrow_exception(failure);
}
}
