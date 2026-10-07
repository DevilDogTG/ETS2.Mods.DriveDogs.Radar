// DriveDogs Radar - SDK-independent core: camera database, "camera ahead" detection and the
// aux-toggle controller. Kept free of SCS SDK types so it can be unit tested without the game.
#pragma once

#include <cmath>
#include <cstdint>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace ddradar {

struct Camera {
    double x = 0, y = 0, z = 0;  // world position (same space as truck.world.placement)
    std::string model;
};

// Reads data/camera_db.csv as written by tools/extract_camera_db.py:
//   uid,x,y,z,unit,model,sector
inline std::vector<Camera> load_cameras(const std::string &path, std::string *error = nullptr)
{
    std::vector<Camera> out;
    std::ifstream in(path);
    if (!in) {
        if (error) *error = "cannot open " + path;
        return out;
    }
    std::string line;
    std::getline(in, line);  // header
    while (std::getline(in, line)) {
        std::vector<std::string> f;
        std::stringstream ss(line);
        std::string cell;
        while (std::getline(ss, cell, ',')) f.push_back(cell);
        if (f.size() < 6) continue;
        Camera c;
        c.x = std::stod(f[1]);
        c.y = std::stod(f[2]);
        c.z = std::stod(f[3]);
        c.model = f[5];
        out.push_back(c);
    }
    return out;
}

struct DetectorConfig {
    double alert_distance = 350.0;   // [m] start warning when a camera is this close ahead
    double release_distance = 400.0; // [m] hysteresis: keep warning until the camera is this far
    double cone_degrees = 25.0;      // half-angle of the "ahead" cone around the travel direction
    double max_height_delta = 30.0;  // [m] ignore cameras on bridges/roads far above/below
    double min_speed = 2.0;          // [m/s] below this the travel direction is not updated
};

// Decides whether a speed camera is ahead. The travel direction comes from successive positions
// (not the SDK heading convention), so it is robust and identical in tests and in game.
class Detector {
public:
    Detector(std::vector<Camera> cameras, DetectorConfig cfg = {})
        : cameras_(std::move(cameras)), cfg_(cfg) {}

    // Feed the truck position once per frame; returns true while a camera is ahead.
    bool update(double x, double y, double z, double dt)
    {
        if (has_prev_ && dt > 0) {
            double dx = x - px_, dz = z - pz_;
            double dist = std::sqrt(dx * dx + dz * dz);
            if (dist / dt >= cfg_.min_speed) {
                // light smoothing so a single jittery frame cannot flip the direction
                fx_ = 0.7 * fx_ + 0.3 * dx / dist;
                fz_ = 0.7 * fz_ + 0.3 * dz / dist;
                double n = std::sqrt(fx_ * fx_ + fz_ * fz_);
                if (n > 1e-6) { fx_ /= n; fz_ /= n; has_dir_ = true; }
            }
        }
        px_ = x; py_ = y; pz_ = z; has_prev_ = true;
        if (!has_dir_) { alert_ = false; nearest_ = -1; return alert_; }

        const double cos_cone = std::cos(cfg_.cone_degrees * 3.14159265358979 / 180.0);
        const double limit = alert_ ? cfg_.release_distance : cfg_.alert_distance;
        int best = -1;
        double best_d = limit;
        for (size_t i = 0; i < cameras_.size(); ++i) {
            const Camera &c = cameras_[i];
            double vx = c.x - x, vz = c.z - z;
            if (std::fabs(vx) > limit || std::fabs(vz) > limit) continue;
            if (std::fabs(c.y - y) > cfg_.max_height_delta) continue;
            double d = std::sqrt(vx * vx + vz * vz);
            if (d >= best_d || d < 1e-3) continue;
            if ((vx * fx_ + vz * fz_) / d < cos_cone) continue;
            best = static_cast<int>(i);
            best_d = d;
        }
        alert_ = best >= 0;
        nearest_ = best;
        nearest_distance_ = best_d;
        return alert_;
    }

    bool alert() const { return alert_; }
    int nearest() const { return nearest_; }
    double nearest_distance() const { return nearest_distance_; }
    const std::vector<Camera> &cameras() const { return cameras_; }

private:
    std::vector<Camera> cameras_;
    DetectorConfig cfg_;
    bool has_prev_ = false, has_dir_ = false, alert_ = false;
    double px_ = 0, py_ = 0, pz_ = 0, fx_ = 0, fz_ = 0;
    int nearest_ = -1;
    double nearest_distance_ = 0;
};

// Turns "aux should be on/off" into button presses on the game's aux toggle control, using the
// aux state reported by telemetry as feedback. Presses are rate limited so a press always has
// time to show up in telemetry before the next decision.
class AuxController {
public:
    explicit AuxController(double cooldown = 0.6) : cooldown_(cooldown) {}

    // Returns true when a toggle press should be emitted this frame.
    bool update(bool want_on, bool aux_is_on, double dt)
    {
        wait_ -= dt;
        if (want_on == aux_is_on || wait_ > 0) return false;
        wait_ = cooldown_;
        return true;
    }

private:
    double cooldown_;
    double wait_ = 0;
};

}  // namespace ddradar
