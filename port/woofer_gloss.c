/*
 * zh_gloss.bin reader and page matcher. See woofer_gloss.h and
 * kit/zh_gloss_bin.py. Nothing in this file is specific to one game.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "woofer_gloss.h"

#define HEADER_SIZE 48
#define TEXT_SIZE 24
#define WORD_SIZE 28

static const unsigned char *sData;
static size_t sSize;
static uint32_t sTexts, sOffTexts, sWords, sOffWords, sTokens, sOffTokens, sPoolSize, sOffPool, sOffDecode;

static uint32_t U32(size_t off)
{
    uint32_t v;
    memcpy(&v, sData + off, 4);
    return v;
}

static uint64_t U64(size_t off)
{
    uint64_t v;
    memcpy(&v, sData + off, 8);
    return v;
}

static int Fits(uint32_t off, uint64_t count, uint32_t size)
{
    return (uint64_t)off + count * size <= sSize;
}

int WooferGloss_Use(const unsigned char *data, size_t size)
{
    sData = data;
    sSize = size;
    if (data == NULL || size < HEADER_SIZE || memcmp(data, "ZHGLS\0\2\0", 8) != 0)
        goto bad;
    sTexts = U32(8);
    sOffTexts = U32(12);
    sWords = U32(16);
    sOffWords = U32(20);
    sTokens = U32(24);
    sOffTokens = U32(28);
    sPoolSize = U32(32);
    sOffPool = U32(36);
    sOffDecode = U32(40);
    if (!Fits(sOffTexts, sTexts, TEXT_SIZE) || !Fits(sOffWords, sWords, WORD_SIZE) || !Fits(sOffTokens, sTokens, 4)
     || !Fits(sOffDecode, 256, 4) || !Fits(sOffPool, sPoolSize, 1) || sPoolSize == 0)
        goto bad;
    return 1;
bad:
    sData = NULL;
    sSize = 0;
    sTexts = 0;
    return 0;
}

int WooferGloss_Load(const char *const *paths, int count)
{
    int i;
    for (i = 0; i < count; i++)
    {
        FILE *f = fopen(paths[i], "rb");
        long size;
        unsigned char *data;
        if (f == NULL)
            continue;
        fseek(f, 0, SEEK_END);
        size = ftell(f);
        fseek(f, 0, SEEK_SET);
        data = size > 0 ? malloc((size_t)size) : NULL;
        if (data != NULL && fread(data, 1, (size_t)size, f) == (size_t)size && WooferGloss_Use(data, (size_t)size))
        {
            fclose(f);
            return 1;
        }
        free(data);
        fclose(f);
    }
    return 0;
}

int WooferGloss_Ready(void)
{
    return sData != NULL;
}

/* A pool string at off, checked to end inside the pool; NULL when not. */
static const unsigned char *Pool(uint32_t off, unsigned char end)
{
    const unsigned char *p;
    if (off == 0 || off >= sPoolSize)
        return NULL;
    p = memchr(sData + sOffPool + off, end, sPoolSize - off);
    return p != NULL ? sData + sOffPool + off : NULL;
}

static const char *Utf8(uint32_t off)
{
    const unsigned char *p = Pool(off, 0);
    return p != NULL ? (const char *)p : "";
}

int WooferGloss_Find(uint64_t hash, uint32_t *first, uint32_t *count, const char **loc)
{
    uint32_t lo = 0, hi = sTexts;
    while (lo < hi)
    {
        uint32_t mid = lo + (hi - lo) / 2;
        size_t at = sOffTexts + (size_t)mid * TEXT_SIZE;
        uint64_t h = U64(at);
        if (h == hash)
        {
            uint32_t f = U32(at + 8), n = U32(at + 12);
            if ((uint64_t)f + n > sTokens)
                return 0;
            if (first != NULL)
                *first = f;
            if (count != NULL)
                *count = n;
            if (loc != NULL)
                *loc = Utf8(U32(at + 16));
            return 1;
        }
        if (h < hash)
            lo = mid + 1;
        else
            hi = mid;
    }
    return 0;
}

uint32_t WooferGloss_Token(uint32_t index)
{
    return index < sTokens ? U32(sOffTokens + (size_t)index * 4) : WOOFER_TOKEN_CONTROL;
}

int WooferGloss_Word(uint32_t index, WooferWord *out)
{
    size_t at;
    if (index >= sWords)
        return 0;
    at = sOffWords + (size_t)index * WORD_SIZE;
    out->game = Pool(U32(at), WOOFER_EOS);
    out->s = Utf8(U32(at + 4));
    out->p = Utf8(U32(at + 8));
    out->g = Utf8(U32(at + 12));
    out->pGame = Pool(U32(at + 16), WOOFER_EOS);
    out->pTones = NULL;
    if (out->pGame != NULL)
    {
        size_t n = (size_t)((const unsigned char *)memchr(out->pGame, WOOFER_EOS, sPoolSize) - out->pGame);
        out->pTones = out->pGame + n + 1;
        if (out->pTones + n > sData + sOffPool + sPoolSize)
            out->pGame = out->pTones = NULL;
    }
    out->gGame = Pool(U32(at + 20), WOOFER_EOS);
    out->hsk = sData[at + 24];
    out->nChars = sData[at + 25];
    return out->game != NULL;
}

const char *WooferGloss_Decode(unsigned char b)
{
    const unsigned char *p;
    if (sData == NULL)
        return NULL;
    p = Pool(U32(sOffDecode + (size_t)b * 4), 0);
    return p != NULL ? (const char *)p : NULL;
}

/* ------------------------------------------------------------------------ */
/* Matching                                                                 */
/* ------------------------------------------------------------------------ */

/* Bytes at t[i] that are not part of the visible text: 0 when visible. */
static int Skip(const unsigned char *t, size_t i, size_t end, const WooferCharset *cs)
{
    int n;
    unsigned char c = t[i];
    if (c == cs->newline || c == cs->scroll || c == cs->space)
        return 1;
    n = cs->ctrlLen != NULL ? cs->ctrlLen(t + i) : 0;
    if (n > 0)
        return (size_t)n <= end - i ? n : (int)(end - i);
    return 0;
}

static size_t SkipAll(const unsigned char *t, size_t i, size_t end, const WooferCharset *cs)
{
    int n;
    while (i < end && (n = Skip(t, i, end, cs)) > 0)
        i += (size_t)n;
    return i;
}

/* Bytes of t from i that spell word (invisible bytes in between allowed); 0 if not. */
static size_t MatchAt(const unsigned char *t, size_t i, size_t end, const unsigned char *word,
                      const WooferCharset *cs)
{
    size_t start = i;
    for (; *word != WOOFER_EOS; word++)
    {
        if (i > start)
            i = SkipAll(t, i, end, cs);
        if (i >= end || t[i] != *word)
            return 0;
        i++;
    }
    return i - start;
}

static int AddSeg(WooferSeg *segs, int n, int max, uint8_t kind, uint32_t word, size_t start, size_t end)
{
    if (n >= max || end <= start)
        return n;
    segs[n].kind = kind;
    segs[n].word = word;
    segs[n].start = (uint16_t)start;
    segs[n].len = (uint16_t)(end - start);
    return n + 1;
}

/* The text between two words: a name if one was due, else unmatched text. */
static int AddGap(WooferSeg *segs, int n, int max, int name, const unsigned char *t, size_t a, size_t b,
                  const WooferCharset *cs)
{
    a = SkipAll(t, a, b, cs);
    while (b > a && Skip(t, b - 1, b, cs) == 1)
        b--;
    return AddSeg(segs, n, max, name ? WOOFER_SEG_NAME : WOOFER_SEG_TEXT, 0, a, b);
}

int WooferGloss_MatchPage(uint64_t hash, int page, const unsigned char *printed, const WooferCharset *cs,
                          WooferSeg *segs, int max)
{
    uint32_t first, count, k, end;
    size_t ps = 0, pe, pos, len;
    int p, n = 0, nameDue = 0, words = 0;

    if (sData == NULL || printed == NULL || page < 0 || !WooferGloss_Find(hash, &first, &count, NULL))
        return 0;
    /* The page's bytes: after `page` clears, up to the next clear or EOS. */
    for (len = 0; len < 0xFFFF && printed[len] != WOOFER_EOS; len++)
        ;
    for (p = 0; p < page; p++)
    {
        while (ps < len && printed[ps] != cs->clear)
            ps += (size_t)(Skip(printed, ps, len, cs) > 1 ? Skip(printed, ps, len, cs) : 1);
        if (ps >= len)
            return 0;
        ps++;
    }
    pe = ps;
    while (pe < len && printed[pe] != cs->clear)
        pe += (size_t)(Skip(printed, pe, len, cs) > 1 ? Skip(printed, pe, len, cs) : 1);
    if (pe > len)
        pe = len;
    /* The page's tokens: after `page` paragraph marks. */
    end = first + count;
    for (k = first, p = 0; k < end && p < page; k++)
        if (WooferGloss_Token(k) == WOOFER_TOKEN_PARA)
            p++;
    if (p < page)
        return 0;

    pos = ps;
    for (; k < end; k++)
    {
        uint32_t t = WooferGloss_Token(k);
        WooferWord w;
        size_t at, m = 0;

        if (t == WOOFER_TOKEN_PARA)
            break;
        if (t == WOOFER_TOKEN_NAME)
        {
            nameDue = 1;
            continue;
        }
        if (t == WOOFER_TOKEN_CONTROL || !WooferGloss_Word(t, &w))
            continue;
        /* Where the word is: right here, or (after a name or text the game
         * changed) further on. */
        at = SkipAll(printed, pos, pe, cs);
        if (!nameDue)
            m = MatchAt(printed, at, pe, w.game, cs);
        if (m == 0)
        {
            for (at = pos; at < pe; at++)
                if ((m = MatchAt(printed, at, pe, w.game, cs)) > 0)
                    break;
            if (m == 0)
                continue;       /* not on this page: left out */
        }
        n = AddGap(segs, n, max, nameDue, printed, pos, at, cs);
        nameDue = 0;
        n = AddSeg(segs, n, max, WOOFER_SEG_WORD, t, at, at + m);
        words++;
        pos = at + m;
    }
    n = AddGap(segs, n, max, nameDue, printed, pos, pe, cs);
    return words > 0 ? n : 0;
}

size_t WooferGloss_CleanCopy(unsigned char *dst, size_t max, const unsigned char *src, size_t len,
                             const WooferCharset *cs)
{
    size_t i = 0, n = 0;
    if (max == 0)
        return 0;
    while (i < len && n + 1 < max)
    {
        int skip = Skip(src, i, len, cs);
        if (skip > 0 && src[i] != cs->space)
        {
            i += (size_t)skip;
            continue;
        }
        if (src[i] == cs->clear || src[i] == WOOFER_EOS)
            break;
        dst[n++] = src[i++];
    }
    dst[n] = WOOFER_EOS;
    return n;
}

size_t WooferGloss_ToUtf8(char *dst, size_t max, const unsigned char *src, size_t len, const WooferCharset *cs)
{
    size_t i = 0, n = 0;
    if (max == 0)
        return 0;
    while (i < len && src[i] != WOOFER_EOS && src[i] != cs->clear)
    {
        const char *u;
        int skip = Skip(src, i, len, cs);
        if (skip > 0)
        {
            if ((src[i] == cs->space || src[i] == cs->newline || src[i] == cs->scroll) && n + 2 < max
             && (n == 0 || dst[n - 1] != ' '))
                dst[n++] = ' ';
            i += (size_t)skip;
            continue;
        }
        u = WooferGloss_Decode(src[i]);
        if (u != NULL && n + strlen(u) + 1 < max)
        {
            memcpy(dst + n, u, strlen(u));
            n += strlen(u);
        }
        i++;
    }
    while (n > 0 && dst[n - 1] == ' ')
        n--;
    dst[n] = '\0';
    return n;
}
