/*
 * Bare C++ blinky for the nRF5340 DK.
 *
 * Toggles the board's led0 (devicetree alias) once a second and logs each
 * transition. A minimal C++23 starting point — it deliberately uses a little
 * STL (std::array, std::string_view, std::chrono) so the C++ Kconfig options
 * in prj.conf are actually exercised.
 */
#include <array>
#include <chrono>
#include <string_view>

#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#define MODULE app
LOG_MODULE_REGISTER(app, LOG_LEVEL_INF);

using namespace std::chrono_literals;
using namespace std::string_view_literals;

namespace {

constexpr auto BLINK_INTERVAL = 1000ms;

// led0 is defined for nrf5340dk in the in-tree board devicetree.
const gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);

inline void zephyr_sleep_for(std::chrono::milliseconds duration)
{
	k_msleep(duration.count());
}

} // namespace

extern "C" int main(void)
{
	if (!gpio_is_ready_dt(&led)) {
		LOG_ERR("LED device %s is not ready", led.port->name);
		return -1;
	}

	if (gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE) < 0) {
		LOG_ERR("Failed to configure LED pin");
		return -1;
	}

	constexpr std::array<std::string_view, 2> labels{"off"sv, "on"sv};

	LOG_INF("nRF Connect SDK C++ template up; blinking led0");

	size_t state = 1;
	while (true) {
		gpio_pin_toggle_dt(&led);
		LOG_INF("LED %.*s", static_cast<int>(labels[state].size()), labels[state].data());
		state ^= 1U;
		zephyr_sleep_for(BLINK_INTERVAL);
	}

	return 0;
}
