// End-to-end smoke test of ddradar.dll without the game: plays the game's side of the SCS SDK
// (telemetry + input registration, frame events, truck placement, aux light that cycles
// off -> dimmed -> full -> off on each toggle press) and drives a straight line through a real
// Berlin camera from the shipped camera_db.csv.
//
// usage: harness.exe <path\to\ddradar.dll>      (built and run by plugin\build.ps1 -Harness)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cmath>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>

#include "scssdk_input.h"
#include "scssdk_telemetry.h"
#include "eurotrucks2/scssdk_eut2.h"
#include "common/scssdk_telemetry_truck_common_channels.h"

#include "../src/radar_core.hpp"

namespace {

struct Channel { scs_telemetry_channel_callback_t cb; scs_context_t ctx; };
std::map<scs_event_t, scs_telemetry_event_callback_t> events;
std::map<std::string, Channel> channels;
scs_input_device_t device = {};
std::vector<scs_input_device_input_t> device_inputs;
std::vector<std::string> log_lines;
double cur_s = 0;

SCSAPI_VOID fake_log(const scs_log_type_t, const scs_string_t msg)
{
    std::printf("  game.log: %s\n", msg);
    log_lines.push_back(msg);
}

SCSAPI_RESULT reg_event(const scs_event_t e, const scs_telemetry_event_callback_t cb, const scs_context_t)
{
    events[e] = cb;
    return SCS_RESULT_ok;
}
SCSAPI_RESULT unreg_event(const scs_event_t e) { events.erase(e); return SCS_RESULT_ok; }

SCSAPI_RESULT reg_channel(const scs_string_t name, const scs_u32_t, const scs_value_type_t, const scs_u32_t,
                          const scs_telemetry_channel_callback_t cb, const scs_context_t ctx)
{
    channels[name] = {cb, ctx};
    return SCS_RESULT_ok;
}
SCSAPI_RESULT unreg_channel(const scs_string_t name, const scs_u32_t, const scs_value_type_t)
{
    channels.erase(name);
    return SCS_RESULT_ok;
}

// SDK rules (scssdk_input_device.h): names [a-z0-9_]; display names English letters, digits,
// underscore, space, dot. The game rejects the whole device otherwise (seen 2026-10-07).
bool valid_name(const char *s)
{
    for (; *s; ++s)
        if (!((*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9') || *s == '_')) return false;
    return true;
}
bool valid_display(const char *s)
{
    for (; *s; ++s)
        if (!(isalnum(static_cast<unsigned char>(*s)) || *s == '_' || *s == ' ' || *s == '.')) return false;
    return true;
}

SCSAPI_RESULT reg_device(const scs_input_device_t *const info)
{
    bool ok = valid_name(info->name) && valid_display(info->display_name);
    for (scs_u32_t i = 0; i < info->input_count; ++i)
        ok = ok && valid_name(info->inputs[i].name) && valid_display(info->inputs[i].display_name);
    if (!ok) {
        std::printf("  game.log: <ERROR> [sdk] input_register_device: invalid name/display_name\n");
        return SCS_RESULT_invalid_parameter;
    }
    device = *info;
    device_inputs.assign(info->inputs, info->inputs + info->input_count);
    device.inputs = device_inputs.data();
    return SCS_RESULT_ok;
}

void send_u32(const char *name, scs_u32_t v)
{
    auto it = channels.find(name);
    if (it == channels.end()) return;
    scs_value_t val = {};
    val.type = SCS_VALUE_TYPE_u32;
    val.value_u32.value = v;
    it->second.cb(name, SCS_U32_NIL, &val, it->second.ctx);
}

void send_placement(double x, double y, double z)
{
    auto it = channels.find(SCS_TELEMETRY_TRUCK_CHANNEL_world_placement);
    if (it == channels.end()) return;
    scs_value_t val = {};
    val.type = SCS_VALUE_TYPE_dplacement;
    val.value_dplacement.position.x = x;
    val.value_dplacement.position.y = y;
    val.value_dplacement.position.z = z;
    it->second.cb(SCS_TELEMETRY_TRUCK_CHANNEL_world_placement, SCS_U32_NIL, &val, it->second.ctx);
}

int failures = 0;
void check(bool ok, const char *what)
{
    std::printf("%s %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) ++failures;
}

}  // namespace

int main(int argc, char **argv)
{
    if (argc < 2) { std::printf("usage: harness <ddradar.dll>\n"); return 2; }
    HMODULE dll = LoadLibraryA(argv[1]);
    if (!dll) { std::printf("cannot load %s\n", argv[1]); return 2; }
    auto tinit = reinterpret_cast<decltype(&scs_telemetry_init)>(GetProcAddress(dll, "scs_telemetry_init"));
    auto tshut = reinterpret_cast<decltype(&scs_telemetry_shutdown)>(GetProcAddress(dll, "scs_telemetry_shutdown"));
    auto iinit = reinterpret_cast<decltype(&scs_input_init)>(GetProcAddress(dll, "scs_input_init"));
    auto ishut = reinterpret_cast<decltype(&scs_input_shutdown)>(GetProcAddress(dll, "scs_input_shutdown"));
    check(tinit && tshut && iinit && ishut, "all four SDK entry points exported");
    if (!(tinit && iinit)) return 1;

    scs_telemetry_init_params_v101_t tp = {};
    tp.common.game_name = "Euro Truck Simulator 2";
    tp.common.game_id = SCS_GAME_ID_EUT2;
    tp.common.game_version = SCS_MAKE_VERSION(1, 19);
    tp.common.log = fake_log;
    tp.register_for_event = reg_event;
    tp.unregister_from_event = unreg_event;
    tp.register_for_channel = reg_channel;
    tp.unregister_from_channel = unreg_channel;
    check(tinit(SCS_TELEMETRY_VERSION_1_01, &tp) == SCS_RESULT_ok, "telemetry init ok");

    scs_input_init_params_v100_t ip = {};
    ip.common = tp.common;
    ip.register_device = reg_device;
    check(iinit(SCS_INPUT_VERSION_1_00, &ip) == SCS_RESULT_ok, "input init ok");
    check(device.input_event_callback != nullptr && device.input_count == 2, "device with 2 inputs registered");

    // pick a Berlin camera from the same DB the plugin loaded
    std::string dir(argv[1]);
    dir = dir.substr(0, dir.find_last_of("\\/"));
    auto cams = ddradar::load_cameras(dir + "\\ddradar\\camera_db.csv");
    const ddradar::Camera *cam = nullptr;
    for (auto &c : cams)
        if (c.model == "speed_camera_ch" && c.x > 8500 && c.x < 13500 && c.z > -11500 && c.z < -8000) { cam = &c; break; }
    check(cam != nullptr, "Berlin speed_camera_ch found in DB");
    if (!cam) return 1;
    std::printf("driving at 15 m/s towards camera at (%.1f, %.1f) from 800 m, 200 m past it\n", cam->x, cam->z);

    events[SCS_TELEMETRY_EVENT_started](SCS_TELEMETRY_EVENT_started, nullptr, nullptr);

    scs_u32_t aux_front = 0;          // game state: 0 off, 1 dimmed, 2 full (toggle cycles)
    bool prev_button = false;
    double first_on = 0, last_off_after = -1;
    bool seen_on = false;
    int presses = 0;
    const double dt = 1.0 / 60, speed = 15.0;
    scs_telemetry_frame_start_t fs = {};
    for (double s = -800; s <= 200; s += speed * dt) {
        cur_s = s;
        fs.render_time += static_cast<scs_timestamp_t>(dt * 1e6);
        events[SCS_TELEMETRY_EVENT_frame_start](SCS_TELEMETRY_EVENT_frame_start, &fs, nullptr);
        send_placement(cam->x, cam->y, cam->z - s);   // moving towards -Z, camera at s = 0
        send_u32(SCS_TELEMETRY_TRUCK_CHANNEL_light_aux_front, aux_front);
        send_u32(SCS_TELEMETRY_TRUCK_CHANNEL_light_aux_roof, 0);

        // game polls the device; input 0 is bound by the "user" to the front aux toggle
        bool button = prev_button;
        scs_input_event_t ev = {};
        for (scs_u32_t call = 0; call < 10; ++call) {
            scs_u32_t flags = call == 0 ? SCS_INPUT_EVENT_CALLBACK_FLAG_first_in_frame : 0;
            if (device.input_event_callback(&ev, flags, device.callback_context) != SCS_RESULT_ok) break;
            if (ev.input_index == 0) button = ev.value_bool.value != 0;
        }
        if (button && !prev_button) { aux_front = (aux_front + 1) % 3; ++presses; std::printf("  press at s=%.0f -> aux %u\n", s, aux_front); }
        prev_button = button;

        if (aux_front != 0 && !seen_on) { seen_on = true; first_on = s; }
        if (aux_front == 0 && seen_on && s > 0 && last_off_after < 0) last_off_after = s;
    }
    std::printf("aux on at %.0f m before the camera, off %.0f m after it, %d presses\n",
                -first_on, last_off_after, presses);
    check(seen_on && first_on >= -360 && first_on <= -250, "aux switched on ~350 m before the camera");
    check(last_off_after > 0 && last_off_after < 120, "aux back off shortly after passing");
    bool logged = false;
    for (auto &l : log_lines) logged |= l.find("camera ahead: speed_camera_ch") != std::string::npos;
    check(logged, "game.log shows 'camera ahead: speed_camera_ch'");

    ishut();
    tshut();
    FreeLibrary(dll);
    std::printf(failures ? "%d FAILED\n" : "harness passed\n", failures);
    return failures ? 1 : 0;
}
