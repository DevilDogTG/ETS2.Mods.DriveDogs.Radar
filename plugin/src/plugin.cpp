// DriveDogs Radar - SCS SDK plugin (telemetry + input) for Euro Truck Simulator 2.
//
// Telemetry gives the truck position and the aux light state; the core decides whether a speed
// camera is ahead; an input device "DriveDogs Radar" presses the aux toggle so the windshield
// detector accessory (flare light_type: aux) blinks. The user binds the device's buttons to the
// game's aux light controls once (Options > Controls).
//
// Install: bin\win_x64\plugins\ddradar.dll + bin\win_x64\plugins\ddradar\camera_db.csv
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>

#include "scssdk_input.h"
#include "scssdk_telemetry.h"
#include "eurotrucks2/scssdk_eut2.h"
#include "eurotrucks2/scssdk_input_eut2.h"
#include "eurotrucks2/scssdk_telemetry_eut2.h"
#include "common/scssdk_telemetry_common_channels.h"
#include "common/scssdk_telemetry_truck_common_channels.h"

#include "radar_core.hpp"

namespace {

enum AuxTarget { AUX_FRONT = 0, AUX_ROOF = 1, AUX_COUNT = 2 };

struct State {
    scs_log_t log = nullptr;
    std::unique_ptr<ddradar::Detector> detector;
    ddradar::AuxController aux_ctl;

    bool paused = true;
    bool have_position = false;
    double x = 0, y = 0, z = 0;
    scs_u32_t aux[AUX_COUNT] = {0, 0};
    scs_timestamp_t last_time = 0;
    bool have_time = false;

    // input device: pending press (down this frame, up next frame) per target
    int press_stage[AUX_COUNT] = {0, 0};
    bool alert_logged = false;
};

State g;

void log_line(scs_log_type_t type, const char *fmt, ...)
{
    if (!g.log) return;
    char buf[512];
    va_list args;
    va_start(args, fmt);
    std::vsnprintf(buf, sizeof buf, fmt, args);
    va_end(args);
    std::string line = std::string("[ddradar] ") + buf;
    g.log(type, line.c_str());
}

std::string plugin_dir()
{
    HMODULE self = nullptr;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       reinterpret_cast<LPCSTR>(&plugin_dir), &self);
    char path[MAX_PATH] = {};
    GetModuleFileNameA(self, path, MAX_PATH);
    std::string p(path);
    return p.substr(0, p.find_last_of("\\/"));
}

// ---------------------------------------------------------------- telemetry callbacks

SCSAPI_VOID on_placement(const scs_string_t, const scs_u32_t, const scs_value_t *const value, const scs_context_t)
{
    if (!value) return;
    const scs_value_dplacement_t &p = value->value_dplacement;
    g.x = p.position.x;
    g.y = p.position.y;
    g.z = p.position.z;
    g.have_position = true;
}

SCSAPI_VOID on_aux(const scs_string_t, const scs_u32_t, const scs_value_t *const value, const scs_context_t context)
{
    const auto target = static_cast<AuxTarget>(reinterpret_cast<uintptr_t>(context));
    g.aux[target] = value ? value->value_u32.value : 0;
}

SCSAPI_VOID on_paused(const scs_event_t event, const void *const, const scs_context_t)
{
    g.paused = (event == SCS_TELEMETRY_EVENT_paused);
}

SCSAPI_VOID on_frame_start(const scs_event_t, const void *const event_info, const scs_context_t)
{
    const auto *info = static_cast<const scs_telemetry_frame_start_t *>(event_info);
    double dt = 0;
    if (g.have_time && info->render_time >= g.last_time)
        dt = (info->render_time - g.last_time) / 1e6;
    g.last_time = info->render_time;
    g.have_time = true;
    if (info->flags & SCS_TELEMETRY_FRAME_START_FLAG_timer_restart) dt = 0;

    if (g.paused || !g.have_position || !g.detector || dt <= 0 || dt > 1.0) return;

    const bool alert = g.detector->update(g.x, g.y, g.z, dt);
    if (alert != g.alert_logged) {
        if (alert) {
            const auto &cam = g.detector->cameras()[g.detector->nearest()];
            log_line(SCS_LOG_TYPE_message, "camera ahead: %s at %.0f m", cam.model.c_str(),
                     g.detector->nearest_distance());
        } else {
            log_line(SCS_LOG_TYPE_message, "camera passed");
        }
        g.alert_logged = alert;
    }

    // POC: drive the front aux toggle; telemetry tells us when the game applied it.
    const bool aux_on = g.aux[AUX_FRONT] != SCS_TELEMETRY_TRUCK_LIGHT_AUX_off ||
                        g.aux[AUX_ROOF] != SCS_TELEMETRY_TRUCK_LIGHT_AUX_off;
    if (g.aux_ctl.update(alert, aux_on, dt) && g.press_stage[AUX_FRONT] == 0) {
        g.press_stage[AUX_FRONT] = 1;
        g.press_stage[AUX_ROOF] = 1;
    }
}

// ---------------------------------------------------------------- input device

const scs_input_device_input_t k_inputs[AUX_COUNT] = {
    {"aux_front", "Aux toggle A (bind to front aux lights)", SCS_VALUE_TYPE_bool},
    {"aux_roof", "Aux toggle B (bind to roof aux lights)", SCS_VALUE_TYPE_bool},
};

SCSAPI_RESULT on_input_event(scs_input_event_t *const event_info, const scs_u32_t, const scs_context_t)
{
    // The game calls this repeatedly each frame until we return not_found.
    for (scs_u32_t i = 0; i < AUX_COUNT; ++i) {
        int &stage = g.press_stage[i];
        if (stage == 1) {          // button down
            event_info->input_index = i;
            event_info->value.value_bool.value = 1;
            stage = 2;
            return SCS_RESULT_ok;
        }
        if (stage == 2) {          // button up (next call)
            event_info->input_index = i;
            event_info->value.value_bool.value = 0;
            stage = 0;
            return SCS_RESULT_ok;
        }
    }
    return SCS_RESULT_not_found;
}

}  // namespace

// ---------------------------------------------------------------- SDK entry points

SCSAPI_RESULT scs_telemetry_init(const scs_u32_t version, const scs_telemetry_init_params_t *const params)
{
    if (version != SCS_TELEMETRY_VERSION_1_01) return SCS_RESULT_unsupported;
    const auto *p = static_cast<const scs_telemetry_init_params_v101_t *>(params);
    g.log = p->common.log;

    if (std::strcmp(p->common.game_id, SCS_GAME_ID_EUT2) != 0) {
        log_line(SCS_LOG_TYPE_warning, "not Euro Truck Simulator 2 (%s), disabled", p->common.game_id);
        return SCS_RESULT_unsupported;
    }

    std::string err;
    const std::string db = plugin_dir() + "\\ddradar\\camera_db.csv";
    auto cams = ddradar::load_cameras(db, &err);
    if (cams.empty()) {
        log_line(SCS_LOG_TYPE_error, "no cameras loaded (%s)", err.empty() ? db.c_str() : err.c_str());
        return SCS_RESULT_generic_error;
    }
    log_line(SCS_LOG_TYPE_message, "loaded %u cameras from %s", static_cast<unsigned>(cams.size()), db.c_str());
    g.detector = std::make_unique<ddradar::Detector>(std::move(cams));

    bool ok = p->register_for_event(SCS_TELEMETRY_EVENT_frame_start, on_frame_start, nullptr) == SCS_RESULT_ok;
    ok &= p->register_for_event(SCS_TELEMETRY_EVENT_paused, on_paused, nullptr) == SCS_RESULT_ok;
    ok &= p->register_for_event(SCS_TELEMETRY_EVENT_started, on_paused, nullptr) == SCS_RESULT_ok;
    ok &= p->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_world_placement, SCS_U32_NIL,
                                  SCS_VALUE_TYPE_dplacement, SCS_TELEMETRY_CHANNEL_FLAG_none,
                                  on_placement, nullptr) == SCS_RESULT_ok;
    ok &= p->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_light_aux_front, SCS_U32_NIL,
                                  SCS_VALUE_TYPE_u32, SCS_TELEMETRY_CHANNEL_FLAG_none, on_aux,
                                  reinterpret_cast<scs_context_t>(static_cast<uintptr_t>(AUX_FRONT))) == SCS_RESULT_ok;
    ok &= p->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_light_aux_roof, SCS_U32_NIL,
                                  SCS_VALUE_TYPE_u32, SCS_TELEMETRY_CHANNEL_FLAG_none, on_aux,
                                  reinterpret_cast<scs_context_t>(static_cast<uintptr_t>(AUX_ROOF))) == SCS_RESULT_ok;
    if (!ok) {
        log_line(SCS_LOG_TYPE_error, "telemetry registration failed");
        return SCS_RESULT_generic_error;
    }
    log_line(SCS_LOG_TYPE_message, "telemetry ready");
    return SCS_RESULT_ok;
}

SCSAPI_VOID scs_telemetry_shutdown(void)
{
    g.detector.reset();
}

SCSAPI_RESULT scs_input_init(const scs_u32_t version, const scs_input_init_params_t *const params)
{
    if (version != SCS_INPUT_VERSION_1_00) return SCS_RESULT_unsupported;
    const auto *p = static_cast<const scs_input_init_params_v100_t *>(params);
    if (!g.log) g.log = p->common.log;

    scs_input_device_t dev = {};
    dev.name = "ddradar";
    dev.display_name = "DriveDogs Radar";
    dev.type = SCS_INPUT_DEVICE_TYPE_generic;
    dev.input_count = AUX_COUNT;
    dev.inputs = k_inputs;
    dev.input_event_callback = on_input_event;
    if (p->register_device(&dev) != SCS_RESULT_ok) {
        log_line(SCS_LOG_TYPE_error, "input device registration failed");
        return SCS_RESULT_generic_error;
    }
    log_line(SCS_LOG_TYPE_message, "input device registered");
    return SCS_RESULT_ok;
}

SCSAPI_VOID scs_input_shutdown(void) {}

BOOL APIENTRY DllMain(HMODULE, DWORD, LPVOID) { return TRUE; }
