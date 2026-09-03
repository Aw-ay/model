#include "calibrator_protocol.h"

#include <string.h>

static uint32_t crc_update(uint32_t crc, const uint8_t *bytes, size_t count)
{
    size_t index;
    for (index = 0; index < count; ++index) {
        unsigned bit;
        crc ^= bytes[index];
        for (bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)-(int32_t)(crc & 1u));
    }
    return crc;
}

uint32_t cal_crc32(const void *header, size_t header_size, const void *payload, size_t payload_size)
{
    uint32_t crc = 0xFFFFFFFFu;
    crc = crc_update(crc, header, header_size);
    crc = crc_update(crc, payload, payload_size);
    return crc ^ 0xFFFFFFFFu;
}

static uint32_t load_u32(const uint8_t *bytes)
{
    uint32_t value;
    memcpy(&value, bytes, sizeof(value));
    return value;
}

static uint64_t load_u64(const uint8_t *bytes)
{
    uint64_t value;
    memcpy(&value, bytes, sizeof(value));
    return value;
}

int cal_dma_event_to_datagram(const uint8_t event[CAL_DMA_EVENT_BYTES], uint64_t sequence,
                              uint8_t datagram[48 + CAL_EVENT_PAYLOAD_BYTES])
{
    struct cal_udp_header header;
    if (load_u32(event) != CAL_DMA_MAGIC || load_u32(event + 4) != CAL_DMA_EVENT_BYTES)
        return -1;
    memset(&header, 0, sizeof(header));
    header.magic = CAL_NET_MAGIC;
    header.version = CAL_PROTOCOL_VERSION;
    header.type = CAL_EVENT_TYPE;
    header.header_len = sizeof(header);
    header.payload_len = CAL_EVENT_PAYLOAD_BYTES;
    header.sequence = sequence;
    header.event_id = load_u32(event + 8);
    header.config_version = load_u32(event + 12);
    header.toa_sample = load_u64(event + 16);
    header.fragment_count = 1;
    memcpy(datagram, &header, sizeof(header));
    memcpy(datagram + sizeof(header), event + CAL_EVENT_PAYLOAD_OFFSET, CAL_EVENT_PAYLOAD_BYTES);
    header.crc32 = cal_crc32(&header, sizeof(header), datagram + sizeof(header), CAL_EVENT_PAYLOAD_BYTES);
    memcpy(datagram, &header, sizeof(header));
    return (int)(sizeof(header) + CAL_EVENT_PAYLOAD_BYTES);
}
