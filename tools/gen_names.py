#!/usr/bin/env python3
"""Official Simplified Chinese names (PokeAPI CSV, language 12 = zh-Hans) as catalogs."""
import csv, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lp

TREE = Path(sys.argv[1]); CSV = Path(sys.argv[2]); OUT = Path(sys.argv[3])
ZH = "12"
table = set(json.loads((OUT.parent / "out/cjk_table.json").read_text())["chars"]) if (OUT.parent / "out/cjk_table.json").exists() else None


def rows(name):
    with open(CSV / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def names(kind, idcol, extra=None):
    ident = {r["id"]: r["identifier"] for r in rows(kind + ".csv")}
    out = {}
    single = {"moves": "move", "abilities": "ability", "types": "type", "natures": "nature",
              "items": "item", "locations": "location"}[kind]
    for r in rows(single + "_names.csv"):
        if r["local_language_id"] == ZH:
            out[ident[r[idcol]]] = r["name"]
    return out


FW = str.maketrans({c: chr(ord(c) - 0xFEE0) for c in "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"})


def clean(s):
    s = s.replace("　", "").replace(" ", "").translate(FW)
    return s.replace("·", "・") if table and "·" not in table else s


def size(s):
    return sum(2 if ord(c) > 0x2000 else 1 for c in s)


def write(rel, header, entries, limit, missing_log):
    texts = lp.c_texts((TREE / rel).read_text(encoding="utf-8"))
    out = ["# " + h for h in header] + [""]
    n = 0
    for label, zh in entries:
        if label not in texts:
            continue
        zh = clean(zh)
        if limit and size(zh) > limit:
            missing_log.append("%s %s too long: %s" % (rel, label, zh))
            continue
        out.append("[%s] %s" % (label, lp.text_hash(texts[label][2])))
        out.append(zh)
        out.append("")
        n += 1
    p = OUT / (rel + ".txt"); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(out), encoding="utf-8")
    print("%-45s %d" % (rel, n))


def key(const, prefix):
    return const[len(prefix):].lower().replace("_", "-")


log = []
# Species
sp = {}
ident = {r["id"]: r["identifier"] for r in rows("pokemon_species.csv")}
genus = {}
for r in rows("pokemon_species_names.csv"):
    if r["local_language_id"] == ZH:
        sp[ident[r["pokemon_species_id"]]] = r["name"]
        genus[ident[r["pokemon_species_id"]]] = r["genus"]
src = (TREE / "src/data/text/species_names.h").read_text()
consts = re.findall(r"\[(SPECIES_\w+)\]\s*=", src)
fix = {"nidoran-f": "nidoran-f", "nidoran-m": "nidoran-m", "mr-mime": "mr-mime", "ho-oh": "ho-oh"}
ent = []
for c in consts:
    k = key(c, "SPECIES_")
    if c == "SPECIES_EGG":
        ent.append((c, "蛋")); continue
    if k.startswith("unown") or k.startswith("old-unown"):
        k = "unown"
    if k in sp:
        ent.append((c, sp[k]))
    elif not k.startswith("old-unown") and c != "SPECIES_NONE":
        log.append("species miss " + c)
write("src/data/text/species_names.h", ["Officiële namen (zh-Hans), PokeAPI pokemon_species_names.csv"], ent, 10, log)

# Pokédex categories: the genus without 宝可梦
src = (TREE / "src/data/pokemon/pokedex_entries.h").read_text()
ent = []
for c in re.findall(r"\[(NATIONAL_DEX_\w+)\]\s*=", src):
    k = key(c, "NATIONAL_DEX_")
    if k in genus and genus[k]:
        g = genus[k]
        g = g[:-3] if g.endswith("宝可梦") else g
        ent.append((c, g))
write("src/data/pokemon/pokedex_entries.h", ["Categorie (genus zonder 宝可梦), PokeAPI"], ent, 11, log)

# Moves
mv = names("moves", "move_id")
alias = {"vice-grip": "vise-grip", "hi-jump-kick": "high-jump-kick", "faint-attack": "feint-attack",
         "smelling-salt": "smelling-salts", "sonic-boom": "sonic-boom", "selfdestruct": "self-destruct",
         "softboiled": "soft-boiled", "dynamicpunch": "dynamic-punch", "doubleslap": "double-slap",
         "thunderpunch": "thunder-punch", "solarbeam": "solar-beam", "thundershock": "thunder-shock",
         "poisonpowder": "poison-powder", "smokescreen": "smokescreen", "extremespeed": "extreme-speed",
         "ancientpower": "ancient-power", "bubblebeam": "bubble-beam", "dragonbreath": "dragon-breath",
         "featherdance": "feather-dance", "grasswhistle": "grass-whistle", "conversion-2": "conversion-2"}
src = (TREE / "src/data/text/move_names.h").read_text()
ent = []
for c in re.findall(r"\[(MOVE_\w+)\]\s*=", src):
    k = key(c, "MOVE_"); k = alias.get(k, k)
    if k in mv: ent.append((c, mv[k]))
    elif c != "MOVE_NONE": log.append("move miss " + c)
write("src/data/text/move_names.h", ["Officiële namen, PokeAPI move_names.csv"], ent, 12, log)

# Abilities
ab = names("abilities", "ability_id")
src = (TREE / "src/data/text/abilities.h").read_text()
ent = []
for c in sorted(set(re.findall(r"\[(ABILITY_\w+)\]\s*=", src))):
    k = key(c, "ABILITY_")
    k = {"compoundeyes": "compound-eyes", "lightningrod": "lightning-rod"}.get(k, k)
    if k in ab: ent.append((c, ab[k]))
    elif c != "ABILITY_NONE": log.append("ability miss " + c)
write("src/data/text/abilities.h", ["Officiële namen, PokeAPI ability_names.csv"], ent, 12, log)

# Types
ty = names("types", "type_id")
src = (TREE / "src/battle_main.c").read_text()
ent = [(c, ty[key(c, "TYPE_")]) for c in re.findall(r"\[(TYPE_\w+)\]\s*=\s*_\(", src) if key(c, "TYPE_") in ty]
ent += [("TYPE_MYSTERY", "？？？")]
write("src/battle_main.c", ["Types, PokeAPI type_names.csv"], ent, 6, log)

# Natures
na = names("natures", "nature_id")
src = (TREE / "src/data/text/nature_names.h").read_text()
ent = []
for lab in re.findall(r"(s(\w+?)NatureName)\[\]", src):
    k = lab[1].lower()
    if k in na: ent.append((lab[0], na[k]))
write("src/data/text/nature_names.h", ["Naturen, PokeAPI nature_names.csv"], ent, None, log)

# Items
it = names("items", "item_id")
src = (TREE / "src/data/items.h").read_text()
ialias = {"poke-ball": "poke-ball", "parlyz-heal": "paralyze-heal", "ppup": "pp-up", "pp-max": "pp-max",
          "tinymushroom": "tiny-mushroom", "x-defend": "x-defense", "x-special": "x-sp-atk",
          "thunderstone": "thunder-stone", "blackglasses": "black-glasses", "silverpowder": "silver-powder",
          "twistedspoon": "twisted-spoon", "deepseatooth": "deep-sea-tooth", "deepseascale": "deep-sea-scale",
          "nevermeltice": "never-melt-ice", "brightpowder": "bright-powder", "kings-rock": "kings-rock",
          "devon-goods": "devon-parts", "s-s-ticket": "ss-ticket", "eon-ticket": "eon-ticket",
          "oaks-parcel": "oaks-parcel", "energypowder": "energy-powder", "up-grade": "up-grade",
          "rm-1-key": "room-1-key", "rm-2-key": "room-2-key", "rm-4-key": "room-4-key", "rm-6-key": "room-6-key",
          "scanner": "scanner", "go-goggles": "go-goggles", "letter": "letter", "devon-scope": "devon-scope",
          "contest-pass": "contest-pass", "wailmer-pail": "wailmer-pail", "soot-sack": "soot-sack",
          "basement-key": "basement-key", "acro-bike": "acro-bike", "mach-bike": "mach-bike",
          "pokeblock-case": "pokeblock-case", "storage-key": "storage-key", "root-fossil": "root-fossil",
          "claw-fossil": "claw-fossil", "magma-emblem": "magma-emblem", "old-sea-map": "old-sea-map",
          "mystic-ticket": "mystic-ticket", "aurora-ticket": "aurora-ticket", "powder-jar": "powder-jar",
          "ruby": "ruby", "sapphire": "sapphire", "lava-cookie": "lava-cookie", "berry-juice": "berry-juice",
          "sacred-ash": "sacred-ash", "big-mushroom": "big-mushroom", "fluffy-tail": "fluffy-tail",
          "red-flute": "red-flute", "yellow-flute": "yellow-flute"}
ent = []
for c in re.findall(r"\[(ITEM_\w+)\]\s*=\s*\{", src):
    k = key(c, "ITEM_")
    m = re.fullmatch(r"(tm|hm)(\d+)(-.*)?", k)
    if m:
        k = m.group(1) + m.group(2)
    k = ialias.get(k, k)
    if k in it: ent.append((c, it[k]))
    elif c != "ITEM_NONE" and not c.startswith("ITEM_UNUSED") and "_034" not in c: log.append("item miss " + c)
write("src/data/items.h", ["Officiële namen, PokeAPI item_names.csv"], ent, 13, log)

# Places (region map)
lo = names("locations", "location_id")
src = (TREE / "src/data/region_map/region_map_entries.h").read_text()
ent = []
for lab in re.findall(r"(sMapName_(\w+))\[\]", src):
    k = lab[1].lower().replace("_", "-")
    for cand in (k, "hoenn-" + k, k.replace("route-", "hoenn-route-"), k + "-hoenn"):
        if cand in lo:
            ent.append((lab[0], lo[cand])); break
    else:
        log.append("place miss " + lab[0])
write("src/data/region_map/region_map_entries.h", ["Plaatsen, PokeAPI location_names.csv"], ent, None, log)

Path(OUT.parent / "names_misses.txt").write_text("\n".join(log), encoding="utf-8")
print(len(log), "misses")

# --- hand-made additions: names PokeAPI has no zh-Hans for ---------------
def append(rel, entries):
    p = OUT / (rel + ".txt")
    texts = lp.c_texts((TREE / rel).read_text(encoding="utf-8"))
    have = set(re.findall(r"^\[(\w+)\]", p.read_text(encoding="utf-8"), re.M))
    out = [p.read_text(encoding="utf-8").rstrip("\n"), "", "# Hand-made (no zh-Hans in PokeAPI)", ""]
    for label, zh in entries:
        if label in texts and label not in have:
            out += ["[%s] %s" % (label, lp.text_hash(texts[label][2])), zh, ""]
    p.write_text("\n".join(out), encoding="utf-8")

src = (TREE / "src/data/items.h").read_text()
tms = [c for c in re.findall(r"\[(ITEM_(?:TM|HM)_\w+)\]\s*=\s*\{", src)]
extra = []
ntm = nhm = 0
for c in tms:
    if c.startswith("ITEM_TM_"):
        ntm += 1; extra.append((c, "招式学习器%02d" % ntm))
    else:
        nhm += 1; extra.append((c, "秘传学习器%02d" % nhm))
mails = {"ORANGE": "橙色", "HARBOR": "海港", "GLITTER": "闪光", "MECH": "机械", "WOOD": "木纹", "WAVE": "波浪",
         "BEAD": "珠子", "SHADOW": "暗影", "TROPIC": "热带", "DREAM": "梦境", "FAB": "华丽", "RETRO": "复古"}
extra += [("ITEM_%s_MAIL" % k, v + "邮件") for k, v in mails.items()]
extra += [("ITEM_ITEMFINDER", "探宝器"), ("ITEM_POKEBLOCK_CASE", "宝可方块盒"), ("ITEM_ROOM_1_KEY", "1号房钥匙"),
          ("ITEM_ROOM_2_KEY", "2号房钥匙"), ("ITEM_ROOM_4_KEY", "4号房钥匙"), ("ITEM_ROOM_6_KEY", "6号房钥匙"),
          ("ITEM_OAKS_PARCEL", "大木的包裹"), ("ITEM_BIKE_VOUCHER", "自行车兑换券"), ("ITEM_CONTEST_PASS", "大赛通行证")]
append("src/data/items.h", extra)
append("src/data/text/move_names.h", [("MOVE_VICE_GRIP", "夹住")])
append("src/data/text/abilities.h", [("ABILITY_CACOPHONY", "噪音")])

places = {"LITTLEROOT_TOWN": "未白镇", "OLDALE_TOWN": "古辰镇", "DEWFORD_TOWN": "武斗镇", "LAVARIDGE_TOWN": "釜炎镇",
          "FALLARBOR_TOWN": "秋叶镇", "VERDANTURF_TOWN": "绿荫镇", "PACIFIDLOG_TOWN": "暮水镇",
          "PETALBURG_CITY": "橙华市", "SLATEPORT_CITY": "凯那市", "MAUVILLE_CITY": "紫堇市", "RUSTBORO_CITY": "卡那兹市",
          "FORTREE_CITY": "茵郁市", "LILYCOVE_CITY": "水静市", "MOSSDEEP_CITY": "绿岭市", "SOOTOPOLIS_CITY": "琉璃市",
          "EVER_GRANDE_CITY": "彩幽市", "UNDERWATER": "海底", "GRANITE_CAVE": "石之洞窟", "MT__CHIMNEY": "烟囱山",
          "SAFARI_ZONE": "狩猎地带", "BATTLE_FRONTIER": "对战开拓区", "PETALBURG_WOODS": "橙华森林",
          "RUSTURF_TUNNEL": "卡绿隧道", "ABANDONED_SHIP": "弃船", "NEW_MAUVILLE": "新紫堇", "METEOR_FALLS": "流星瀑布",
          "MT__PYRE": "送神山", "SHOAL_CAVE": "浅滩洞穴", "SEAFLOOR_CAVERN": "海底洞窟", "VICTORY_ROAD": "冠军之路",
          "MIRAGE_ISLAND": "幻影岛", "CAVE_OF_ORIGIN": "觉醒祠堂", "SOUTHERN_ISLAND": "南方小岛", "FIERY_PATH": "火焰小径",
          "JAGGED_PASS": "凹凸山道", "SEALED_CHAMBER": "封印之间", "SCORCHED_SLAB": "炙热岩洞", "ISLAND_CAVE": "小岛横穴",
          "DESERT_RUINS": "沙漠遗迹", "ANCIENT_TOMB": "古代墓穴", "INSIDE_OF_TRUCK": "卡车里", "SKY_PILLAR": "天空柱",
          "SECRET_BASE": "秘密基地", "_AQUA__HIDEOUT_Clone": "{AQUA}基地"}
src = (TREE / "src/data/region_map/region_map_entries.h").read_text()
ent = [("sMapName_" + k, v) for k, v in places.items()]
ent += [("sMapName_ROUTE_%d" % n, "%d号道路" % n) for n in range(101, 135)]
write("src/data/region_map/region_map_entries.h", ["Hoenn-plaatsnamen (officiële zh-Hans namen)"], ent, None, log)
