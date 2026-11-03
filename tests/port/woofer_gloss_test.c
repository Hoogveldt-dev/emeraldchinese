/*
 * Host test of port/woofer_gloss.c on the real data: every text of
 * kit/zh_dialog.bin, with names filled in as the game does, page by page
 * against kit/zh_gloss.bin. Run: scripts/test_port.sh (needs the two kit .bin files from
 * `translate_dialogue.py build`; skipped without them).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "woofer_gloss.h"

/* pokeemerald's GetExtCtrlCodeLength, plus the 0xFC itself. */
static const unsigned char kCtrl[] = {1, 2, 2, 2, 4, 2, 2, 1, 2, 1, 1, 3, 2, 2, 2, 1, 3, 2, 2, 2, 2, 1, 1, 1, 1};

static int CtrlLen(const unsigned char *p)
{
    if (p[0] != 0xFC)
        return 0;
    return 1 + (p[1] < sizeof(kCtrl) ? kCtrl[p[1]] : 1);
}

static const WooferCharset kCharset = {0xFE, 0xFA, 0xFB, 0x00, CtrlLen};

static unsigned char *ReadFile(const char *path, size_t *size)
{
    FILE *f = fopen(path, "rb");
    unsigned char *data;
    long n;
    if (f == NULL)
        return NULL;
    fseek(f, 0, SEEK_END);
    n = ftell(f);
    fseek(f, 0, SEEK_SET);
    data = malloc((size_t)n);
    if (data == NULL || fread(data, 1, (size_t)n, f) != (size_t)n)
    {
        fclose(f);
        free(data);
        return NULL;
    }
    fclose(f);
    *size = (size_t)n;
    return data;
}

/* The text as printed: placeholders FD xx become a name, "ABE" in game letters. */
static size_t Expand(unsigned char *dst, const unsigned char *src, size_t len)
{
    size_t i, n = 0;
    for (i = 0; i < len && src[i] != 0xFF; i++)
    {
        if (src[i] == 0xFD)
        {
            dst[n++] = 0xBB;
            dst[n++] = 0xBC;
            dst[n++] = 0xBF;
            i++;
            continue;
        }
        dst[n++] = src[i];
    }
    dst[n] = 0xFF;
    return n;
}

static int SameGame(const unsigned char *a, const unsigned char *b)
{
    while (*a == *b && *a != 0xFF)
    {
        a++;
        b++;
    }
    return *a == *b;
}

static int Pages(const unsigned char *t, size_t len)
{
    size_t i = 0;
    int pages = 1;
    while (i < len)
    {
        int c = CtrlLen(t + i);
        if (c)
        {
            i += (size_t)c;
            continue;
        }
        if (t[i] == 0xFB && i + 1 < len)
            pages++;
        i++;
    }
    return pages;
}

int main(int argc, char **argv)
{
    const char *dir = argc > 1 ? argv[1] : "kit";
    char path[512];
    size_t dsize, gsize;
    unsigned char *dlg, *gloss;
    uint32_t count, blob, i;
    long pages = 0, matched = 0, words = 0, missed = 0, texts = 0;
    static WooferSeg segs[256];
    static unsigned char printed[8192], clean[2048];
    char utf8[4096];

    snprintf(path, sizeof(path), "%s/zh_dialog.bin", dir);
    dlg = ReadFile(path, &dsize);
    snprintf(path, sizeof(path), "%s/zh_gloss.bin", dir);
    gloss = ReadFile(path, &gsize);
    if (dlg == NULL || gloss == NULL)
    {
        printf("woofer_gloss: skipped (no kit/zh_dialog.bin or kit/zh_gloss.bin)\n");
        return 0;
    }
    if (!WooferGloss_Use(gloss, gsize))
    {
        printf("FAIL: zh_gloss.bin not accepted\n");
        return 1;
    }
    memcpy(&count, dlg + 8, 4);
    memcpy(&blob, dlg + 12, 4);
    for (i = 0; i < count; i++)
    {
        uint64_t hash;
        uint32_t off, len, first, ntok, k;
        size_t plen;
        int page, np, expectWords = 0;

        memcpy(&hash, dlg + 16 + i * 16, 8);
        memcpy(&off, dlg + 16 + i * 16 + 8, 4);
        memcpy(&len, dlg + 16 + i * 16 + 12, 4);
        if (!WooferGloss_Find(hash, &first, &ntok, NULL))
            continue;
        texts++;
        plen = Expand(printed, dlg + blob + off, len);
        np = Pages(printed, plen);
        for (k = first; k < first + ntok; k++)
        {
            uint32_t t = WooferGloss_Token(k);
            if (t < WOOFER_TOKEN_PARA)
                expectWords++;
        }
        for (page = 0; page < np; page++)
        {
            int n = WooferGloss_MatchPage(hash, page, printed, &kCharset, segs, 256), s, got = 0, ok = 1;
            pages++;
            for (s = 0; s < n; s++)
            {
                if (segs[s].kind == WOOFER_SEG_WORD)
                {
                    WooferWord w;
                    got++;
                    WooferGloss_Word(segs[s].word, &w);
                    WooferGloss_CleanCopy(clean, sizeof(clean), printed + segs[s].start, segs[s].len, &kCharset);
                    if (!SameGame(clean, w.game))
                        ok = 0;
                }
                else if (segs[s].kind == WOOFER_SEG_TEXT)
                    ok = 0;
                if (s > 0 && segs[s].start < segs[s - 1].start + segs[s - 1].len)
                    ok = 0;
            }
            words += got;
            matched += ok && got > 0;
        }
        (void)expectWords;
    }
    /* One page in UTF-8, to see the decode table work. */
    WooferGloss_ToUtf8(utf8, sizeof(utf8), (const unsigned char *)"\xBB\xBC\xBF\x00\xD5", 5, &kCharset);
    if (strcmp(utf8, "ABE a") != 0)
    {
        printf("FAIL: decode gave '%s'\n", utf8);
        missed++;
    }
    /* Every word back to UTF-8 from its game bytes: two-byte characters
     * through the wide table. This is what the panel gets for a name or for
     * text that is not a word. */
    {
        uint32_t w, bad = 0, n = 0;
        WooferWord word;
        for (w = 0; WooferGloss_Word(w, &word) || w < 1; w++)
        {
            size_t len = 0;
            while (word.game[len] != 0xFF)
                len++;
            WooferGloss_ToUtf8(utf8, sizeof(utf8), word.game, len, &kCharset);
            n++;
            if (strcmp(utf8, word.s) != 0 && bad++ < 5)
                printf("FAIL: word %u decodes to '%s', not '%s'\n", w, utf8, word.s);
        }
        if (bad || n < 100)
        {
            printf("FAIL: %u of %u words do not decode\n", bad, n);
            missed++;
        }
    }
    printf("woofer_gloss: %ld texts, %ld pages, %ld fully matched (%.1f%%), %ld words\n", texts, pages, matched,
           pages ? 100.0 * matched / pages : 0.0, words);
    free(dlg);
    free(gloss);
    return (missed || pages == 0 || matched * 100 < pages * 90) ? 1 : 0;
}
