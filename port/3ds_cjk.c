/*
 * Chinese build: the dialogue table.
 *
 * sdmc:/3ds/emerald3ds/zh_dialog.bin (made by tools/zh/translate_dialogue.py)
 * maps a text of the game, by the FNV-1a 64 hash of its bytes up to and
 * including EOS, to its translation in the game's encoding (CJK characters as
 * lead/trail byte pairs, see 3ds_cjk_font.c). Every text the game copies,
 * expands, measures or prints passes through Port_ResolveTextPointer, which
 * asks Cjk_TextOverride: a text with an entry is replaced by its translation,
 * anything else passes through unchanged. No file, no change.
 *
 * Layout (little endian): "ZHDLG\0\1\0", u32 count, u32 blob offset, then
 * count entries {u64 hash, u32 offset, u32 length} sorted by hash, then the
 * blob of EOS-terminated texts.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "3ds_log.h"
#define PORT_LOG(...) CtrLog_Write(CTR_LOG_FS, __VA_ARGS__)

#define CJK_EOS 0xFF
#define CJK_MAX_TEXT 4096

struct CjkEntry
{
    uint64_t hash;
    uint32_t offset;
    uint32_t length;
};

static unsigned char *sFile;
static size_t sFileSize;
static const struct CjkEntry *sEntries;
static uint32_t sCount;
static const unsigned char *sBlob;
static size_t sBlobSize;

static const char *const sPaths[] = {
    "sdmc:/3ds/emerald3ds/zh_dialog.bin",
    "romfs:/zh_dialog.bin",
};

void Cjk_Init(void)
{
    size_t i;
    if (sFile != NULL)
        return;
    for (i = 0; i < sizeof(sPaths) / sizeof(sPaths[0]); i++)
    {
        FILE *f = fopen(sPaths[i], "rb");
        long size;
        unsigned char *data;
        uint32_t count, blob;
        if (f == NULL)
            continue;
        fseek(f, 0, SEEK_END);
        size = ftell(f);
        fseek(f, 0, SEEK_SET);
        if (size < 16)
        {
            fclose(f);
            continue;
        }
        data = malloc((size_t)size);
        if (data == NULL || fread(data, 1, (size_t)size, f) != (size_t)size)
        {
            free(data);
            fclose(f);
            continue;
        }
        fclose(f);
        memcpy(&count, data + 8, 4);
        memcpy(&blob, data + 12, 4);
        if (memcmp(data, "ZHDLG\0\1\0", 8) != 0 || blob > (uint32_t)size
         || (uint64_t)16 + (uint64_t)count * sizeof(struct CjkEntry) > blob)
        {
            PORT_LOG("cjk: %s is not a dialogue table", sPaths[i]);
            free(data);
            continue;
        }
        sFile = data;
        sFileSize = (size_t)size;
        sEntries = (const struct CjkEntry *)(data + 16);
        sCount = count;
        sBlob = data + blob;
        sBlobSize = (size_t)size - blob;
        PORT_LOG("cjk: %u dialogue texts from %s", (unsigned)count, sPaths[i]);
        return;
    }
}

const unsigned char *Cjk_TextOverride(const unsigned char *ptr)
{
    uint64_t hash = 0xcbf29ce484222325ULL;
    uint32_t lo, hi;
    size_t n;

    if (sCount == 0 || ptr == NULL)
        return ptr;
    if (ptr >= sBlob && ptr < sBlob + sBlobSize)
        return ptr;
    for (n = 0; n < CJK_MAX_TEXT; n++)
    {
        hash ^= ptr[n];
        hash *= 0x100000001b3ULL;
        if (ptr[n] == CJK_EOS)
            break;
    }
    if (n == CJK_MAX_TEXT || n < 2)
        return ptr;
    lo = 0;
    hi = sCount;
    while (lo < hi)
    {
        uint32_t mid = lo + (hi - lo) / 2;
        uint64_t h = sEntries[mid].hash;
        if (h == hash)
        {
            if (sEntries[mid].offset < sBlobSize)
                return sBlob + sEntries[mid].offset;
            return ptr;
        }
        if (h < hash)
            lo = mid + 1;
        else
            hi = mid;
    }
    return ptr;
}

/* ------------------------------------------------------------------------ */
/* CJK glyphs for the port's own text drawing (bottom screen, battle HUD)    */
/* ------------------------------------------------------------------------ */
extern const unsigned char gCjkLeadIndex[256];
extern const unsigned short gCjkGlyphs[][12];
extern const unsigned int gCjkGlyphCount;

int Cjk_IsLead(unsigned char c)
{
    return gCjkLeadIndex[c] != 0xFF;
}

/* The glyph index of a lead/trail pair, -1 if there is none. */
int Cjk_Index(unsigned char lead, unsigned char trail)
{
    unsigned index;

    if (gCjkLeadIndex[lead] == 0xFF || trail < 1 || trail > 246)
        return -1;
    index = gCjkLeadIndex[lead] * 246u + (trail - 1u);
    return index < gCjkGlyphCount ? (int)index : -1;
}

static int CjkPix(const unsigned short *rows, int x, int y)
{
    if (x < 0 || x >= 12 || y < 0 || y >= 12)
        return 0;
    return (rows[y] >> (11 - x)) & 1;
}

/* One 8-pixel half of a glyph row in the game's 2bpp layout (1 ink, 2 shadow),
 * as the Latin glyphs' rows are read by the port's text drawing. */
unsigned short Cjk_GlyphBits(unsigned index, int row, int half)
{
    const unsigned short *rows;
    unsigned short bits = 0;
    int k;

    if (index >= gCjkGlyphCount)
        return 0;
    rows = gCjkGlyphs[index];
    for (k = 0; k < 8; k++)
    {
        int x = half * 8 + k;
        unsigned v = CjkPix(rows, x, row) ? 1
                   : (CjkPix(rows, x - 1, row) || CjkPix(rows, x, row - 1) || CjkPix(rows, x - 1, row - 1)) ? 2 : 0;
        if (k < 4)
            bits |= v << (8 + 6 - 2 * k);
        else
            bits |= v << (6 - 2 * (k - 4));
    }
    return bits;
}
