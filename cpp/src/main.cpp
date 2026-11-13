#include "arch00.hpp"
#include "glob.hpp"
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>
namespace fs=std::filesystem;
namespace {
std::string lower(std::string s) { for (auto& c:s) c=static_cast<char>(std::tolower(static_cast<unsigned char>(c))); return s; }
std::vector<fs::path> archive_files(const fs::path& dir) {
    std::vector<fs::path> files;
    for (const auto& item:fs::directory_iterator(dir)) if (item.is_regular_file() && lower(item.path().extension().string())==".arch00") files.push_back(item.path());
    std::sort(files.begin(),files.end(),[](const auto& a,const auto& b){return lower(a.filename().string())<lower(b.filename().string());});
    if (files.empty()) throw arch00::Error("no .Arch00 archives found in " + dir.string());
    return files;
}
void list(const fs::path& path, const arch00::Archive& a, bool verbose) {
    const auto& h=a.header;
    std::cout << "Archive: " << path.string() << "\nLTAR v" << h.version << "\nNames: " << h.names_size << "; folders: " << h.folder_count << "; file records: " << h.file_count << "\nHeader flags: retail=" << h.retail << " download=" << h.download << " crc=" << h.crc_enabled << "\nGUID bytes: ";
    for (auto c:h.guid) std::cout << std::hex << std::setw(2) << std::setfill('0') << unsigned(c);
    std::cout << std::dec << std::setfill(' ') << '\n';
    for (const auto& e:a.entries) std::cout << e.stored_size << " -> " << e.unpacked_size << " " << (e.compression==0 ? "raw" : "method="+std::to_string(e.compression)) << " " << e.name << '\n';
    if (verbose) for (const auto& f:a.folders) std::cout << "Folder: " << f << '\n';
}
int batch(const std::string& cmd, const fs::path& dir, const fs::path& output, bool raw, bool skip, bool verbose, unsigned jobs) {
    auto paths=archive_files(dir); std::size_t failed=0, skipped=0;
    if (cmd=="extract-all") fs::create_directories(output);
    for (std::size_t i=0;i<paths.size();++i) {
        const auto& path=paths[i]; fs::path final, partial;
        if (cmd=="extract-all") {
            final=output / path.filename(); final += ".extracted";
            partial=output / path.filename(); partial += ".extracted.incomplete";
            if (fs::exists(final)) { if (skip) { ++skipped; std::cerr << "SKIP existing " << final.string() << '\n'; continue; } throw arch00::Error("destination already exists: " + final.string()); }
            if (fs::exists(partial)) throw arch00::Error("incomplete destination already exists: " + partial.string());
        }
        std::cerr << "[" << i+1 << "/" << paths.size() << "] " << path.filename().string() << '\n';
        try {
            auto a=arch00::parse(path);
            if (cmd=="test-all") arch00::test(path,a,raw,false,jobs);
            else { if (!fs::create_directory(partial)) throw arch00::Error("cannot create incomplete directory"); arch00::extract(path,a,partial,raw,verbose,jobs); fs::rename(partial,final); }
            std::cout << "OK " << path.filename().string() << ": " << a.entries.size() << " files\n";
        } catch (const std::exception& e) { ++failed; std::cout << "FAIL " << path.filename().string() << ": " << e.what() << '\n'; }
    }
    std::cout << "Processed " << paths.size() << " archives; skipped=" << skipped << " failed=" << failed << '\n'; return failed ? 1 : 0;
}
}
int main(int argc, char** argv) {
    if (argc<3) { std::cerr << "Usage: arch00tool-cpp list|test|extract|test-all|extract-all|repack INPUT [OUTPUT] [options]\n"; return 2; }
    try {
        std::string cmd=argv[1], pattern, replace_dir; bool raw=false, verbose=false, skip=false; unsigned jobs=1; int start=3;
        bool extracting=cmd=="extract" || cmd=="extract-all";
        bool has_output=extracting || cmd=="repack";
        if (has_output) { if (argc<4) throw arch00::Error("extract requires an output directory"); start=4; }
        if (cmd!="list" && cmd!="test" && cmd!="extract" && cmd!="test-all" && cmd!="extract-all" && cmd!="repack") throw arch00::Error("unsupported command");
        for (int i=start;i<argc;++i) {
            std::string arg=argv[i];
            if ((cmd=="list" || cmd=="test" || extracting) && (arg=="-v" || arg=="--verbose")) verbose=true;
            else if (cmd!="list" && cmd!="repack" && arg=="--compression" && i+1<argc) {
                std::string mode=argv[++i]; if (mode!="auto" && mode!="raw") throw arch00::Error("invalid compression mode"); raw=(mode=="raw");
            } else if ((cmd=="test" || cmd=="test-all" || extracting) && arg=="--jobs" && i+1<argc) {
                std::string value=argv[++i];
                if (value.empty() || value.size()>2 || value.find_first_not_of("0123456789")!=std::string::npos) throw arch00::Error("jobs must be between 1 and 64");
                jobs=static_cast<unsigned>(std::stoul(value)); if (jobs<1 || jobs>64) throw arch00::Error("jobs must be between 1 and 64");
            } else if (cmd=="repack" && arg=="--replace-dir" && i+1<argc) replace_dir=argv[++i];
            else if (cmd=="extract" && arg=="--pattern" && i+1<argc) pattern=argv[++i];
            else if (cmd=="extract-all" && arg=="--skip-existing") skip=true;
            else throw arch00::Error("unknown or incomplete option: " + arg);
        }
        if (cmd=="repack") { auto result=arch00::repack(fs::u8path(argv[2]),fs::u8path(argv[3]),fs::u8path(replace_dir)); std::cout << "Repacked and verified " << result.files << " files (" << result.payload_bytes << " payload bytes); replaced=" << result.replaced << '\n'; return 0; }
        if (cmd=="test-all" || cmd=="extract-all") return batch(cmd,fs::u8path(argv[2]),extracting ? fs::u8path(argv[3]) : fs::path{},raw,skip,verbose,jobs);
        auto path=fs::u8path(argv[2]); auto a=arch00::parse(path);
        if (cmd=="test") { arch00::test(path,a,raw,verbose,jobs); std::cout << "OK: validated " << a.entries.size() << " files\n"; return 0; }
        if (cmd=="extract") {
            if (!pattern.empty()) a.entries.erase(std::remove_if(a.entries.begin(),a.entries.end(),[&](const auto& e){return !glob_match(e.name,pattern);}),a.entries.end());
            arch00::extract(path,a,fs::u8path(argv[3]),raw,verbose,jobs); std::cout << "Extracted " << a.entries.size() << " files\n"; return 0;
        }
        list(path,a,verbose); return 0;
    } catch (const std::exception& e) { std::cerr << "error: " << e.what() << '\n'; return 2; }
}
