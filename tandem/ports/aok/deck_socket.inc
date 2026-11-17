
// ------------------------------------------------------------------ Tandem (Linux handheld)
// Appended to src/thor/Thor.cpp by tandem/ports/aok/build.sh: there the deck is Tandem's bottom screen
// (ui/decks/aok.py), and a local socket takes the place of the Android JNI bridge. What ThorBridge.java reads through
// JNI goes out as one JSON line: "i" is the snapshot's numbers as they are (Thor::Header and what follows it), the
// rest its words. The mini-map and the icons are binary blocks the deck asks for.
#include <cstdio>

#include "tandem_deck.h"

namespace {

void TandemWords(std::string& out, const char* key, const std::string& words) {
    out += key;
    out += '"';
    for (const char c : words) {
        if (c == '"' || c == '\\') out += '\\';
        out += static_cast<unsigned char>(c) < 0x20 ? ' ' : c;
    }
    out += '"';
}

void TandemList(std::string& out, const char* key, const std::vector<std::string>& list) {
    out += key;
    out += '[';
    for (size_t i = 0; i < list.size(); ++i) TandemWords(out, i ? "," : "", list[i]);
    out += ']';
}

// The state for the deck; without a game (or with one that stopped drawing) only that there is none.
int TandemState(char* buf, int size) {
    std::string out;
    {
        std::lock_guard<std::mutex> hold(Thor::S().lock);
        const auto& s = Thor::S();
        if (s.written == 0 || SDL_GetTicks() - s.written > 1500) {
            out = "{\"v\":1,\"ingame\":0}";
        } else {
            out = "{\"v\":1,\"ingame\":1,\"i\":[";
            for (size_t i = 0; i < s.snap.size(); ++i) out += (i ? "," : "") + std::to_string(s.snap[i]);
            out += ']';
            TandemWords(out, ",\"age\":", s.age);
            TandemWords(out, ",\"next\":", s.next_age);
            TandemWords(out, ",\"name\":", s.name);
            TandemList(out, ",\"labels\":", s.labels);
            TandemList(out, ",\"goto\":", s.go_to);
            const size_t without_help = out.size();
            TandemList(out, ",\"help\":", s.help);
            if (out.size() + 1 >= static_cast<size_t>(size)) out.resize(without_help);   // the help is what can go
            out += '}';
        }
    }
    if (out.size() >= static_cast<size_t>(size)) return 0;
    std::memcpy(buf, out.c_str(), out.size() + 1);
    return static_cast<int>(out.size());
}

// "cmd <type> <a> <b>": a Thor::Command. "map": the mini-map as the block "map", kMapW x kMapH pixels of four bytes
// (blue, green, red, alpha). "icon <slp> <frame>": an interface graphic as the block "icon:<slp>:<frame>", its width
// and height (two bytes each, low byte first) and then its pixels; empty when there is none.
void TandemCommand(const char* line) {
    int a = 0, b = 0, c = 0;
    if (std::sscanf(line, "cmd %d %d %d", &a, &b, &c) >= 1) {
        if (a >= Thor::kCommand && a <= Thor::kGame) Thor::Push(a, b, c);
    } else if (std::strcmp(line, "map") == 0) {
        std::vector<int> pixels;
        {
            std::lock_guard<std::mutex> hold(Thor::S().lock);
            pixels = Thor::S().pixels;
        }
        TandemDeck_Block("map", pixels.data(), pixels.size() * sizeof(int));
    } else if (std::sscanf(line, "icon %d %d", &a, &b) == 2) {
        auto& cache = HAL::GraphicCache::Get();
        const HAL::DrsArchive* drs = cache.InterfaceArchive();
        HAL::SlpFrame f;
        std::vector<uint32_t> out;
        if (drs != nullptr && a > 0 && b >= 0 && HAL::SlpDecodeFrame(*drs, static_cast<uint32_t>(a), static_cast<uint32_t>(b), f) &&
            f.width > 0 && f.height > 0 && f.width < 65536 && f.height < 65536) {
            const size_t n = static_cast<size_t>(f.width) * static_cast<size_t>(f.height);
            out.assign(n + 1, 0);
            out[0] = static_cast<uint32_t>(f.width) | static_cast<uint32_t>(f.height) << 16;
            for (size_t i = 0; i < n; ++i) {
                if (!f.alpha[i]) continue;
                const HAL::PaletteColor p = cache.GetPaletteColor(f.player[i] ? f.player[i] : f.indexes[i]);
                out[i + 1] = 0xFF000000u | static_cast<uint32_t>(p.r << 16) | static_cast<uint32_t>(p.g << 8) | p.b;
            }
        }
        char name[48];
        std::snprintf(name, sizeof name, "icon:%d:%d", a, b);
        TandemDeck_Block(name, out.data(), out.size() * sizeof(uint32_t));
    }
}

// With Tandem's socket in the environment the deck is there: the top screen draws no interface.
struct TandemBoot {
    TandemBoot() {
        if (std::getenv("TANDEM_DECK_SOCKET") == nullptr) return;
        Thor::SetDual(true);
        TandemDeck_Start(TandemState, TandemCommand);
    }
} tandem_boot;

} // namespace
