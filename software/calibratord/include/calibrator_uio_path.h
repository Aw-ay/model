#ifndef CALIBRATOR_UIO_PATH_H
#define CALIBRATOR_UIO_PATH_H

#include <ctype.h>
#include <stdio.h>
#include <string.h>

/* Convert /sys/class/uio/uioN/name into its corresponding /dev/uioN node. */
static inline int cal_uio_device_from_sysfs_name(const char *sysfs_path, char device[32])
{
    const char *name = strrchr(sysfs_path, '/');
    const char *start;
    const char *cursor;
    int written;

    if (name == NULL || strcmp(name, "/name") != 0)
        return -1;
    start = name;
    while (start > sysfs_path && start[-1] != '/')
        --start;
    if ((size_t)(name - start) <= 3 || strncmp(start, "uio", 3) != 0)
        return -1;
    for (cursor = start + 3; cursor < name; ++cursor) {
        if (!isdigit((unsigned char)*cursor))
            return -1;
    }
    written = snprintf(device, 32, "/dev/%.*s", (int)(name - start), start);
    return written > 0 && written < 32 ? 0 : -1;
}

#endif
