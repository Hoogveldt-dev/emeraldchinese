/*
 * Host test of port/woofer_dict.c with the real kit data and stand-ins for
 * the game: a message with a name and two pages is shown, paged, a word is
 * selected and saved, and the bridge messages are checked.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "woofer_bridge.h"
#include "woofer_dict.h"
#include "woofer_gloss.h"

/* ---- stand-ins for the game ---- */
unsigned char gStringVar4[1000];
unsigned char gDisplayedStringBattle[1000];
static int16_t sPage;
static uint64_t sHash;
static const unsigned char kCtrl[] = {1, 2, 2, 2, 4, 2, 2, 1, 2, 1, 1, 3, 2, 2, 2, 1, 3, 2, 2, 2, 2, 1, 1, 1, 1};

int16_t CtrText_PrinterPage(uint8_t windowId, const uint8_t *str)
{
    (void)windowId;
    (void)str;
    return sPage;
}

uint8_t GetExtCtrlCodeLength(uint8_t code)
{
    return code < sizeof(kCtrl) ? kCtrl[code] : 1;
}

int Cjk_TextKey(const unsigned char *ptr, uint64_t *hash, const unsigned char **english)
{
    *hash = sHash;
    *english = ptr;      /* the test gives the English */
    return 1;
}

/* ---- bridge capture ---- */
static char sOut[8][WOOFER_MAX_MESSAGE + 1];
static int sOutCount;
static int Info(int64_t *out, uint32_t type, int32_t param)
{
    (void)type;
    *out = param == 0 ? 1 : 0;
    return 0;
}
static void Output(const char *text, size_t length)
{
    if (sOutCount < 8)
    {
        memcpy(sOut[sOutCount], text, length);
        sOut[sOutCount++][length] = '\0';
    }
}

static int sFailures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); sFailures++; } } while (0)

int main(int argc, char **argv)
{
    const char *dir = argc > 1 ? argv[1] : "kit";
    const char *tmp = argc > 2 ? argv[2] : "/tmp";
    char path[512], line[2048];
    static unsigned char dlg[1 << 20];
    const char *paths[1];
    FILE *f;
    uint32_t count, blob, i;
    int found = 0, words = 0, isWord = 0, n;
    static const unsigned char english[] = {0xBB, 0xBC, 0x00, 0xFB, 0xBF, 0xFF};   /* "AB" / "E" */

    snprintf(path, sizeof(path), "%s/zh_gloss.bin", dir);
    paths[0] = path;
    if (!WooferGloss_Load(paths, 1))
    {
        printf("woofer_dict: skipped (no kit/zh_gloss.bin)\n");
        return 0;
    }
    snprintf(path, sizeof(path), "%s/zh_dialog.bin", dir);
    f = fopen(path, "rb");
    if (f == NULL || fread(dlg, 1, sizeof(dlg), f) < 16)
        return 0;
    fclose(f);
    memcpy(&count, dlg + 8, 4);
    memcpy(&blob, dlg + 12, 4);
    /* A text with {PLAYER} (FD 01) and a second page (FB). */
    for (i = 0; i < count && !found; i++)
    {
        uint32_t off, len, k, m = 0;
        const unsigned char *t;
        memcpy(&sHash, dlg + 16 + i * 16, 8);
        memcpy(&off, dlg + 24 + i * 16, 4);
        memcpy(&len, dlg + 28 + i * 16, 4);
        t = dlg + blob + off;
        if (!memchr(t, 0xFB, len) || !WooferGloss_Find(sHash, NULL, NULL, NULL))
            continue;
        for (k = 0; k + 1 < len; k++)
            if (t[k] == 0xFD && t[k + 1] == 0x01)
                found = 1;
        if (!found)
            continue;
        for (k = 0; k < len && t[k] != 0xFF && m + 4 < sizeof(gStringVar4); k++)
        {
            if (t[k] == 0xFD)
            {
                gStringVar4[m++] = 0xBB;      /* the player is called "AB" */
                gStringVar4[m++] = 0xBC;
                k++;
                continue;
            }
            gStringVar4[m++] = t[k];
        }
        gStringVar4[m] = 0xFF;
    }
    CHECK(found);

    gWooferSystemInfo = Info;
    gWooferOutput = Output;
    gWooferVocabDir = tmp;
    snprintf(path, sizeof(path), "%s/vocab.jsonl", tmp);
    remove(path);
    CHECK(Woofer_Init("test-zh", NULL, NULL, NULL, NULL) == 1);
    WooferDict_Init();

    sPage = 0;
    WooferDict_OnMessage(english);
    n = WooferDict_SegCount();
    CHECK(n > 0);
    CHECK(WooferDict_Stamp() != 0);
    for (i = 0; i < (uint32_t)n; i++)
        if (WooferDict_Seg((int)i, &isWord) && isWord && words++ == 0)
            WooferDict_Select((int)i);
    CHECK(words > 0);
    CHECK(WooferDict_Selected() >= 0);
    CHECK(sOutCount == 2 && strncmp(sOut[1], "WOOF1 {\"t\":\"line\"", 17) == 0);
    CHECK(strstr(sOut[1], "\"en\":\"AB\"") != NULL);

    CHECK(WooferDict_Save() == 1);
    CHECK(WooferDict_SelectedIsSaved());
    CHECK(WooferDict_Save() == 0);                  /* not twice */
    CHECK(sOutCount == 3 && strstr(sOut[2], "\"t\":\"saved\"") != NULL);
    f = fopen(path, "r");
    CHECK(f != NULL && fgets(line, sizeof(line), f) != NULL);
    if (f != NULL)
        fclose(f);
    CHECK(strncmp(line, "{\"v\":1,\"game\":\"test-zh\",\"s\":\"", 29) == 0);
    CHECK(strstr(line, "\"status\":\"new\"") != NULL);

    WooferDict_ToggleEnglish();
    CHECK(WooferDict_ShowsEnglish());
    sPage = 1;
    WooferDict_Frame();
    CHECK(WooferDict_Selected() == -1);
    CHECK(sOutCount == 4 && strstr(sOut[3], "\"en\":\"E\"") != NULL);

    WooferDict_OnHide();
    CHECK(WooferDict_Stamp() == 0);
    CHECK(sOutCount == 5 && strcmp(sOut[4], "WOOF1 {\"t\":\"clear\"}") == 0);

    /* The next text is reported while the buffer still holds the previous
     * one (a hook before the game fills it), then again once it is filled:
     * the words must be those of the new text, not left over from the old. */
    {
        uint64_t prev = sHash, next = 0;
        uint32_t first = 0, ntok = 0, k;
        static char expect[1024];
        static unsigned char fresh[1000];
        size_t m = 0;
        for (i = 0; i < count && next == 0; i++)
        {
            uint32_t off, len;
            const unsigned char *t;
            uint64_t h;
            memcpy(&h, dlg + 16 + i * 16, 8);
            memcpy(&off, dlg + 24 + i * 16, 4);
            memcpy(&len, dlg + 28 + i * 16, 4);
            t = dlg + blob + off;
            if (h == prev || len < 8 || len >= sizeof(fresh) || memchr(t, 0xFD, len) || memchr(t, 0xFC, len)
             || !WooferGloss_Find(h, &first, &ntok, NULL))
                continue;
            expect[0] = '\0';
            for (k = first; k < first + ntok; k++)
            {
                uint32_t tok = WooferGloss_Token(k);
                WooferWord w;
                if (tok == WOOFER_TOKEN_PARA)
                    break;
                if (tok >= WOOFER_TOKEN_PARA || !WooferGloss_Word(tok, &w))
                {
                    expect[0] = '\0';
                    break;
                }
                strncat(expect, w.s, sizeof(expect) - strlen(expect) - 1);
            }
            if (expect[0] == '\0')
                continue;
            for (m = 0; m < len && t[m] != 0xFF; m++)
                fresh[m] = t[m];
            fresh[m] = 0xFF;
            next = h;
        }
        CHECK(next != 0);
        sHash = next;
        sPage = 0;
        sOutCount = 0;
        WooferDict_OnMessage(english);            /* gStringVar4: still the old text */
        memcpy(gStringVar4, fresh, m + 1);
        WooferDict_OnMessage(english);            /* now filled */
        CHECK(sOutCount >= 1);
        if (sOutCount >= 1)
        {
            char want[1100];
            snprintf(want, sizeof(want), "\"zh\":\"%s\"", expect);
            CHECK(strstr(sOut[sOutCount - 1], want) != NULL);
            if (strstr(sOut[sOutCount - 1], want) == NULL)
                printf("  want %s\n  got  %.300s\n", want, sOut[sOutCount - 1]);
        }
        /* The same text reported again with the same buffer: nothing new. */
        n = sOutCount;
        WooferDict_OnMessage(english);
        CHECK(sOutCount == n);
    }

    printf(sFailures ? "woofer_dict: %d failures\n" : "woofer_dict: ok\n", sFailures);
    if (!sFailures)
        printf("  line: %.160s...\n  saved: %.160s\n", sOut[1], line);
    return sFailures ? 1 : 0;
}
