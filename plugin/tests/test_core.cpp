// Unit tests for radar_core.hpp (no SCS SDK needed). Build + run: plugin\build.ps1 -Test
#include "../src/radar_core.hpp"

#include <cstdio>
#include <cstdlib>

using namespace ddradar;

static int failures = 0;
#define CHECK(cond)                                                          \
    do {                                                                     \
        if (!(cond)) { std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond); ++failures; } \
    } while (0)

// Drive in a straight line at `speed` m/s from (x0,z0) along (dx,dz); return frames with alert on.
static int drive(Detector &d, double x0, double z0, double dx, double dz, double meters, double speed = 20)
{
    const double dt = 1.0 / 60;
    double n = std::sqrt(dx * dx + dz * dz);
    dx /= n; dz /= n;
    int on = 0;
    for (double s = 0; s <= meters; s += speed * dt)
        on += d.update(x0 + dx * s, 0, z0 + dz * s, dt) ? 1 : 0;
    return on;
}

static void test_ahead_and_behind()
{
    Detector d({{0, 0, -1000, "cam"}});
    // approach from z=0 heading -Z: camera ahead at 1000 m -> alert only in the last ~350 m
    Detector a = d;
    for (int i = 0; i <= 60 * 30; ++i) a.update(0, 0, -20.0 * i / 60, 1.0 / 60);  // 600 m driven
    CHECK(!a.alert());                                                        // 400 m left
    for (int i = 0; i <= 60 * 5; ++i) a.update(0, 0, -600 - 20.0 * i / 60, 1.0 / 60);  // 700 m
    CHECK(a.alert());
    CHECK(a.nearest() == 0);
    // driving away (+Z) from the camera never alerts
    Detector b = d;
    CHECK(drive(b, 0, -900, 0, 1, 900) == 0);
}

static void test_cone_and_height()
{
    // camera 100 m ahead but 60 m to the side -> outside a 25 deg cone
    Detector side({{60, 0, -100, "side"}});
    CHECK(drive(side, 0, 0, 0, -1, 50) == 0);
    // camera straight ahead but 40 m higher (bridge) -> ignored
    Detector bridge({{0, 40, -200, "bridge"}});
    CHECK(drive(bridge, 0, 0, 0, -1, 150) == 0);
}

static void test_release_after_pass()
{
    Detector d({{0, 0, -300, "cam"}});
    drive(d, 0, 0, 0, -1, 280);
    CHECK(d.alert());
    drive(d, 0, -280, 0, -1, 60);  // now 40 m past it
    CHECK(!d.alert());
}

static void test_stationary_has_no_direction()
{
    Detector d({{0, 0, -100, "cam"}});
    for (int i = 0; i < 120; ++i) d.update(0, 0, 0, 1.0 / 60);
    CHECK(!d.alert());
}

static void test_aux_controller()
{
    AuxController c(0.5);
    CHECK(c.update(true, false, 0.016));    // needs on, is off -> press
    CHECK(!c.update(true, false, 0.016));   // cooldown: telemetry not updated yet
    for (int i = 0; i < 40; ++i) c.update(true, true, 0.016);
    CHECK(!c.update(true, true, 0.016));    // in sync -> nothing
    CHECK(c.update(false, true, 0.6));      // needs off -> press
}

static void test_load_db(const char *path)
{
    std::string err;
    auto cams = load_cameras(path, &err);
    if (!err.empty()) { std::printf("skip db test: %s\n", err.c_str()); return; }
    CHECK(cams.size() > 500);
    int berlin = 0;
    for (auto &c : cams)
        if (c.x > 8500 && c.x < 13500 && c.z > -11500 && c.z < -8000) ++berlin;
    CHECK(berlin >= 20);
    std::printf("db: %zu cameras, %d in Berlin area\n", cams.size(), berlin);
}

int main(int argc, char **argv)
{
    test_ahead_and_behind();
    test_cone_and_height();
    test_release_after_pass();
    test_stationary_has_no_direction();
    test_aux_controller();
    test_load_db(argc > 1 ? argv[1] : "../data/camera_db.csv");
    std::printf(failures ? "%d FAILED\n" : "all tests passed\n", failures);
    return failures ? EXIT_FAILURE : EXIT_SUCCESS;
}
