#include "arch00.hpp"
#include "gui_page.hpp"
#include "glob.hpp"
#include <algorithm>
#include <cctype>
#include <vector>
#include <httplib.h>
#include <nlohmann/json.hpp>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <random>
#include <sstream>
#include <string>

namespace fs=std::filesystem;
using json=nlohmann::json;
namespace {
std::string lower_ascii(std::string s) {
    for (auto& c : s) c=static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}
std::string batch_run(const fs::path& directory, const fs::path& output, bool extracting,
                      bool raw, unsigned jobs, bool skip, bool& failed) {
    std::vector<fs::path> paths;
    for (const auto& item : fs::directory_iterator(directory)) {
        if (item.is_regular_file() && lower_ascii(item.path().extension().string())==".arch00") paths.push_back(item.path());
    }
    std::sort(paths.begin(),paths.end(),[](const auto& a,const auto& b) { return lower_ascii(a.filename().string()) < lower_ascii(b.filename().string()); });
    if (paths.empty()) throw arch00::Error("No .Arch00 archives found in input directory");
    if (extracting) fs::create_directories(output);
    std::ostringstream result; std::size_t errors=0, skipped=0;
    for (const auto& path : paths) {
        fs::path final, partial;
        if (extracting) {
            final=output/path.filename(); final += ".extracted";
            partial=output/path.filename(); partial += ".extracted.incomplete";
            if (fs::exists(final)) {
                if (skip) { ++skipped; result << "SKIP " << path.filename().u8string() << "\n"; continue; }
                throw arch00::Error("Destination already exists: " + final.u8string());
            }
            if (fs::exists(partial)) throw arch00::Error("Incomplete destination already exists: " + partial.u8string());
        }
        try {
            auto a=arch00::parse(path);
            if (extracting) {
                if (!fs::create_directory(partial)) throw arch00::Error("Could not create incomplete directory");
                arch00::extract(path,a,partial,raw,false,jobs);
                fs::rename(partial,final);
            } else arch00::test(path,a,raw,false,jobs);
            result << "OK " << path.filename().u8string() << ": " << a.entries.size() << " files\n";
        } catch (const std::exception& e) { ++errors; result << "FAIL " << path.filename().u8string() << ": " << e.what() << "\n"; }
    }
    result << "Processed " << paths.size() << " archives; skipped=" << skipped << " failed=" << errors;
    failed=errors!=0;
    return result.str();
}
}
int main() {
    try {
        // Only listen on IPv4 loopback. The fragment is never sent as an HTTP request.
        std::random_device rng; std::ostringstream secret;
        for (int i=0;i<32;++i) secret << std::hex << std::setw(2) << std::setfill('0') << (rng() & 255);
        const std::string token=secret.str();
        httplib::Server server;
        server.set_payload_max_length(16384);
        server.set_default_headers({{"Cache-Control","no-store"},{"X-Content-Type-Options","nosniff"},{"Referrer-Policy","no-referrer"},{"Content-Security-Policy","default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"}});
        std::mutex operation; int port=0;
        const auto valid_host=[&](const httplib::Request& req) { return req.remote_addr=="127.0.0.1" && req.get_header_value("Host")=="127.0.0.1:"+std::to_string(port); };
        server.Get("/", [&](const httplib::Request& req, httplib::Response& res) {
            if (!valid_host(req)) { res.status=403; return; }
            res.set_content(gui_page,"text/html; charset=utf-8");
        });
        server.Post("/api", [&](const httplib::Request& req, httplib::Response& res) {
            auto answer=[&](int status,const std::string& text) { res.status=status; res.set_content(json{{"message",text}}.dump(-1,' ',false,json::error_handler_t::replace),"application/json"); };
            if (!valid_host(req) || req.get_header_value("Origin")!="http://127.0.0.1:"+std::to_string(port) || req.get_header_value("X-Arch00-Token")!=token || req.get_header_value("Content-Type")!="application/json") { answer(403,"Forbidden"); return; }
            std::unique_lock<std::mutex> lock(operation,std::try_to_lock); if (!lock.owns_lock()) { answer(409,"Another operation is running"); return; }
            try {
                auto data=json::parse(req.body);
                auto action=data.at("action").get<std::string>(); auto archive=data.at("archive").get<std::string>();
                if (archive.empty() || archive.find('\0')!=std::string::npos) throw arch00::Error("Archive path is required");
                auto path=fs::u8path(archive);
                if (action=="repack") {
                    auto output=data.at("output").get<std::string>(), replace=data.value("replace",std::string{});
                    if (output.empty() || output.find('\0')!=std::string::npos || replace.find('\0')!=std::string::npos) throw arch00::Error("Invalid output or replacement path");
                    auto result=arch00::repack(path,fs::u8path(output),fs::u8path(replace));
                    answer(200,"Repacked and verified " + std::to_string(result.files) + " files; replaced=" + std::to_string(result.replaced)); return;
                }
                if (action!="list" && action!="test" && action!="extract" && action!="test-all" && action!="extract-all") throw arch00::Error("Unknown action");
                auto compression=data.value("compression",std::string("auto")); if(compression!="auto" && compression!="raw") throw arch00::Error("Invalid compression mode");
                if (data.contains("jobs") && !data["jobs"].is_number_integer()) throw arch00::Error("Workers must be an integer");
                auto jobs=data.value("jobs",1); if(jobs<1 || jobs>64) throw arch00::Error("Workers must be 1–64");
                if (action=="test-all" || action=="extract-all") {
                    const bool extracting=action=="extract-all";
                    auto out=data.value("output",std::string{});
                    if (extracting && (out.empty() || out.find('\0')!=std::string::npos)) throw arch00::Error("Output path is required");
                    bool failed=false;
                    auto message=batch_run(path,fs::u8path(out),extracting,compression=="raw",static_cast<unsigned>(jobs),data.value("skip_existing",false),failed);
                    answer(failed ? 400 : 200,message); return;
                }
                auto a=arch00::parse(path);
                if (action=="list") {
                    std::ostringstream out; out << "LTAR v" << a.header.version << "; " << a.entries.size() << " files\n\n";
                    const std::size_t limit=2000;
                    for (std::size_t i=0;i<a.entries.size() && i<limit;++i) { const auto& e=a.entries[i]; out << e.stored_size << " -> " << e.unpacked_size << " [" << e.compression << "] " << e.name << '\n'; }
                    if(a.entries.size()>limit) out << "\nOnly first " << limit << " entries shown. Use the CLI for the full listing.\n";
                    answer(200,out.str()); return;
                }
                if(action=="test") { arch00::test(path,a,compression=="raw",false,static_cast<unsigned>(jobs)); answer(200,"Validated " + std::to_string(a.entries.size()) + " files"); return; }
                auto output=data.at("output").get<std::string>(); if(output.empty() || output.find('\0')!=std::string::npos) throw arch00::Error("Output path is required");
                auto pattern=data.value("pattern",std::string{});
                if (!pattern.empty()) a.entries.erase(std::remove_if(a.entries.begin(),a.entries.end(),[&](const auto& entry){return !glob_match(entry.name,pattern);}),a.entries.end());
                arch00::extract(path,a,fs::u8path(output),compression=="raw",false,static_cast<unsigned>(jobs)); answer(200,"Extracted " + std::to_string(a.entries.size()) + " files");
            } catch (const std::exception& e) { answer(400,e.what()); }
        });
        port=server.bind_to_any_port("127.0.0.1"); if(port<0) throw arch00::Error("Could not bind loopback port");
        std::cout << "Open http://127.0.0.1:" << port << "/#" << token << "\nPress Ctrl+C to stop. Do not share this URL.\n" << std::flush;
        if(!server.listen_after_bind()) throw arch00::Error("Server stopped unexpectedly");
        return 0;
    } catch(const std::exception& e) { std::cerr << "error: " << e.what() << '\n'; return 2; }
}
