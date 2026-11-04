/*
 * Stand-ins for the game, so port/woofer_dict.c builds on a host for
 * tools/scan_panel.py. Only the charset is used there.
 */
#include <stdint.h>

unsigned char gStringVar4[1000];
unsigned char gDisplayedStringBattle[1000];

static const unsigned char kCtrl[] = {1, 2, 2, 2, 4, 2, 2, 1, 2, 1, 1, 3, 2, 2, 2, 1, 3, 2, 2, 2, 2, 1, 1, 1, 1};

int16_t CtrText_PrinterPage(uint8_t windowId, const uint8_t *str)
{
    (void)windowId;
    (void)str;
    return -1;
}

uint8_t GetExtCtrlCodeLength(uint8_t code)
{
    return code < sizeof(kCtrl) ? kCtrl[code] : 1;
}

unsigned char *StringExpandPlaceholders(unsigned char *dest, const unsigned char *src)
{
    (void)src;
    *dest = 0xFF;
    return dest;
}

int Cjk_TextKey(const unsigned char *ptr, uint64_t *hash, const unsigned char **english)
{
    (void)ptr;
    (void)hash;
    (void)english;
    return 0;
}
