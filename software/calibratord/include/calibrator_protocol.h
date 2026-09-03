#pragma once

#include <stddef.h>
#include <stdint.h>

#define CAL_DMA_MAGIC 0x31414D44u
#define CAL_NET_MAGIC 0x314C4143u
#define CAL_PROTOCOL_VERSION 1u
#define CAL_EVENT_TYPE 1u
#define CAL_DMA_EVENT_BYTES 192u
#define CAL_EVENT_PAYLOAD_OFFSET 24u
#define CAL_EVENT_PAYLOAD_BYTES 168u

#if defined(__GNUC__)
#define CAL_PACKED __attribute__((packed))
#else
#define CAL_PACKED
#endif

struct CAL_PACKED cal_udp_header {
    uint32_t magic;
    uint16_t version;
    uint16_t type;
    uint16_t header_len;
    uint16_t flags;
    uint32_t payload_len;
    uint64_t sequence;
    uint32_t event_id;
    uint32_t config_version;
    uint64_t toa_sample;
    uint16_t fragment_index;
    uint16_t fragment_count;
    uint32_t crc32;
};

_Static_assert(sizeof(struct cal_udp_header) == 48, "UDP header must be 48 bytes");

uint32_t cal_crc32(const void *header, size_t header_size, const void *payload, size_t payload_size);
int cal_dma_event_to_datagram(const uint8_t event[CAL_DMA_EVENT_BYTES], uint64_t sequence,
                              uint8_t datagram[48 + CAL_EVENT_PAYLOAD_BYTES]);
