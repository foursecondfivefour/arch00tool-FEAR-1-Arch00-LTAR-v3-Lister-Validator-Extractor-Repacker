#pragma once
#include <codecvt>
#include <locale>
#include <string>
#include <vector>

// Case-sensitive glob matching over Unicode code points; separators are ordinary characters.
inline bool glob_match(const std::string& name, const std::string& pattern) {
    std::wstring_convert<std::codecvt_utf8<char32_t>, char32_t> converter;
    auto s=converter.from_bytes(name), p=converter.from_bytes(pattern);
    std::vector<unsigned char> prev(s.size()+1), next(s.size()+1); prev[0]=1;
    for (std::size_t i=0;i<p.size();++i) {
        std::fill(next.begin(),next.end(),0);
        if (p[i]==U'*') {
            next[0]=prev[0]; for (std::size_t j=1;j<=s.size();++j) next[j]=prev[j] || next[j-1];
        } else if (p[i]==U'?') {
            for (std::size_t j=1;j<=s.size();++j) next[j]=prev[j-1];
        } else if (p[i]==U'[') {
            std::size_t end=i+1; if (end<p.size() && p[end]==U'!') ++end;
            if (end<p.size() && p[end]==U']') ++end;
            while (end<p.size() && p[end]!=U']') ++end;
            if (end==p.size()) { for (std::size_t j=1;j<=s.size();++j) next[j]=prev[j-1] && s[j-1]==U'['; }
            else {
                std::size_t first=i+1; bool neg=first<end && p[first]==U'!'; if (neg) ++first;
                for (std::size_t j=1;j<=s.size();++j) {
                    bool match=false; for (std::size_t k=first;k<end;++k) {
                        if (k+2<end && p[k+1]==U'-') { if (p[k]<=s[j-1] && s[j-1]<=p[k+2]) match=true; k+=2; }
                        else if (p[k]==s[j-1]) match=true;
                    }
                    next[j]=prev[j-1] && (neg ? !match : match);
                }
                i=end;
            }
        } else for (std::size_t j=1;j<=s.size();++j) next[j]=prev[j-1] && s[j-1]==p[i];
        prev.swap(next);
    }
    return prev[s.size()]!=0;
}
