/*
 * Bare C++ blinky for the nRF5340 DK.
 *
 * Toggles the board's led0 (devicetree alias) once a second and logs each
 * transition. A minimal starting point for a C++ NCS application.
 */

#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(app, LOG_LEVEL_INF);

namespace {

constexpr k_timeout_t kBlinkInterval = K_MSEC(1000);

// led0 is defined for nrf5340dk in the in-tree board devicetree.
const gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);

}  // namespace

int main()
{
    if (!gpio_is_ready_dt(&led)) {
        LOG_ERR("LED device %s is not ready", led.port->name);
        return -1;
    }

    if (gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE) < 0) {
        LOG_ERR("Failed to configure LED pin");
        return -1;
    }

    LOG_INF("nRF Connect SDK C++ template up; blinking led0");

    bool on = true;
    while (true) {
        gpio_pin_toggle_dt(&led);
        LOG_INF("LED %s", on ? "on" : "off");
        on = !on;
        k_sleep(kBlinkInterval);
    }

    return 0;
}
