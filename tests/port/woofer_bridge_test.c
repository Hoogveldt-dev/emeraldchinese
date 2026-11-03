/* Host test of port/woofer_bridge.c: scripts/test_port.sh */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "woofer_bridge.h"

static int sFailures;
static char sOut[16][WOOFER_MAX_MESSAGE + 1];
static int sOutCount;
static int64_t sVersion;
static int64_t sFlags;

#define CHECK(cond)                                                     \
    do                                                                  \
    {                                                                   \
        if (!(cond))                                                    \
        {                                                               \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
            sFailures++;                                                \
        }                                                               \
    } while (0)

static int FakeInfo(int64_t *out, uint32_t type, int32_t param)
{
    if (type != WOOFER_INFO_TYPE || sVersion == 0)
        return -1; /* a real 3DS: error */
    *out = param == 0 ? sVersion : param == 1 ? sFlags : 0;
    return 0;
}

static void FakeOutput(const char *text, size_t length)
{
    if (sOutCount < 16 && length <= WOOFER_MAX_MESSAGE)
    {
        memcpy(sOut[sOutCount], text, length);
        sOut[sOutCount][length] = '\0';
        sOutCount++;
    }
}

static void TestNoEmulator(void)
{
    static WooferMsg m;
    sVersion = 0;
    sOutCount = 0;
    CHECK(Woofer_Init("test-zh", "Test", "zh-Hans", "en", "1") == 0);
    CHECK(!Woofer_Active());
    Woofer_Begin(&m, "line");
    CHECK(Woofer_Send(&m) == 0);
    CHECK(Woofer_SendClear() == 0);
    CHECK(Woofer_HostFlags() == 0);
    CHECK(sOutCount == 0);
}

static void TestMessages(void)
{
    static WooferMsg m;
    sVersion = 1;
    sFlags = WOOFER_HOST_PANEL_VISIBLE;
    sOutCount = 0;
    CHECK(Woofer_Init("test-zh", "Test", "zh-Hans", NULL, "1") == 1);
    CHECK(strcmp(sOut[0], "WOOF1 {\"t\":\"hello\",\"game\":\"test-zh\",\"title\":\"Test\","
                          "\"lang\":\"zh-Hans\",\"build\":\"1\"}") == 0);
    CHECK(Woofer_HostFlags() == WOOFER_HOST_PANEL_VISIBLE);

    Woofer_Begin(&m, "line");
    Woofer_Hex64(&m, "h", 0x6b8a1f0c9e2d4a17ULL);
    Woofer_Str(&m, "zh", "\xe4\xbd\xa0\xe5\xa5\xbd"); /* two characters, UTF-8 */
    Woofer_Str(&m, "en", "say \"hi\"\\\n");
    Woofer_ArrayBegin(&m, "w");
    Woofer_ObjectBegin(&m, NULL);
    Woofer_Str(&m, "s", "\xe4\xbd\xa0\xe5\xa5\xbd");
    Woofer_Str(&m, "p", "n\xc7\x90h\xc7\x8eo");
    Woofer_Int(&m, "hsk", 1);
    Woofer_ObjectEnd(&m);
    Woofer_ObjectBegin(&m, NULL);
    Woofer_Str(&m, "s", "!");
    Woofer_ObjectEnd(&m);
    Woofer_ArrayEnd(&m);
    CHECK(Woofer_Send(&m) == 1);
    CHECK(strcmp(sOut[1], "WOOF1 {\"t\":\"line\",\"h\":\"6b8a1f0c9e2d4a17\","
                          "\"zh\":\"\xe4\xbd\xa0\xe5\xa5\xbd\",\"en\":\"say \\\"hi\\\"\\\\\\u000a\","
                          "\"w\":[{\"s\":\"\xe4\xbd\xa0\xe5\xa5\xbd\",\"p\":\"n\xc7\x90h\xc7\x8eo\",\"hsk\":1},"
                          "{\"s\":\"!\"}]}") == 0);

    CHECK(Woofer_SendClear() == 1);
    CHECK(strcmp(sOut[2], "WOOF1 {\"t\":\"clear\"}") == 0);
    CHECK(Woofer_SendSaved("a", "b") == 1);
    CHECK(strcmp(sOut[3], "WOOF1 {\"t\":\"saved\",\"s\":\"a\",\"p\":\"b\"}") == 0);

    /* unbalanced: not sent */
    Woofer_Begin(&m, "line");
    Woofer_ArrayBegin(&m, "w");
    CHECK(Woofer_Send(&m) == 0);
    CHECK(sOutCount == 4);
}

static void TestOverflow(void)
{
    static WooferMsg m;
    static char big[WOOFER_MAX_MESSAGE];
    memset(big, 'x', sizeof(big) - 1);
    big[sizeof(big) - 1] = '\0';
    sOutCount = 0;
    Woofer_Begin(&m, "line");
    Woofer_Str(&m, "en", big);
    CHECK(m.overflow);
    CHECK(Woofer_Send(&m) == 0);
    CHECK(sOutCount == 0);
    /* the same buffer can be used again */
    Woofer_Begin(&m, "clear");
    CHECK(Woofer_Send(&m) == 1);
}

static void TestVocab(const char *dir)
{
    static WooferMsg m;
    char path[256], line[512];
    FILE *f;
    int lines = 0;

    gWooferVocabDir = dir;
    Woofer_BeginVocab(&m);
    Woofer_Str(&m, "s", "\xe4\xbd\xa0");
    Woofer_Str(&m, "status", "new");
    CHECK(Woofer_SaveVocab(&m) == 1);
    Woofer_BeginVocab(&m);
    Woofer_Str(&m, "s", "x");
    CHECK(Woofer_SaveVocab(&m) == 1);

    snprintf(path, sizeof(path), "%s/vocab.jsonl", dir);
    f = fopen(path, "r");
    CHECK(f != NULL);
    if (f == NULL)
        return;
    while (fgets(line, sizeof(line), f) != NULL)
    {
        if (lines == 0)
            CHECK(strcmp(line, "{\"v\":1,\"game\":\"test-zh\",\"s\":\"\xe4\xbd\xa0\",\"status\":\"new\"}\n") == 0);
        lines++;
    }
    fclose(f);
    CHECK(lines == 2);
}

int main(int argc, char **argv)
{
    gWooferSystemInfo = FakeInfo;
    gWooferOutput = FakeOutput;
    TestNoEmulator();
    TestMessages();
    TestOverflow();
    if (argc > 1)
        TestVocab(argv[1]);
    printf(sFailures ? "woofer_bridge: %d failures\n" : "woofer_bridge: ok\n", sFailures);
    return sFailures ? EXIT_FAILURE : EXIT_SUCCESS;
}
