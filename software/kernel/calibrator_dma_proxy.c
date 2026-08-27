// SPDX-License-Identifier: GPL-2.0
/* DMAengine-to-character-device bridge for complete 192-byte calibrator events. */

#include <linux/dmaengine.h>
#include <linux/dma-mapping.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/poll.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include <linux/wait.h>

#define CAL_EVENT_BYTES 192u
#define CAL_RING_SIZE 256u

struct cal_dma_proxy;

struct cal_dma_slot {
    struct cal_dma_proxy *proxy;
    unsigned int index;
    dma_addr_t dma_address;
    void *cpu_address;
};

struct cal_dma_proxy {
    struct device *device;
    struct dma_chan *channel;
    void *ring_cpu;
    dma_addr_t ring_dma;
    struct cal_dma_slot slots[CAL_RING_SIZE];
    unsigned short completed[CAL_RING_SIZE];
    unsigned int completed_head;
    unsigned int completed_tail;
    spinlock_t completion_lock;
    wait_queue_head_t completion_wait;
    struct mutex read_lock;
    atomic_t opened;
    u64 completed_count;
    u64 dropped_count;
    struct miscdevice misc;
};

static int cal_submit_slot(struct cal_dma_slot *slot);

static void cal_dma_complete(void *argument)
{
    struct cal_dma_slot *slot = argument;
    struct cal_dma_proxy *proxy = slot->proxy;
    unsigned long flags;
    unsigned int next;

    spin_lock_irqsave(&proxy->completion_lock, flags);
    next = (proxy->completed_head + 1u) % CAL_RING_SIZE;
    if (next == proxy->completed_tail) {
        ++proxy->dropped_count;
        spin_unlock_irqrestore(&proxy->completion_lock, flags);
        cal_submit_slot(slot);
        dma_async_issue_pending(proxy->channel);
        return;
    }
    proxy->completed[proxy->completed_head] = (unsigned short)slot->index;
    proxy->completed_head = next;
    ++proxy->completed_count;
    spin_unlock_irqrestore(&proxy->completion_lock, flags);
    wake_up_interruptible(&proxy->completion_wait);
}

static int cal_submit_slot(struct cal_dma_slot *slot)
{
    struct dma_async_tx_descriptor *descriptor;
    dma_cookie_t cookie;
    descriptor = dmaengine_prep_slave_single(
        slot->proxy->channel, slot->dma_address, CAL_EVENT_BYTES,
        DMA_DEV_TO_MEM, DMA_PREP_INTERRUPT | DMA_CTRL_ACK);
    if (!descriptor)
        return -EIO;
    descriptor->callback = cal_dma_complete;
    descriptor->callback_param = slot;
    cookie = dmaengine_submit(descriptor);
    return dma_submit_error(cookie);
}

static int cal_open(struct inode *inode, struct file *file)
{
    struct miscdevice *misc = file->private_data;
    struct cal_dma_proxy *proxy = container_of(misc, struct cal_dma_proxy, misc);
    if (atomic_cmpxchg(&proxy->opened, 0, 1) != 0)
        return -EBUSY;
    file->private_data = proxy;
    return nonseekable_open(inode, file);
}

static int cal_release(struct inode *inode, struct file *file)
{
    struct cal_dma_proxy *proxy = file->private_data;
    (void)inode;
    atomic_set(&proxy->opened, 0);
    return 0;
}

static ssize_t cal_read(struct file *file, char __user *target, size_t count, loff_t *position)
{
    struct cal_dma_proxy *proxy = file->private_data;
    struct cal_dma_slot *slot;
    unsigned long flags;
    unsigned int index;
    int status;
    (void)position;
    if (count < CAL_EVENT_BYTES)
        return -EMSGSIZE;
    if (mutex_lock_interruptible(&proxy->read_lock))
        return -ERESTARTSYS;
    if ((file->f_flags & O_NONBLOCK) &&
        READ_ONCE(proxy->completed_head) == READ_ONCE(proxy->completed_tail)) {
        status = -EAGAIN;
        goto unlock;
    }
    status = wait_event_interruptible(proxy->completion_wait,
                                      READ_ONCE(proxy->completed_head) !=
                                      READ_ONCE(proxy->completed_tail));
    if (status)
        goto unlock;
    spin_lock_irqsave(&proxy->completion_lock, flags);
    index = proxy->completed[proxy->completed_tail];
    proxy->completed_tail = (proxy->completed_tail + 1u) % CAL_RING_SIZE;
    spin_unlock_irqrestore(&proxy->completion_lock, flags);
    slot = &proxy->slots[index];
    status = copy_to_user(target, slot->cpu_address, CAL_EVENT_BYTES) ? -EFAULT : CAL_EVENT_BYTES;
    if (cal_submit_slot(slot)) {
        ++proxy->dropped_count;
        if (status >= 0)
            status = -EIO;
    } else {
        dma_async_issue_pending(proxy->channel);
    }
unlock:
    mutex_unlock(&proxy->read_lock);
    return status;
}

static __poll_t cal_poll(struct file *file, struct poll_table_struct *wait)
{
    struct cal_dma_proxy *proxy = file->private_data;
    poll_wait(file, &proxy->completion_wait, wait);
    if (READ_ONCE(proxy->completed_head) != READ_ONCE(proxy->completed_tail))
        return EPOLLIN | EPOLLRDNORM;
    return 0;
}

static const struct file_operations cal_fops = {
    .owner = THIS_MODULE,
    .open = cal_open,
    .release = cal_release,
    .read = cal_read,
    .poll = cal_poll,
    .llseek = noop_llseek,
};

static int cal_probe(struct platform_device *pdev)
{
    struct cal_dma_proxy *proxy;
    struct dma_slave_config configuration = {0};
    unsigned int index;
    int status;

    proxy = devm_kzalloc(&pdev->dev, sizeof(*proxy), GFP_KERNEL);
    if (!proxy)
        return -ENOMEM;
    proxy->device = &pdev->dev;
    spin_lock_init(&proxy->completion_lock);
    init_waitqueue_head(&proxy->completion_wait);
    mutex_init(&proxy->read_lock);
    atomic_set(&proxy->opened, 0);
    proxy->channel = dma_request_chan(&pdev->dev, "rx");
    if (IS_ERR(proxy->channel))
        return dev_err_probe(&pdev->dev, PTR_ERR(proxy->channel), "cannot request RX DMA\n");
    configuration.direction = DMA_DEV_TO_MEM;
    status = dmaengine_slave_config(proxy->channel, &configuration);
    if (status)
        goto release_channel;
    proxy->ring_cpu = dma_alloc_coherent(&pdev->dev, CAL_RING_SIZE * CAL_EVENT_BYTES,
                                         &proxy->ring_dma, GFP_KERNEL);
    if (!proxy->ring_cpu) {
        status = -ENOMEM;
        goto release_channel;
    }
    for (index = 0; index < CAL_RING_SIZE; ++index) {
        proxy->slots[index].proxy = proxy;
        proxy->slots[index].index = index;
        proxy->slots[index].cpu_address =
            (u8 *)proxy->ring_cpu + index * CAL_EVENT_BYTES;
        proxy->slots[index].dma_address = proxy->ring_dma + index * CAL_EVENT_BYTES;
        status = cal_submit_slot(&proxy->slots[index]);
        if (status)
            goto terminate;
    }
    proxy->misc.minor = MISC_DYNAMIC_MINOR;
    proxy->misc.name = "calibrator-events";
    proxy->misc.fops = &cal_fops;
    proxy->misc.parent = &pdev->dev;
    status = misc_register(&proxy->misc);
    if (status)
        goto terminate;
    platform_set_drvdata(pdev, proxy);
    dma_async_issue_pending(proxy->channel);
    dev_info(&pdev->dev, "started %u-entry coherent event ring\n", CAL_RING_SIZE);
    return 0;

terminate:
    dmaengine_terminate_sync(proxy->channel);
    dma_free_coherent(&pdev->dev, CAL_RING_SIZE * CAL_EVENT_BYTES,
                      proxy->ring_cpu, proxy->ring_dma);
release_channel:
    dma_release_channel(proxy->channel);
    return status;
}

static void cal_remove(struct platform_device *pdev)
{
    struct cal_dma_proxy *proxy = platform_get_drvdata(pdev);
    misc_deregister(&proxy->misc);
    dmaengine_terminate_sync(proxy->channel);
    dma_free_coherent(&pdev->dev, CAL_RING_SIZE * CAL_EVENT_BYTES,
                      proxy->ring_cpu, proxy->ring_dma);
    dma_release_channel(proxy->channel);
}

static const struct of_device_id cal_of_match[] = {
    { .compatible = "away,calibrator-dma-proxy-1.0" },
    { }
};
MODULE_DEVICE_TABLE(of, cal_of_match);

static struct platform_driver cal_driver = {
    .probe = cal_probe,
    .remove = cal_remove,
    .driver = {
        .name = "calibrator-dma-proxy",
        .of_match_table = cal_of_match,
    },
};
module_platform_driver(cal_driver);

MODULE_AUTHOR("AWAY calibrator project");
MODULE_DESCRIPTION("Whole-event AXI DMA proxy for the RFSoC calibrator");
MODULE_LICENSE("GPL");
