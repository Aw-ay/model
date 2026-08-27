#define _GNU_SOURCE

#include "calibrator_protocol.h"
#include "calibrator_regs.h"
#include "calibrator_control.h"
#include "calibrator_uio_path.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <metal/device.h>
#include <metal/sys.h>
#include <netinet/in.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/reboot.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <xrfdc.h>

#define CAL_PROJECT_ID 0x43414C31u
#define CAL_ABI_VERSION 0x00010000u
#define CAL_CONTROL_ACQUIRE 0x1u
#define CAL_CONTROL_LOOPBACK 0x2u
#define CAL_CONTROL_MUTE 0x4u
#define CAL_UIO_MAP_BYTES 0x10000u
#define CAL_CONTROL_PORT 47001
#define CAL_DATA_PORT 47000
#define CAL_MAX_LINE 4096u

struct cal_hw {
    int fd;
    volatile uint32_t *registers;
};

struct daemon_state {
    struct cal_hw hw;
    XRFdc rfdc;
    struct metal_device *metal_device;
    int event_fd;
    int udp_fd;
    struct sockaddr_in udp_peer;
    pthread_t event_thread;
    pthread_mutex_t lock;
    volatile sig_atomic_t running;
    bool rfdc_ready;
    bool metal_initialized;
    bool event_thread_started;
    bool mts_ready;
    bool poweroff_requested;
    uint64_t sequence;
    uint64_t software_drops;
};

static struct daemon_state *signal_state;

static uint32_t reg_read(const struct cal_hw *hw, uint32_t offset)
{
    return hw->registers[offset / sizeof(uint32_t)];
}

static void reg_write(struct cal_hw *hw, uint32_t offset, uint32_t value)
{
    hw->registers[offset / sizeof(uint32_t)] = value;
    __sync_synchronize();
}

static uint64_t reg_read64(const struct cal_hw *hw, uint32_t low_offset, uint32_t high_offset)
{
    uint32_t first_high;
    uint32_t low;
    uint32_t second_high;
    do {
        first_high = reg_read(hw, high_offset);
        low = reg_read(hw, low_offset);
        second_high = reg_read(hw, high_offset);
    } while (first_high != second_high);
    return ((uint64_t)second_high << 32) | low;
}

static int find_control_uio(char path[32])
{
    glob_t matches;
    size_t index;
    if (glob("/sys/class/uio/uio*/name", 0, NULL, &matches) != 0)
        return -1;
    for (index = 0; index < matches.gl_pathc; ++index) {
        char name[64] = {0};
        FILE *stream = fopen(matches.gl_pathv[index], "r");
        if (stream == NULL)
            continue;
        if (fgets(name, sizeof(name), stream) == NULL) {
            fclose(stream);
            continue;
        }
        fclose(stream);
        name[strcspn(name, "\r\n")] = '\0';
        if (strcmp(name, "calibrator-control") != 0)
            continue;
        if (cal_uio_device_from_sysfs_name(matches.gl_pathv[index], path) == 0) {
            globfree(&matches);
            return 0;
        }
    }
    globfree(&matches);
    return -1;
}

static int cal_hw_open(struct cal_hw *hw)
{
    char device[32] = {0};
    if (find_control_uio(device) != 0)
        return -1;
    hw->fd = open(device, O_RDWR | O_CLOEXEC);
    if (hw->fd < 0)
        return -1;
    hw->registers = mmap(NULL, CAL_UIO_MAP_BYTES, PROT_READ | PROT_WRITE, MAP_SHARED, hw->fd, 0);
    if (hw->registers == MAP_FAILED) {
        close(hw->fd);
        hw->fd = -1;
        return -1;
    }
    if (reg_read(hw, CAL_PROJECT_ID_OFFSET) != CAL_PROJECT_ID ||
        reg_read(hw, CAL_ABI_VERSION_OFFSET) != CAL_ABI_VERSION) {
        munmap((void *)hw->registers, CAL_UIO_MAP_BYTES);
        close(hw->fd);
        hw->registers = NULL;
        hw->fd = -1;
        errno = EPROTO;
        return -1;
    }
    return 0;
}

static void cal_hw_force_safe(struct cal_hw *hw)
{
    reg_write(hw, CAL_CONTROL_OFFSET, CAL_CONTROL_MUTE);
}

static void cal_hw_close(struct cal_hw *hw)
{
    if (hw->registers != NULL)
        munmap((void *)hw->registers, CAL_UIO_MAP_BYTES);
    if (hw->fd >= 0)
        close(hw->fd);
    hw->registers = NULL;
    hw->fd = -1;
}

static int cal_run_mts(struct daemon_state *state)
{
    XRFdc_MultiConverter_Sync_Config adc;
    XRFdc_MultiConverter_Sync_Config dac;
    u32 adc_status;
    u32 dac_status;
    if (!state->rfdc_ready)
        return -1;
    if (XRFdc_MultiConverter_Init(&dac, NULL, NULL, XRFDC_TILE_ID0) != XRFDC_SUCCESS)
        return -1;
    dac.Tiles = 0x3u;
    dac_status = XRFdc_MultiConverter_Sync(&state->rfdc, XRFDC_DAC_TILE, &dac);
    if (XRFdc_MultiConverter_Init(&adc, NULL, NULL, XRFDC_TILE_ID0) != XRFDC_SUCCESS)
        return -1;
    adc.Tiles = 0xFu;
    adc_status = XRFdc_MultiConverter_Sync(&state->rfdc, XRFDC_ADC_TILE, &adc);
    state->mts_ready = adc_status == XRFDC_MTS_OK && dac_status == XRFDC_MTS_OK;
    return state->mts_ready ? 0 : -1;
}

static int cal_rfdc_initialize(struct daemon_state *state)
{
    struct metal_init_params parameters = METAL_INIT_DEFAULTS;
    XRFdc_Config *configuration;
    XRFdc_IPStatus status;
    unsigned tile;
    if (metal_init(&parameters) != 0)
        return -1;
    state->metal_initialized = true;
    configuration = XRFdc_LookupConfig(0);
    if (configuration == NULL ||
        XRFdc_RegisterMetal(&state->rfdc, 0, &state->metal_device) != XRFDC_SUCCESS ||
        XRFdc_CfgInitialize(&state->rfdc, configuration) != XRFDC_SUCCESS ||
        XRFdc_GetIPStatus(&state->rfdc, &status) != XRFDC_SUCCESS)
        return -1;
    for (tile = 0; tile < 4; ++tile) {
        if (!status.ADCTileStatus[tile].IsEnabled)
            return -1;
    }
    for (tile = 0; tile < 2; ++tile) {
        if (!status.DACTileStatus[tile].IsEnabled)
            return -1;
    }
    state->rfdc_ready = true;
    return cal_run_mts(state);
}

static void *event_worker(void *opaque)
{
    struct daemon_state *state = opaque;
    uint8_t event[CAL_DMA_EVENT_BYTES];
    uint8_t datagram[48 + CAL_EVENT_PAYLOAD_BYTES];
    while (state->running) {
        size_t consumed = 0;
        while (consumed < sizeof(event)) {
            ssize_t count = read(state->event_fd, event + consumed, sizeof(event) - consumed);
            if (count < 0 && errno == EINTR)
                continue;
            if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
                goto retry;
            if (count <= 0)
                goto retry;
            consumed += (size_t)count;
        }
        pthread_mutex_lock(&state->lock);
        {
            int size = cal_dma_event_to_datagram(event, state->sequence++, datagram);
            if (size < 0 || sendto(state->udp_fd, datagram, (size_t)size, 0,
                                   (struct sockaddr *)&state->udp_peer,
                                   sizeof(state->udp_peer)) != size)
                ++state->software_drops;
        }
        pthread_mutex_unlock(&state->lock);
        continue;
retry:
        if (state->running)
            usleep(10000);
    }
    return NULL;
}

static const char *json_command(const char *line, const char *command)
{
    static char pattern[96];
    snprintf(pattern, sizeof(pattern), "\"command\":\"%s\"", command);
    return strstr(line, pattern);
}

static int json_u32(const char *line, const char *name, uint32_t maximum, uint32_t *value)
{
    char pattern[80];
    char *end;
    unsigned long parsed;
    const char *position;
    snprintf(pattern, sizeof(pattern), "\"%s\":", name);
    position = strstr(line, pattern);
    if (position == NULL)
        return -1;
    errno = 0;
    parsed = strtoul(position + strlen(pattern), &end, 0);
    if (errno != 0 || end == position + strlen(pattern) || parsed > maximum)
        return -1;
    *value = (uint32_t)parsed;
    return 0;
}

static int json_i32(const char *line, const char *name, int32_t minimum, int32_t maximum, int32_t *value)
{
    char pattern[80];
    char *end;
    long parsed;
    const char *position;
    snprintf(pattern, sizeof(pattern), "\"%s\":", name);
    position = strstr(line, pattern);
    if (position == NULL)
        return -1;
    errno = 0;
    parsed = strtol(position + strlen(pattern), &end, 0);
    if (errno != 0 || end == position + strlen(pattern) || parsed < minimum || parsed > maximum)
        return -1;
    *value = (int32_t)parsed;
    return 0;
}

static void send_error(int client, const char *message)
{
    dprintf(client, "{\"ok\":false,\"error\":\"%s\"}\n", message);
}

static void send_status(struct daemon_state *state, int client)
{
    uint64_t events = reg_read64(&state->hw, CAL_EVENT_COUNT_LO_OFFSET, CAL_EVENT_COUNT_HI_OFFSET);
    uint64_t drops = reg_read64(&state->hw, CAL_DROP_COUNT_LO_OFFSET, CAL_DROP_COUNT_HI_OFFSET);
    dprintf(client,
            "{\"ok\":true,\"status\":{\"control\":%u,\"rfdc_ready\":%s,"
            "\"mts_ready\":%s,\"config_version\":%u,\"events\":%llu,"
            "\"hardware_drops\":%llu,\"software_drops\":%llu,\"stream_errors\":%u}}\n",
            reg_read(&state->hw, CAL_CONTROL_OFFSET), state->rfdc_ready ? "true" : "false",
            state->mts_ready ? "true" : "false", reg_read(&state->hw, CAL_CONFIG_VERSION_OFFSET),
            (unsigned long long)events, (unsigned long long)drops,
            (unsigned long long)state->software_drops,
            reg_read(&state->hw, CAL_STREAM_ERRORS_OFFSET));
}

static void handle_calibration(struct daemon_state *state, int client, const char *line)
{
    uint32_t channel;
    uint32_t integer_delay;
    uint32_t fractional_delay;
    uint32_t flags;
    int32_t gain_real;
    int32_t gain_imag;
    uint32_t base;
    if (reg_read(&state->hw, CAL_CONTROL_OFFSET) & CAL_CONTROL_ACQUIRE) {
        send_error(client, "acquisition must be stopped");
        return;
    }
    if (json_u32(line, "channel", 7, &channel) ||
        json_u32(line, "integer_delay", 2047, &integer_delay) ||
        json_u32(line, "fractional_delay_q20", 1048575, &fractional_delay) ||
        json_i32(line, "gain_real", -8388608, 8388607, &gain_real) ||
        json_i32(line, "gain_imag", -8388608, 8388607, &gain_imag) ||
        json_u32(line, "flags", 1, &flags)) {
        send_error(client, "invalid calibration fields");
        return;
    }
    base = 0x100u + channel * 0x20u;
    reg_write(&state->hw, base + 0x00u, integer_delay);
    reg_write(&state->hw, base + 0x04u, fractional_delay);
    reg_write(&state->hw, base + 0x08u, (uint32_t)gain_real);
    reg_write(&state->hw, base + 0x0Cu, (uint32_t)gain_imag);
    reg_write(&state->hw, base + 0x10u, flags);
    dprintf(client, "{\"ok\":true}\n");
}

static void handle_request(struct daemon_state *state, int client, const char *line)
{
    uint32_t value;
    if (json_command(line, "get_status")) {
        send_status(state, client);
    } else if (json_command(line, "start")) {
        if (!state->rfdc_ready || !state->mts_ready)
            send_error(client, "RFDC/MTS not ready");
        else {
            reg_write(&state->hw, CAL_CONTROL_OFFSET, CAL_CONTROL_ACQUIRE | CAL_CONTROL_LOOPBACK);
            dprintf(client, "{\"ok\":true}\n");
        }
    } else if (json_command(line, "stop")) {
        cal_hw_force_safe(&state->hw);
        dprintf(client, "{\"ok\":true}\n");
    } else if (json_command(line, "set_threshold")) {
        if (json_u32(line, "threshold", UINT32_MAX, &value))
            send_error(client, "invalid threshold");
        else {
            reg_write(&state->hw, CAL_DETECT_THRESHOLD_OFFSET, value);
            dprintf(client, "{\"ok\":true}\n");
        }
    } else if (json_command(line, "set_calibration")) {
        handle_calibration(state, client, line);
    } else if (json_command(line, "commit_calibration")) {
        if (reg_read(&state->hw, CAL_CONTROL_OFFSET) & CAL_CONTROL_ACQUIRE)
            send_error(client, "acquisition must be stopped");
        else {
            reg_write(&state->hw, CAL_COMMIT_CALIBRATION_OFFSET, 1);
            dprintf(client, "{\"ok\":true,\"config_version\":%u}\n",
                    reg_read(&state->hw, CAL_CONFIG_VERSION_OFFSET));
        }
    } else if (json_command(line, "run_mts")) {
        cal_hw_force_safe(&state->hw);
        if (cal_run_mts(state))
            send_error(client, "MTS failed");
        else
            dprintf(client, "{\"ok\":true}\n");
    } else if (json_command(line, "clear_errors")) {
        reg_write(&state->hw, CAL_STREAM_ERRORS_OFFSET, UINT32_MAX);
        dprintf(client, "{\"ok\":true}\n");
    } else if (json_command(line, "shutdown")) {
        cal_hw_force_safe(&state->hw);
        state->poweroff_requested = cal_poweroff_allowed(getenv("CALIBRATOR_ALLOW_POWEROFF"));
        state->running = 0;
        dprintf(client, "{\"ok\":true}\n");
    } else {
        send_error(client, "unknown command");
    }
}

static int create_control_listener(void)
{
    struct sockaddr_in address;
    int enabled = 1;
    int listener = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (listener < 0)
        return -1;
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &enabled, sizeof(enabled));
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons(CAL_CONTROL_PORT);
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) || listen(listener, 8)) {
        close(listener);
        return -1;
    }
    return listener;
}

static int read_request_line(int client, char line[CAL_MAX_LINE])
{
    struct cal_json_line_reader reader = {0};
    char chunk[512];
    for (;;) {
        ssize_t count = read(client, chunk, sizeof(chunk));
        int status;
        if (count < 0 && errno == EINTR)
            continue;
        if (count < 0)
            return -4;
        if (count == 0)
            return cal_json_line_eof(&reader);
        status = cal_json_line_append(&reader, line, CAL_MAX_LINE, chunk, (size_t)count);
        if (status != CAL_JSON_LINE_INCOMPLETE)
            return status;
    }
}

static void on_signal(int signal_number)
{
    (void)signal_number;
    if (signal_state != NULL)
        signal_state->running = 0;
}

static int configure_udp(struct daemon_state *state)
{
    const char *host = getenv("CALIBRATOR_UDP_HOST");
    if (host == NULL)
        host = "192.168.1.100";
    state->udp_fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    memset(&state->udp_peer, 0, sizeof(state->udp_peer));
    state->udp_peer.sin_family = AF_INET;
    state->udp_peer.sin_port = htons(CAL_DATA_PORT);
    return state->udp_fd >= 0 && inet_pton(AF_INET, host, &state->udp_peer.sin_addr) == 1 ? 0 : -1;
}

int main(void)
{
    struct daemon_state state;
    int listener = -1;
    memset(&state, 0, sizeof(state));
    state.hw.fd = -1;
    state.event_fd = -1;
    state.udp_fd = -1;
    state.running = 1;
    pthread_mutex_init(&state.lock, NULL);
    signal_state = &state;
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);

    if (cal_hw_open(&state.hw) != 0)
        goto fail;
    cal_hw_force_safe(&state.hw);
    if (cal_rfdc_initialize(&state) != 0)
        goto fail;
    if (configure_udp(&state) != 0)
        goto fail;
    state.event_fd = open("/dev/calibrator-events", O_RDONLY | O_CLOEXEC | O_NONBLOCK);
    if (state.event_fd < 0 || pthread_create(&state.event_thread, NULL, event_worker, &state) != 0)
        goto fail;
    state.event_thread_started = true;
    listener = create_control_listener();
    if (listener < 0)
        goto fail;

    while (state.running) {
        char line[CAL_MAX_LINE];
        struct pollfd ready = { .fd = listener, .events = POLLIN };
        ssize_t count;
        int poll_status = poll(&ready, 1, 250);
        if (poll_status < 0) {
            if (errno == EINTR)
                continue;
            goto fail;
        }
        if (poll_status == 0)
            continue;
        int client = accept4(listener, NULL, NULL, SOCK_CLOEXEC);
        if (client < 0) {
            if (errno == EINTR)
                continue;
            goto fail;
        }
        count = read_request_line(client, line);
        if (count == CAL_JSON_LINE_TOO_LONG)
            send_error(client, "request line exceeds 4095 bytes");
        else if (count == CAL_JSON_LINE_MISSING_NEWLINE)
            send_error(client, "request must be newline terminated");
        else if (count == CAL_JSON_LINE_EXTRA_DATA)
            send_error(client, "request must contain one JSON line");
        else if (count != CAL_JSON_LINE_COMPLETE)
            send_error(client, "request read failed");
        else {
            handle_request(&state, client, line);
        }
        close(client);
    }

    cal_hw_force_safe(&state.hw);
    if (listener >= 0)
        close(listener);
    if (state.event_thread_started)
        pthread_join(state.event_thread, NULL);
    if (state.event_fd >= 0)
        close(state.event_fd);
    if (state.udp_fd >= 0)
        close(state.udp_fd);
    cal_hw_close(&state.hw);
    if (state.metal_initialized)
        metal_finish();
    pthread_mutex_destroy(&state.lock);
    if (state.poweroff_requested) {
        sync();
        reboot(RB_POWER_OFF);
    }
    return 0;

fail:
    if (state.hw.registers != NULL)
        cal_hw_force_safe(&state.hw);
    perror("calibratord");
    state.running = 0;
    if (listener >= 0)
        close(listener);
    if (state.event_thread_started)
        pthread_join(state.event_thread, NULL);
    if (state.event_fd >= 0)
        close(state.event_fd);
    if (state.udp_fd >= 0)
        close(state.udp_fd);
    cal_hw_close(&state.hw);
    if (state.metal_initialized)
        metal_finish();
    pthread_mutex_destroy(&state.lock);
    return 1;
}
