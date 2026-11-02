/*
 * zh_gloss.bin reader and page matcher (format: kit/zh_gloss_bin.py, v2).
 *
 * Game independent: the game gives the text as printed (names filled in,
 * line breaks, control codes) and the page it shows; this finds the words of
 * that page in it, in order. Where a name was filled in, the bytes between
 * two words become a NAME segment; what cannot be matched stays TEXT.
 */
#ifndef WOOFER_GLOSS_H
#define WOOFER_GLOSS_H

#include <stddef.h>
#include <stdint.h>

#define WOOFER_TOKEN_PARA 0xFFFF0000u
#define WOOFER_TOKEN_NAME 0xFFFF0001u
#define WOOFER_TOKEN_CONTROL 0xFFFF0002u
#define WOOFER_EOS 0xFF

enum { WOOFER_SEG_WORD, WOOFER_SEG_NAME, WOOFER_SEG_TEXT };

typedef struct WooferWord
{
    const unsigned char *game;     /* the characters in game bytes, 0xFF-terminated */
    const char *s, *p, *g;         /* UTF-8: characters, pinyin, meaning ("" when none) */
    const unsigned char *pGame;    /* pinyin letters in game bytes, 0xFF-terminated, or NULL */
    const unsigned char *pTones;   /* one tone (0-4) per letter of pGame */
    const unsigned char *gGame;    /* meaning in game bytes, 0xFF-terminated, or NULL */
    unsigned hsk, nChars;
} WooferWord;

typedef struct WooferSeg
{
    uint8_t kind;          /* WOOFER_SEG_* */
    uint32_t word;         /* word index for WOOFER_SEG_WORD */
    uint16_t start, len;   /* bytes of the printed text */
} WooferSeg;

/* The printed text's control codes: bytes taken by the one starting at p,
 * 0 when p is not one. Given by the game (pokeemerald: EXT_CTRL_CODE_BEGIN). */
typedef int (*WooferCtrlLen)(const unsigned char *p);

/* Bytes the game uses in printed text (pokeemerald's charmap). */
typedef struct WooferCharset
{
    unsigned char newline, scroll, clear, space;
    WooferCtrlLen ctrlLen;
} WooferCharset;

/* Takes the file's bytes (kept, not copied). 1 when it is a v2 gloss file. */
int WooferGloss_Use(const unsigned char *data, size_t size);
/* Reads the first of the paths that holds a gloss file. */
int WooferGloss_Load(const char *const *paths, int count);
int WooferGloss_Ready(void);

/* The text with this hash: its first token, token count and place. */
int WooferGloss_Find(uint64_t hash, uint32_t *first, uint32_t *count, const char **loc);
uint32_t WooferGloss_Token(uint32_t index);
int WooferGloss_Word(uint32_t index, WooferWord *out);
/* UTF-8 of a single game byte, or NULL. */
const char *WooferGloss_Decode(unsigned char b);

/* The segments of page `page` (counted by `clear`) of the printed text.
 * Returns the number of segments (at most max), 0 when the text has no words. */
int WooferGloss_MatchPage(uint64_t hash, int page, const unsigned char *printed, const WooferCharset *cs,
                          WooferSeg *segs, int max);

/* Copies the drawable bytes of src[0..len) (no line breaks or control codes)
 * to dst and ends it with 0xFF. Returns the bytes copied. */
size_t WooferGloss_CleanCopy(unsigned char *dst, size_t max, const unsigned char *src, size_t len,
                             const WooferCharset *cs);

/* UTF-8 of game bytes with the decode table (single bytes only); returns length. */
size_t WooferGloss_ToUtf8(char *dst, size_t max, const unsigned char *src, size_t len, const WooferCharset *cs);

#endif
