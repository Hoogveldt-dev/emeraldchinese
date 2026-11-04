/*
 * The dictionary in the game (phase 2 of docs/PLAN-woordenboek.md): which
 * text and page the message box shows, its words from zh_gloss.bin, the word
 * the player tapped, saving it, and the bridge messages for WooferCitra.
 *
 * Called from the field message box (patch 9110) and the bottom screen
 * (patch 0120). The drawing itself is in 3ds_bottom_ui.c.
 */
#ifndef WOOFER_DICT_H
#define WOOFER_DICT_H

#include <stdint.h>

#include "woofer_gloss.h"

void WooferDict_Init(void);
/* The bytes the game uses in printed text (for host tools and tests). */
const WooferCharset *WooferDict_Charset(void);
/* A field message starts (src: the text passed to the message box) or ends. */
/* A text the game is about to show; see woofer_dict.c. */
void WooferDict_OnText(const unsigned char *src, const unsigned char *printed, unsigned char window);
void WooferDict_OnMessage(const unsigned char *src);
void WooferDict_OnBattle(const unsigned char *src);
void WooferDict_OnPrint(unsigned char window, const unsigned char *str);
void WooferDict_OnHide(void);
/* Once a frame: follows the page the message box prints. */
void WooferDict_Frame(void);

/* Changes whenever what the panel shows changes; 0 when there is no panel. */
uint32_t WooferDict_Stamp(void);

int WooferDict_SegCount(void);
/* The segment's drawable game bytes (0xFF-terminated); *isWord when tappable. */
const unsigned char *WooferDict_Seg(int i, int *isWord);
int WooferDict_Selected(void);                  /* segment index, -1 when none */
int WooferDict_SelectedWord(WooferWord *out);
void WooferDict_Select(int seg);

int WooferDict_ShowsEnglish(void);
void WooferDict_ToggleEnglish(void);
/* The English of the page (game bytes, 0xFF-terminated), or NULL. */
const unsigned char *WooferDict_EnglishPage(void);

/* Saves the selected word to sdmc:/woofer/vocab.jsonl. 1 when saved. */
int WooferDict_Save(void);
int WooferDict_SelectedIsSaved(void);

#endif
