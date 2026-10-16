/*
 * C++23 blinky: toggles led0 once a second and logs each transition. Uses a little of
 * the STL so the C++ options in prj.conf are exercised by a real build.
 */
#include <array>
#include <chrono>
#include <cstddef>
#include <string_view>

#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(app, LOG_LEVEL_INF);

using namespace std::chrono_literals;
using namespace std::string_view_literals;

namespace
{

constexpr auto BLINK_INTERVAL = 1000ms;

const gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);

void sleep_for(std::chrono::milliseconds duration)
{
    k_msleep(static_cast<int32_t>(duration.count()));
}

} // namespace

int main()
{
    if (!gpio_is_ready_dt(&led)) {
        LOG_ERR("LED device %s is not ready", led.port->name);
        return -1;
    }

    /* Starts off, so the first toggle turns it on and matches the first label logged. */
    if (gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE) < 0) {
        LOG_ERR("Failed to configure LED pin");
        return -1;
    }

    constexpr std::array<std::string_view, 2> labels{"off"sv, "on"sv};

    LOG_INF("Zephyr C++ template up, blinking led0");

    std::size_t state = 1;
    while (true) {
        gpio_pin_toggle_dt(&led);
        LOG_INF("LED %.*s", static_cast<int>(labels[state].size()), labels[state].data());
        state ^= 1U;
        sleep_for(BLINK_INTERVAL);
    }

    return 0;
}
