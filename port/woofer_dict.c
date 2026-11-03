/*
 * The dictionary in the game. See woofer_dict.h.
 *
 * Game glue for Pokémon Emerald 3DS. A text has two sides: the source the
 * game looked up (its hash comes from Cjk_TextKey, 3ds_cjk.c) and the buffer
 * that is printed, with names filled in. For a field message those are the
 * script text and gStringVar4, in a battle the battle string and
 * gDisplayedStringBattle, and for a menu or a description both are the same
 * pointer. The page being shown comes from CtrText_PrinterPage (text.c).
 * The rest is game independent.
 */
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "woofer_bridge.h"
#include "woofer_dict.h"
#include "woofer_gloss.h"

/* The game (declared here with plain types; the port's own files do not
 * include pokeemerald's headers). */
extern unsigned char gStringVar4[];
extern unsigned char gDisplayedStringBattle[];
int16_t CtrText_PrinterPage(uint8_t windowId, const uint8_t *str);
uint8_t GetExtCtrlCodeLength(uint8_t code);
int Cjk_TextKey(const unsigned char *ptr, uint64_t *hash, const unsigned char **english);

#define MAX_SEGS 96
#define SEG_BYTES 64
#define MAX_SAVED 128

static const char *const sPaths[] = {
    "sdmc:/3ds/emerald3ds/zh_gloss.bin",
    "romfs:/zh_gloss.bin",
};

static int CtrlLen(const unsigned char *p)
{
    if (p[0] == 0xFC)            /* EXT_CTRL_CODE_BEGIN */
        return p[1] == 0xFF ? 1 : 1 + GetExtCtrlCodeLength(p[1]);
    if (p[0] == 0xFD)            /* PLACEHOLDER_BEGIN (in English not yet filled in) */
        return p[1] == 0xFF ? 1 : 2;
    return 0;
}

static const WooferCharset sCharset = {0xFE, 0xFA, 0xFB, 0x00, CtrlLen};

static struct
{
    int active;                   /* a text with words is up */
    const unsigned char *printed; /* the buffer being printed */
    unsigned char window;         /* its text printer */
    uint64_t hash;
    uint32_t sum;                 /* of the printed bytes when matched */
    const unsigned char *english;
    const char *loc;
    int page;
    int count;
    WooferSeg segs[MAX_SEGS];
    unsigned char text[MAX_SEGS][SEG_BYTES];
    unsigned char englishPage[512];
    int selected;
    int showEnglish;
    uint32_t stamp;
} sDict;

static uint32_t sSaved[MAX_SAVED];
static int sSavedCount;

void WooferDict_Init(void)
{
    if (!WooferGloss_Ready())
        WooferGloss_Load(sPaths, (int)(sizeof(sPaths) / sizeof(sPaths[0])));
}

static void Changed(void)
{
    if (++sDict.stamp == 0)
        sDict.stamp = 1;
}

/* The English of page `page`, without line breaks, for the panel. */
static void EnglishPage(void)
{
    const unsigned char *p = sDict.english;
    size_t n = 0;
    int page = 0;

    sDict.englishPage[0] = WOOFER_EOS;
    if (p == NULL)
        return;
    while (*p != WOOFER_EOS && page < sDict.page)
    {
        int c = CtrlLen(p);
        if (c > 0)
        {
            p += c;
            continue;
        }
        if (*p == sCharset.clear)
            page++;
        p++;
    }
    while (*p != WOOFER_EOS && *p != sCharset.clear && n + 1 < sizeof(sDict.englishPage))
    {
        int c = CtrlLen(p);
        if (c > 0)
        {
            p += c;
            continue;
        }
        /* a line break of the box becomes a space; the panel wraps itself */
        sDict.englishPage[n++] = (*p == sCharset.newline || *p == sCharset.scroll) ? sCharset.space : *p;
        p++;
    }
    sDict.englishPage[n] = WOOFER_EOS;
}

/* "line" for WooferCitra (docs/woofer-bridge/PROTOCOL.md). */
static void SendLine(void)
{
    static WooferMsg msg;
    static char zh[1024], en[1024], part[256];
    int i, withEnglish, withMeaning;

    if (!Woofer_Active() || sDict.count == 0)
        return;
    zh[0] = '\0';
    for (i = 0; i < sDict.count; i++)
    {
        const WooferSeg *s = &sDict.segs[i];
        WooferWord w;
        if (s->kind == WOOFER_SEG_WORD && WooferGloss_Word(s->word, &w))
            strncat(zh, w.s, sizeof(zh) - strlen(zh) - 1);
        else
        {
            WooferGloss_ToUtf8(part, sizeof(part), sDict.printed + s->start, s->len, &sCharset);
            strncat(zh, part, sizeof(zh) - strlen(zh) - 1);
        }
    }
    WooferGloss_ToUtf8(en, sizeof(en), sDict.englishPage, sizeof(sDict.englishPage), &sCharset);
    /* Too long for one message: without the English, then without meanings. */
    for (withEnglish = 1, withMeaning = 1;; withEnglish ? (withEnglish = 0) : (withMeaning = 0))
    {
        Woofer_Begin(&msg, "line");
        Woofer_Hex64(&msg, "h", sDict.hash);
        Woofer_Str(&msg, "zh", zh);
        if (withEnglish && en[0])
            Woofer_Str(&msg, "en", en);
        if (sDict.loc != NULL && sDict.loc[0])
            Woofer_Str(&msg, "loc", sDict.loc);
        Woofer_ArrayBegin(&msg, "w");
        for (i = 0; i < sDict.count; i++)
        {
            const WooferSeg *s = &sDict.segs[i];
            WooferWord w;
            Woofer_ObjectBegin(&msg, NULL);
            if (s->kind == WOOFER_SEG_WORD && WooferGloss_Word(s->word, &w))
            {
                Woofer_Str(&msg, "s", w.s);
                if (w.p[0])
                {
                    Woofer_Str(&msg, "p", w.p);
                    if (withMeaning)
                        Woofer_Str(&msg, "g", w.g);
                    if (w.hsk)
                        Woofer_Int(&msg, "hsk", (long)w.hsk);
                }
            }
            else
            {
                WooferGloss_ToUtf8(part, sizeof(part), sDict.printed + s->start, s->len, &sCharset);
                Woofer_Str(&msg, "s", part);
            }
            Woofer_ObjectEnd(&msg);
        }
        Woofer_ArrayEnd(&msg);
        if (Woofer_Send(&msg) || !withMeaning)
            break;
    }
}

/* FNV-1a of the printed text up to its end, to see that a buffer changed. */
static uint32_t Sum(const unsigned char *p)
{
    uint32_t h = 2166136261u;
    size_t n;
    for (n = 0; n < 0x400 && p[n] != WOOFER_EOS; n++)
        h = (h ^ p[n]) * 16777619u;
    return h;
}

static void Rematch(void)
{
    int i;

    sDict.sum = Sum(sDict.printed);
    sDict.count = WooferGloss_MatchPage(sDict.hash, sDict.page, sDict.printed, &sCharset, sDict.segs, MAX_SEGS);
    for (i = 0; i < sDict.count; i++)
        WooferGloss_CleanCopy(sDict.text[i], SEG_BYTES, sDict.printed + sDict.segs[i].start, sDict.segs[i].len,
                              &sCharset);
    sDict.selected = -1;
    EnglishPage();
    Changed();
    SendLine();
}

/*
 * A text the game is about to show.
 * @param src      what the game looked up: gives the hash and the English
 * @param printed  the buffer that is printed (names filled in); may be src
 * @param window   the text printer that prints it
 */
void WooferDict_OnText(const unsigned char *src, const unsigned char *printed, unsigned char window)
{
    uint64_t hash;
    const unsigned char *english;

    if (src == NULL || printed == NULL || !WooferGloss_Ready() || !Cjk_TextKey(src, &hash, &english)
     || !WooferGloss_Find(hash, NULL, NULL, &sDict.loc))
        return;             /* no words for this text: keep what is up */
    /* The same text reported twice (a source hook and the printer both do):
     * stay on the page we are on. Only when the buffer still holds what was
     * matched: a hook that runs before the game fills the buffer would
     * otherwise leave the words of the previous text up. */
    if (sDict.active && sDict.hash == hash && sDict.printed == printed && sDict.page >= 0
     && sDict.sum == Sum(printed))
        return;
    sDict.active = 1;
    sDict.count = 0;
    sDict.printed = printed;
    sDict.window = window;
    sDict.hash = hash;
    /* For a text that is printed as it is, the "English" is the text itself. */
    sDict.english = english == src && src == printed ? NULL : english;
    sDict.page = -1;
    sDict.showEnglish = 0;
    WooferDict_Frame();
}

/* A field message: the script text, printed from gStringVar4 by printer 0. */
void WooferDict_OnMessage(const unsigned char *src)
{
    if (src == NULL)
    {
        WooferDict_OnHide();
        return;
    }
    WooferDict_OnText(src, gStringVar4, 0);
}

/* A battle message: the battle string, printed from gDisplayedStringBattle. */
void WooferDict_OnBattle(const unsigned char *src)
{
    WooferDict_OnText(src, gDisplayedStringBattle, 0);
}

/* Any other text printer: a menu, a description, a list. The text is printed
 * as it is, so it is its own source. The two buffers above have their own
 * hooks, which know the text the game started from. */
void WooferDict_OnPrint(unsigned char window, const unsigned char *str)
{
    if (str == gStringVar4 || str == gDisplayedStringBattle)
        return;
    WooferDict_OnText(str, str, window);
}

void WooferDict_OnHide(void)
{
    if (sDict.active || sDict.count)
    {
        sDict.active = 0;
        sDict.count = 0;
        Changed();
    }
    Woofer_SendClear();
}

void WooferDict_Frame(void)
{
    int page;

    if (!sDict.active)
        return;
    page = CtrText_PrinterPage(sDict.window, sDict.printed);
    if (page < 0 && sDict.page < 0)
        page = 0;           /* not printing yet: the first page */
    if (page >= 0 && page != sDict.page)
    {
        sDict.page = page;
        Rematch();
    }
}

uint32_t WooferDict_Stamp(void)
{
    return sDict.active && sDict.count > 0 ? sDict.stamp : 0;
}

int WooferDict_SegCount(void)
{
    return sDict.active ? sDict.count : 0;
}

const unsigned char *WooferDict_Seg(int i, int *isWord)
{
    WooferWord w;
    if (i < 0 || i >= sDict.count)
        return NULL;
    *isWord = sDict.segs[i].kind == WOOFER_SEG_WORD && WooferGloss_Word(sDict.segs[i].word, &w) && w.p[0];
    return sDict.text[i];
}

int WooferDict_Selected(void)
{
    return sDict.selected;
}

int WooferDict_SelectedWord(WooferWord *out)
{
    if (sDict.selected < 0 || sDict.selected >= sDict.count)
        return 0;
    return WooferGloss_Word(sDict.segs[sDict.selected].word, out);
}

void WooferDict_Select(int seg)
{
    int isWord = 0;
    if (seg == sDict.selected || WooferDict_Seg(seg, &isWord) == NULL || !isWord)
        return;
    sDict.selected = seg;
    sDict.showEnglish = 0;
    Changed();
}

int WooferDict_ShowsEnglish(void)
{
    return sDict.showEnglish && sDict.englishPage[0] != WOOFER_EOS;
}

void WooferDict_ToggleEnglish(void)
{
    sDict.showEnglish = !sDict.showEnglish;
    Changed();
}

const unsigned char *WooferDict_EnglishPage(void)
{
    return sDict.englishPage[0] != WOOFER_EOS ? sDict.englishPage : NULL;
}

int WooferDict_SelectedIsSaved(void)
{
    int i;
    if (sDict.selected < 0)
        return 0;
    for (i = 0; i < sSavedCount; i++)
        if (sSaved[i] == sDict.segs[sDict.selected].word)
            return 1;
    return 0;
}

int WooferDict_Save(void)
{
    static WooferMsg msg;
    static char zh[1024], en[1024], part[256], at[24];
    WooferWord w;
    time_t now = time(NULL);
    struct tm *t = gmtime(&now);
    int i;

    if (!WooferDict_SelectedWord(&w) || WooferDict_SelectedIsSaved())
        return 0;
    zh[0] = '\0';
    for (i = 0; i < sDict.count; i++)
    {
        WooferWord sw;
        if (sDict.segs[i].kind == WOOFER_SEG_WORD && WooferGloss_Word(sDict.segs[i].word, &sw))
            strncat(zh, sw.s, sizeof(zh) - strlen(zh) - 1);
        else
        {
            WooferGloss_ToUtf8(part, sizeof(part), sDict.printed + sDict.segs[i].start, sDict.segs[i].len, &sCharset);
            strncat(zh, part, sizeof(zh) - strlen(zh) - 1);
        }
    }
    WooferGloss_ToUtf8(en, sizeof(en), sDict.englishPage, sizeof(sDict.englishPage), &sCharset);
    Woofer_BeginVocab(&msg);
    Woofer_Str(&msg, "s", w.s);
    Woofer_Str(&msg, "p", w.p);
    Woofer_Str(&msg, "g", w.g);
    Woofer_Str(&msg, "zh", zh);
    if (en[0])
        Woofer_Str(&msg, "en", en);
    if (sDict.loc != NULL && sDict.loc[0])
        Woofer_Str(&msg, "loc", sDict.loc);
    if (t != NULL && strftime(at, sizeof(at), "%Y-%m-%dT%H:%M:%SZ", t) > 0)
        Woofer_Str(&msg, "at", at);
    Woofer_Str(&msg, "status", "new");
    if (!Woofer_SaveVocab(&msg))
        return 0;
    if (sSavedCount < MAX_SAVED)
        sSaved[sSavedCount++] = sDict.segs[sDict.selected].word;
    Woofer_SendSaved(w.s, w.p);
    Changed();
    return 1;
}
