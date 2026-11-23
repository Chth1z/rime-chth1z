#!/usr/bin/env python3
"""
Deterministic, idempotent dictionary and OpenCC data cleaner for rime-chth1z.
Normalizes phonetic readings, deduplicates entries across active tables,
rebalances polyphone and collision weights, and repairs OpenCC text tables.
Run directly after syncing upstream rime-frost dictionaries:
    python scripts/clean-dicts.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import Counter

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT
DST_ROOT = REPO_ROOT

TRAD_JP_TO_SIMP = str.maketrans({
    "亜": "亚", "亞": "亚", "佈": "布", "倉": "仓", "倫": "伦", "傑": "杰", "傳": "传", "優": "优",
    "內": "内", "冨": "富", "凍": "冻", "凜": "凛", "凱": "凯", "則": "则", "剛": "刚", "劊": "刽",
    "劍": "剑", "劑": "剂", "動": "动", "勝": "胜", "勞": "劳", "呂": "吕", "喚": "唤", "喬": "乔",
    "單": "单", "嚴": "严", "圍": "围", "園": "园", "圓": "圆", "圖": "图", "團": "团", "堅": "坚",
    "場": "场", "塊": "块", "塚": "冢", "塩": "盐", "塵": "尘", "墊": "垫", "増": "增", "墜": "坠",
    "壯": "壮", "夢": "梦", "奧": "奥", "奪": "夺", "姫": "姬", "學": "学", "実": "实", "宮": "宫",
    "寧": "宁", "審": "审", "寬": "宽", "寶": "宝", "將": "将", "對": "对", "層": "层", "屬": "属",
    "岡": "冈", "峯": "峰", "島": "岛", "峽": "峡", "嵐": "岚", "嶋": "岛", "嶺": "岭", "師": "师",
    "帶": "带", "庫": "库", "廟": "庙", "強": "强", "後": "后", "復": "复", "徳": "德", "恆": "恒",
    "恵": "惠", "惡": "恶", "愛": "爱", "態": "态", "慟": "恸", "憂": "忧", "憶": "忆", "應": "应",
    "懲": "惩", "戰": "战", "戸": "户", "掃": "扫", "揮": "挥", "損": "损", "擁": "拥", "擊": "击",
    "斉": "齐", "斎": "斋", "斷": "断", "時": "时", "東": "东", "栄": "荣", "桜": "樱", "條": "条",
    "楓": "枫", "極": "极", "榮": "荣", "槍": "枪", "樂": "乐", "標": "标", "樹": "树", "橋": "桥",
    "機": "机", "橫": "横", "權": "权", "歐": "欧", "歩": "步", "歸": "归", "殺": "杀", "気": "气",
    "氣": "气", "氫": "氢", "氬": "氩", "沢": "泽", "涼": "凉", "淵": "渊", "済": "济", "渕": "渊",
    "湯": "汤", "滅": "灭", "漢": "汉", "潛": "潜", "澤": "泽", "澱": "淀", "濱": "滨", "濵": "滨",
    "瀝": "沥", "瀬": "濑", "灣": "湾", "災": "灾", "烏": "乌", "無": "无", "煉": "炼", "煙": "烟",
    "燈": "灯", "營": "营", "燼": "烬", "爾": "尔", "牆": "墙", "犧": "牺", "獄": "狱", "獅": "狮",
    "獰": "狞", "獵": "猎", "瑤": "瑶", "瑪": "玛", "環": "环", "璽": "玺", "產": "产", "異": "异",
    "疊": "叠", "瘋": "疯", "盡": "尽", "盤": "盘", "盪": "荡", "眞": "真", "眾": "众", "砲": "炮",
    "確": "确", "祿": "禄", "禍": "祸", "禦": "御", "禮": "礼", "禱": "祷", "種": "种", "稲": "稻",
    "穂": "穗", "窩": "窝", "窪": "洼", "竊": "窃", "節": "节", "籠": "笼", "紀": "纪", "紅": "红",
    "納": "纳", "純": "纯", "紗": "纱", "級": "级", "細": "细", "終": "终", "絆": "绊", "結": "结",
    "絕": "绝", "統": "统", "絵": "绘", "絹": "绢", "維": "维", "綺": "绮", "綾": "绫", "綿": "绵",
    "緊": "紧", "緒": "绪", "緞": "缎", "練": "练", "縮": "缩", "織": "织", "繪": "绘", "纏": "缠",
    "纖": "纤", "羅": "罗", "羈": "羁", "義": "义", "聖": "圣", "聡": "聪", "聯": "联", "脇": "胁",
    "腦": "脑", "腳": "脚", "膚": "肤", "膿": "脓", "臨": "临", "與": "与", "興": "兴", "茲": "兹",
    "荊": "荆", "莊": "庄", "莢": "荚", "華": "华", "菸": "烟", "萊": "莱", "萬": "万", "葉": "叶",
    "葦": "苇", "蒼": "苍", "蔵": "藏", "薫": "薰", "藍": "蓝", "蘇": "苏", "蘭": "兰", "蟲": "虫",
    "蠍": "蝎", "蠟": "蜡", "術": "术", "衛": "卫", "褲": "裤", "襲": "袭", "見": "见", "視": "视",
    "覽": "览", "觀": "观", "訪": "访", "詞": "词", "詩": "诗", "語": "语", "誠": "诚", "調": "调",
    "諏": "诹", "諾": "诺", "證": "证", "識": "识", "護": "护", "變": "变", "豊": "丰", "豬": "猪",
    "貓": "猫", "貞": "贞", "貫": "贯", "貴": "贵", "賀": "贺", "賓": "宾", "賜": "赐", "賢": "贤",
    "賽": "赛", "贖": "赎", "跡": "迹", "蹤": "踪", "軀": "躯", "軍": "军", "輝": "辉", "辮": "辫",
    "辺": "边", "迴": "回", "連": "连", "運": "运", "過": "过", "達": "达", "違": "违", "遠": "远",
    "遺": "遗", "邊": "边", "郷": "乡", "鄭": "郑", "鄰": "邻", "釘": "钉", "釩": "钒", "鈣": "钙",
    "鈴": "铃", "鈹": "铍", "鉀": "钾", "鉈": "铊", "鉑": "铂", "鉛": "铅", "鉤": "钩", "鉭": "钽",
    "鉻": "铬", "銀": "银", "銅": "铜", "銜": "衔", "銠": "铑", "銨": "铵", "銫": "铯", "銬": "铐",
    "銻": "锑", "鋁": "铝", "鋅": "锌", "鋇": "钡", "鋨": "锇", "鋰": "锂", "鋳": "铸", "鋼": "钢",
    "錘": "锤", "錦": "锦", "錫": "锡", "錳": "锰", "鍊": "链", "鍺": "锗", "鎂": "镁", "鎖": "锁",
    "鎘": "镉", "鎚": "锤", "鎢": "钨", "鎧": "铠", "鎮": "镇", "鎳": "镍", "鐐": "镣", "鐘": "钟",
    "鐮": "镰", "鐵": "铁", "鑄": "铸", "鑰": "钥", "鑼": "锣", "鑽": "钻", "長": "长", "門": "门",
    "間": "间", "関": "关", "陸": "陆", "陽": "阳", "隸": "隶", "雙": "双", "難": "难", "雲": "云",
    "靈": "灵", "響": "响", "頂": "顶", "項": "项", "順": "顺", "須": "须", "預": "预", "頑": "顽",
    "頭": "头", "願": "愿", "顧": "顾", "顯": "显", "顱": "颅", "風": "风", "颯": "飒", "飚": "飙",
    "飛": "飞", "飯": "饭", "飾": "饰", "餘": "余", "館": "馆", "馬": "马", "馭": "驭", "駒": "驹",
    "騎": "骑", "驕": "骄", "髏": "髅", "髙": "高", "髮": "发", "鬥": "斗", "魚": "鱼", "鯨": "鲸",
    "鰂": "鲗", "鱗": "鳞", "鴉": "鸦", "鷹": "鹰", "鹼": "碱", "鹽": "盐", "麗": "丽", "麥": "麦",
    "黃": "黄", "黒": "黑", "點": "点", "齋": "斋", "齒": "齿", "龍": "龙", "醯": "酰",
})


class _SimpleConverter:
    def convert(self, text: str) -> str:
        return text.translate(TRAD_JP_TO_SIMP)


CC_T2S = _SimpleConverter()


def jp_t2s(text: str) -> str:
    return text.translate(TRAD_JP_TO_SIMP)


def split_header_body(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split a Rime .dict.yaml file into header (up to and including '...') and body."""
    for i, line in enumerate(lines):
        if line.strip() == "...":
            return lines[: i + 1], lines[i + 1 :]
    return [], lines


def parse_entry(line: str) -> tuple[str, str, str, list[str]] | None:
    """Return (word, py, weight, extra_cols) or None if comment/blank."""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    parts = line.rstrip("\r\n").split("\t")
    if len(parts) < 2:
        return None
    w = parts[0]
    py = parts[1]
    wt = parts[2] if len(parts) >= 3 else ""
    extra = parts[3:] if len(parts) > 3 else []
    return w, py, wt, extra


def format_entry(w: str, py: str, wt: str, extra: list[str]) -> str:
    cols = [w, py]
    if wt != "" or extra:
        cols.append(wt)
    cols.extend(extra)
    return "\t".join(cols)


def normalize_lue_nue(py: str) -> str:
    return re.sub(r"\b([ln])ue\b", r"\1ve", py)


def replace_syl_at(word: str, py: str, char: str, old_s: str, new_s: str, cond=None) -> str:
    syls = py.split()
    if len(syls) != len(word):
        return py
    changed = False
    for i, (ch, sy) in enumerate(zip(word, syls)):
        if ch == char and sy == old_s:
            if cond is None or cond(word, syls, i):
                syls[i] = new_s
                changed = True
    return " ".join(syls) if changed else py


def w_int(wt: str) -> int:
    try:
        return int(wt)
    except ValueError:
        return 0


def find_entry_span(
    body: list[str],
    start_key: tuple[str, str],
    end_key: tuple[str, str],
    next_word: str | None = None,
) -> tuple[int, int] | None:
    """Locate an inclusive [start_idx, end_idx] span in body by (word, py) sentinels."""
    start_idx = None
    for i, line in enumerate(body):
        p = parse_entry(line)
        if not p:
            continue
        k = (p[0], normalize_lue_nue(p[1]))
        if start_idx is None:
            if k == start_key:
                if next_word is not None:
                    nxt = None
                    for j in range(i + 1, min(i + 5, len(body))):
                        np = parse_entry(body[j])
                        if np:
                            nxt = np[0]
                            break
                    if nxt != next_word:
                        continue
                start_idx = i
        elif k == end_key:
            return start_idx, i
    return None


# ---------------------------------------------------------------------------
# Explicit verified fix tables (word, old_py) -> new_py | None (DELETE)
# or (word, old_py) -> ("WORD_AND_PY", new_word, new_py)
# ---------------------------------------------------------------------------

BASE_PY_FIXES: dict[tuple[str, str], str | None] = {
    # Hard format bug
    ("均订", "junding"): "jun ding",
    # Single-reading bugs (ffe1e944 + c1b5d1b8 + 3f37fbc7)
    ("拉群", "la qu"): "la qun",
    ("母子俩", "mu zi liang"): "mu zi lia",
    ("都给她", "dou ji ta"): "dou gei ta",
    ("大行情", "da xing qing"): "da hang qing",
    ("折衷", "she zhong"): "zhe zhong",
    ("申时行", "shen shi hang"): "shen shi xing",
    ("还准备", "huan zhun bei"): "hai zhun bei",
    ("壳牌", "qiao pai"): "ke pai",
    ("蓦地", "mo de"): "mo di",
    ("不咋的", "bu za di"): "bu za de",
    ("不得劲", "bu dei jin"): "bu de jin",
    ("得非常", "dei fei chang"): None,  # broken complement fragment
    ("得就", "dei jiu"): None,  # broken fragment
    ("得于", "dei yu"): None,  # broken fragment
    ("谁谁", "shei shui"): "shei shei",
    # Tail single-reading polyphone bugs (3f37fbc7)
    ("行研", "xing yan"): "hang yan",
    ("调阻", "diao zu"): "tiao zu",
    ("调香", "diao xiang"): "tiao xiang",
    ("行里", "xing li"): "hang li",
    ("手长", "shou zhang"): "shou chang",
    ("我勒个去", "wo lei ge qu"): "wo le ge qu",
    ("故技重施", "gu ji zhong shi"): "gu ji chong shi",
    ("长牛", "zhang niu"): "chang niu",
    ("长链", "zhang lian"): "chang lian",
    ("弹个", "dan ge"): "tan ge",
    ("勾调", "gou diao"): "gou tiao",
    ("打颤", "da zhan"): "da chan",
    ("裤长", "ku zhang"): "ku chang",
    ("键长", "jian zhang"): "jian chang",
    ("利星行", "li xing xing"): "li xing hang",
    ("长三乙", "zhang san yi"): "chang san yi",
    ("阿伽通", "a ga tong"): "a jia tong",
    ("行与行", "xing yu xing"): "hang yu hang",
    ("说唱乐", "shuo chang le"): "shuo chang yue",
    ("长赐轮", "zhang ci lun"): "chang ci lun",
    ("重雪芝", "zhong xue zhi"): "chong xue zhi",
    ("劲装", "jin zhuang"): "jing zhuang",
    ("长则", "zhang ze"): "chang ze",
    ("系统地", "xi tong di"): "xi tong de",
    ("般地", "ban di"): None,  # suffix fragment
    ("淡淡地", "dan dan di"): "dan dan de",
    ("直直地", "zhi zhi di"): "zhi zhi de",
    ("细细地", "xi xi di"): "xi xi de",
    ("简短地", "jian duan di"): "jian duan de",
    ("曝出", "pu chu"): "bao chu",
    ("削骨", "xiao gu"): "xue gu",
    # Bogus duplicate readings to DELETE (correct reading already exists in base)
    ("得到", "dei dao"): None,
    ("就得到", "jiu dei dao"): None,
    ("你得到", "ni dei dao"): None,
    ("也得到", "ye dei dao"): None,
    ("可得到", "ke dei dao"): None,
    ("我得到", "wo dei dao"): None,
    ("不得", "bu dei"): None,
    ("不得了", "bu de le"): None,
    ("还不起", "hai bu qi"): None,
    ("还得了", "hai de le"): None,
    ("罢了", "ba liao"): None,
    ("了不起", "le bu qi"): None,
    ("美的", "mei di"): None,
    ("大都会", "da dou hui"): None,
    ("举办地", "ju ban de"): None,
    ("拓扑排序", "ta pu pai xu"): None,
    # Common mispronunciations moved to corrections.dict.yaml with calibrated weights & hints
    ("脉脉", "mai mai"): None,
    ("扛鼎", "kang ding"): None,
    ("抹布", "mo bu"): None,
    ("游说", "you shuo"): None,
    ("咋的", "za di"): None,
    ("怎的", "zen di"): None,
    ("下调", "xia diao"): None,
    ("下调到", "xia diao dao"): None,
    ("爪哇", "zhua wa"): None,
    ("魔爪", "mo zhua"): None,
    ("单薄", "dan bao"): None,
    ("轻薄", "qing bao"): None,
    ("躯壳", "qu ke"): None,
    ("裸露", "luo lou"): None,
    ("外露", "wai lou"): None,
    ("深藏不露", "shen cang bu lou"): None,
    ("给予", "gei yu"): None,
    ("供给", "gong gei"): None,
    ("关卡", "guan ka"): None,
    ("卡脖子", "ka bo zi"): None,
    ("藤蔓", "teng man"): None,
    ("青玉案", "qing yu wan"): None,
    ("青玉案元夕", "qing yu wan yuan xi"): None,
    # 105 verified conflict fixes from c1b5d1b8 Part 2
    ("白袷蓝衫", "bai qia lan shan"): "bai jia lan shan",
    ("苯并芘", "ben bing bi"): "ben bing pi",
    ("闭明塞聪", "bi ming sai cong"): "bi ming se cong",
    ("丙泊酚", "bing po fen"): "bing bo fen",
    ("补阳还五汤", "bu yang hai wu tang"): "bu yang huan wu tang",
    ("岑参", "cen can"): "cen shen",
    ("炒茄丝", "chao jia si"): "chao qie si",
    ("川芎茶调散", "chuan xiong cha diao san"): "chuan xiong cha tiao san",
    ("道在屎溺", "dao zai shi ni"): "dao zai shi niao",
    ("颠茄", "dian jia"): "dian qie",
    ("颠茄片", "dian jia pian"): "dian qie pian",
    ("调露", "diao lu"): "tiao lu",
    ("调律", "diao lv"): "tiao lv",
    ("都一处", "dou yi chu"): "du yi chu",
    ("都匀毛尖", "dou yun mao jian"): "du yun mao jian",
    ("多言数穷", "duo yan shu qiong"): "duo yan shuo qiong",
    ("多粘菌素", "duo zhan jun su"): "duo nian jun su",
    ("恶之欲其死", "e zhi yu qi si"): "wu zhi yu qi si",
    ("飞镜又重磨", "fei jing you zhong mo"): "fei jing you chong mo",
    ("肺俞穴", "fei yu xue"): "fei shu xue",
    ("服部半藏", "fu bu ban cang"): "fu bu ban zang",
    ("钙调蛋白", "gai diao dan bai"): "gai tiao dan bai",
    ("钙调磷酸酶", "gai diao lin suan mei"): "gai tiao lin suan mei",
    ("钙调素", "gai diao su"): "gai tiao su",
    ("肝俞穴", "gan yu xue"): "gan shu xue",
    ("格栅灯", "ge zha deng"): "ge shan deng",
    ("刮匙", "gua shi"): "gua chi",
    ("郭寄峤", "guo ji jiao"): "guo ji qiao",
    ("海螵蛸", "hai piao shao"): "hai piao xiao",
    ("何日更重游", "he ri geng zhong you"): "he ri geng chong you",
    ("嵇曾筠", "ji ceng yun"): "ji zeng yun",
    ("解铃还须系铃人", "jie ling hai xu xi ling ren"): None,
    ("今人多不弹", "jin ren duo bu dan"): "jin ren duo bu tan",
    ("句芒", "ju mang"): "gou mang",
    ("卡泊芬净", "ka po fen jing"): "ka bo fen jing",
    ("落人口实", "la ren kou shi"): "luo ren kou shi",
    ("辣汁茄丝", "la zhi jia si"): "la zhi qie si",
    ("礼服呢", "li fu ne"): None,
    ("临别殷勤重寄词", "lin bie yin qin zhong ji ci"): "lin bie yin qin chong ji ci",
    ("苓桂术甘汤", "ling gui shu gan tang"): "ling gui zhu gan tang",
    ("露阴癖", "lou yin pi"): "lu yin pi",
    ("马作的卢飞快", "ma zuo de lu fei kuai"): "ma zuo di lu fei kuai",
    ("美都", "mei dou"): "mei du",
    ("蒙藏院", "meng cang yuan"): "meng zang yuan",
    ("藐姑射之山", "miao gu she zhi shan"): "miao gu ye zhi shan",
    ("辟兵", "pi bing"): "bi bing",
    ("便宜坊", "pian yi fang"): "bian yi fang",
    ("屏声静气", "ping sheng jing qi"): "bing sheng jing qi",
    ("泊洛沙姆", "po luo sha mu"): "bo luo sha mu",
    ("泊松分布", "po song fen bu"): None,
    ("俟我于城隅", "qi wo yu cheng yu"): "si wo yu cheng yu",
    ("炝青蛤", "qiang qing ha"): "qiang qing ge",
    ("郄穴", "qie xue"): "xi xue",
    ("曲阑深处重相见", "qu lan shen chu zhong xiang jian"): "qu lan shen chu chong xiang jian",
    ("融融泄泄", "rong rong xie xie"): "rong rong yi yi",
    ("如听仙乐耳暂明", "ru ting xian le er zan ming"): "ru ting xian yue er zan ming",
    ("桑给巴尔", "sang gei ba er"): "sang ji ba er",
    ("桑螵蛸", "sang piao shao"): "sang piao xiao",
    ("善贾而沽", "shan gu er gu"): "shan jia er gu",
    ("舌系带", "she ji dai"): "she xi dai",
    ("舌系带过短", "she ji dai guo duan"): "she xi dai guo duan",
    ("生查子", "sheng cha zi"): "sheng zha zi",
    ("盛年不重来", "sheng nian bu zhong lai"): "sheng nian bu chong lai",
    ("事非得已", "shi fei dei yi"): "shi fei de yi",
    ("时行感冒", "shi hang gan mao"): "shi xing gan mao",
    ("水榭花都", "shui xie hua dou"): "shui xie hua du",
    ("酥炸茄盒", "su zha jia he"): "su zha qie he",
    ("头孢泊肟酯", "tou bao po wo zhi"): "tou bao bo wo zhi",
    ("图像传输", "tu xiang zhuan shu"): None,
    ("胃俞穴", "wei yu xue"): "wei shu xue",
    ("我劝天公重抖擞", "wo quan tian gong zhong dou sou"): "wo quan tian gong chong dou sou",
    ("我言秋日胜春朝", "wo yan qiu ri sheng chun chao"): "wo yan qiu ri sheng chun zhao",
    ("五行八作", "wu xing ba zuo"): "wu hang ba zuo",
    ("茜草", "xi cao"): "qian cao",
    ("仙乐风飘处处闻", "xian le feng piao chu chu wen"): "xian yue feng piao chu chu wen",
    ("刑不上大夫", "xing bu shang dai fu"): "xing bu shang da fu",
    ("星都", "xing dou"): "xing du",
    ("燕都", "yan dou"): "yan du",
    ("以俟夫观人风者得焉", "yi qi fu guan ren feng zhe de yan"): "yi si fu guan ren feng zhe de yan",
    ("依托泊苷", "yi tuo po gan"): "yi tuo bo gan",
    ("意义识记", "yi yi zhi ji"): "yi yi shi ji",
    ("蔚山现代", "yu shan xian dai"): "wei shan xian dai",
    ("俞穴", "yu xue"): "shu xue",
    ("与衣狐貉者立", "yu yi hu hao zhe li"): "yu yi hu he zhe li",
    ("攒竹", "zan zhu"): "cuan zhu",
    ("攒竹穴", "zan zhu xue"): "cuan zhu xue",
    ("炸茄饼", "zha jia bing"): "zha qie bing",
    ("乍暖还寒", "zha nuan huan han"): "zha nuan hai han",
    ("乍暖还寒时候", "zha nuan huan han shi hou"): "zha nuan hai han shi hou",
    ("粘多糖", "zhan duo tang"): "nian duo tang",
    ("粘滞性", "zhan zhi xing"): "nian zhi xing",
    ("中大夫", "zhong dai fu"): "zhong da fu",
    ("重睑成形术", "zhong jian cheng xing shu"): "chong jian cheng xing shu",
    ("重睑术", "zhong jian shu"): "chong jian shu",
    ("重言式", "zhong yan shi"): "chong yan shi",
    ("椎心饮泣", "zhui xin yin qi"): "chui xin yin qi",
    ("自矜者不长", "zi jin zhe bu zhang"): "zi jin zhe bu chang",
}

BASE_DELETE_WORDS: set[str] = {
    # Verified spelling typos (note: 义正词严 is standard in 现汉第7版 and kept)
    "总得来说", "毛人风", "讲诉", "很拉跨",
    "名符其实", "莫明其妙", "螳臂挡车", "锐不可挡",
    "书声朗朗", "坐无虚席", "震聋发聩", "轰堂大笑", "一笔勾消", "真知卓见",
    # Pure suffix / broken particle fragments (never valid standalone words or .gram glue)
    "们的", "般的", "了呢", "了我", "了他", "了么",
    "了个", "了些", "了下", "了她", "了点", "了呀", "了什么", "了才", "了哦",
    "了呗", "了一阵", "了吧唧", "了点儿", "个月",
    # Truncated fragments
    "既又", "是我太", "无招胜", "埃雅仁", "麦克劳", "奥金莱", "龙勃罗", "库兹涅",
    "心金魂", "船小好", "瑟兰督", "哥尔摩", "爱猷识", "间通信", "维流形", "陪你到",
    "的人时",
}

BASE_REWEIGHT: dict[tuple[str, str], int] = {
    # Polyphone weight clones & classical readings
    ("都会", "du hui"): 1000,
    ("不了", "bu le"): 1000,
    ("面的", "mian di"): 150,
    ("打着", "da zhao"): 400,
    ("落在", "la zai"): 350,
    ("落下", "la xia"): 700,
    ("穿着", "chuan zhuo"): 2000,
    ("我穿着", "wo chuan zhuo"): 20,
    ("他穿着", "ta chuan zhuo"): 20,
    ("人和", "ren hu"): 100,
    ("平和", "ping hu"): 100,
    ("天和", "tian hu"): 50,
    ("圈里", "juan li"): 80,
    ("浅浅", "jian jian"): 20,
    ("大城", "dai cheng"): 30,
    ("半藏", "ban cang"): 30,
    ("怎么还", "zen me huan"): 100,
    ("是以", "shi yi"): 400,
    ("衣裳", "yi chang"): 150,
    # Rebalanced grammatical bigrams (kept in lattice for .gram collocations, below standalone real words)
    ("是在", "shi zai"): 2500,
    ("时的", "shi de"): 300,
    ("是有", "shi you"): 1000,
    ("是由", "shi you"): 800,
    ("就把", "jiu ba"): 500,
    ("在这", "zai zhe"): 800,
    ("我把", "wo ba"): 800,
    ("又有", "you you"): 400,
    ("人是", "ren shi"): 1000,
    ("中的", "zhong de"): 500,
    ("上的", "shang de"): 1500,
    ("里的", "li de"): 1000,
    ("人的", "ren de"): 150,
    ("后的", "hou de"): 600,
    ("下的", "xia de"): 600,
    ("多的", "duo de"): 600,
    ("家的", "jia de"): 600,
    ("字的", "zi de"): 100,
    ("神的", "shen de"): 200,
    ("气的", "qi de"): 200,
    ("住的", "zhu de"): 200,
    ("点的", "dian de"): 200,
    ("前的", "qian de"): 200,
    ("书的", "shu de"): 200,
    ("水的", "shui de"): 200,
    ("站的", "zhan de"): 200,
    ("车的", "che de"): 200,
    ("线的", "xian de"): 200,
    ("组的", "zu de"): 200,
    ("喝的", "he de"): 200,
    ("带的", "dai de"): 200,
    ("放的", "fang de"): 200,
    ("练的", "lian de"): 200,
    ("卡的", "ka de"): 200,
    ("装的", "zhuang de"): 200,
    ("提的", "ti de"): 200,
    ("唱的", "chang de"): 200,
    ("搞的", "gao de"): 200,
    # Rebalanced verb/adj+的 so 得/real words aren't crushed
    ("来的", "lai de"): 1500,
    ("过的", "guo de"): 1800,
    ("讲的", "jiang de"): 1400,
    ("学的", "xue de"): 900,
    ("玩的", "wan de"): 900,
    ("打的", "da de"): 1500,
    ("高的", "gao de"): 2500,
    ("小的", "xiao de"): 1000,
    ("长的", "chang de"): 1000,
    ("生的", "sheng de"): 300,
    # Extreme Zhihu/pop-culture hijackers
    ("曼联", "man lian"): 1000,
    ("苏轼", "su shi"): 500,
    ("梅西", "mei xi"): 650,
    ("曹操", "cao cao"): 750,
    ("尸体", "shi ti"): 2000,
    ("知友", "zhi you"): 300,
    ("大一", "da yi"): 1500,
    ("题主", "ti zhu"): 2000,
    ("知乎", "zhi hu"): 5000,
    ("答主", "da zhu"): 1500,
    ("谢邀", "xie yao"): 1000,
    ("分割线", "fen ge xian"): 1500,
    ("牛逼", "niu bi"): 1500,
    ("蝙蝠侠", "bian fu xia"): 1500,
}

BASE_XIE_DOWNWEIGHT_WORDS: set[str] = {
    "血液", "血管", "血糖", "血统", "血腥", "吸血鬼", "血压", "心血", "鲜血", "血脉",
    "血量", "血浆", "血缘", "血清", "血栓", "血型", "血氧", "血脂", "血检", "血虚",
    "血崩", "血肿", "血书", "血象", "血尿", "血亲", "血库", "血痂", "贫血", "失血",
    "缺血", "凝血", "溶血", "混血", "输血", "采血", "献血", "验血", "止血", "活血",
    "供血", "补血", "铁血", "冷血", "热血", "充血", "嗜血", "残血", "满血", "淤血",
    "瘀血", "便血", "尿血", "咯血", "咳血", "呕血", "回血", "吸血", "血迹", "气血",
    "血肉", "血色", "血性", "血战", "换血", "血亏", "血条", "血气", "一血", "血洗",
    "掉血", "血样", "带血", "血红", "血源", "加血", "血汗", "血站", "血污", "半血",
    "血拼", "血线", "血案", "血月", "血痕", "血海", "血魔", "血染", "血中", "血厚",
    "血槽", "血渍", "骨血", "红血", "经血", "泣血",
}

BASE_SHOU_DOWNWEIGHT_WORDS: set[str] = {
    "熟记", "纯熟", "早熟", "熟食", "杀熟", "相熟", "熟铁", "熟客", "耳熟", "催熟", "练熟",
}

BASE_SHUI_SCALE_WORDS: set[str] = {
    "是谁", "谁的", "谁能", "谁知道", "谁是", "谁都", "谁说", "谁会", "谁也", "谁来",
    "谁家", "有谁", "谁还", "谁知", "谁让", "谁敢", "看谁", "谁就", "谁在", "谁呢",
    "谁又", "谁要", "比谁", "给谁", "谁不", "和谁", "谁去", "谁有", "找谁", "跟谁",
    "谁知道呢", "谁叫", "谁啊", "那谁", "为谁", "谁赢", "谁给", "被谁", "谁做", "说谁",
    "对谁", "怪谁", "听谁", "谁想", "换谁", "谁买", "谁用", "向谁", "选谁", "问谁",
    "由谁", "谁料", "谁人", "那个谁", "这谁", "谁干", "谁好", "谁信", "见谁", "任谁",
    "归谁", "谁当", "打谁", "谁对", "谁呀", "谁最", "没谁", "谁管", "谁看", "谁出",
    "用谁", "谁怕", "谁上", "爱谁", "帮谁", "谁再",
}

EXT_PY_FIXES: dict[tuple[str, str], str | None] = {
    # ffe1e944
    ("多周目", "er zhou mu"): "duo zhou mu",
    ("发现不了", "fa xian bu le"): "fa xian bu liao",
    ("处理不了", "chu li bu le"): "chu li bu liao",
    ("抽丝剥茧", "chou si bao jian"): "chou si bo jian",
    ("都对应", "du dui ying"): "dou dui ying",
    ("都得不到", "dou dei bu dao"): "dou de bu dao",
    ("重头再来", "zhong tou zai lai"): "chong tou zai lai",
    ("长肌肉", "chang ji rou"): "zhang ji rou",
    ("必须得到", "bi xu dei dao"): "bi xu de dao",
    ("不着痕迹", "bu zhao hen ji"): "bu zhuo hen ji",
    ("重头开始", "zhong tou kai shi"): "chong tou kai shi",
    ("不得有", "bu dei you"): "bu de you",
    ("什么都得不到", "shen me dou dei bu dao"): "shen me dou de bu dao",
    ("美的空调", "mei di kong tiao"): "mei de kong tiao",
    ("还贷款", "hai dai kuan"): None,
    ("也不得", "ye bu dei"): None,
    # c1b5d1b8 Part 2
    ("阿其所好", "a qi suo hao"): "e qi suo hao",
    ("挨山塞海", "ai shan sai hai"): "ai shan se hai",
    ("被坚执锐", "bei jian zhi rui"): "pi jian zhi rui",
    ("兵车行", "bing che hang"): "bing che xing",
    ("不长眼", "bu chang yan"): None,
    ("不长眼睛", "bu chang yan jing"): None,
    ("大王村", "dai wang cun"): "da wang cun",
    ("得放手时须放手", "dei fang shou shi xu fang shou"): "de fang shou shi xu fang shou",
    ("氐土貉", "di tu hao"): "di tu he",
    ("厚味腊毒", "hou wei la du"): "hou wei xi du",
    ("神使鬼差", "shen shi gui cha"): "shen shi gui chai",
    ("熟得快", "shou dei kuai"): "shou de kuai",
    ("熟得快", "shu dei kuai"): "shu de kuai",
    ("万箭攒心", "wan jian zan xin"): "wan jian cuan xin",
    ("文徵明", "wen zhi ming"): "wen zheng ming",
    ("揎拳捋袖", "xuan quan lv xiu"): "xuan quan luo xiu",
    ("蔚山广域市", "yu shan guang yu shi"): "wei shan guang yu shi",
    ("炸茄盒", "zha jia he"): "zha qie he",
    ("丹佛掘金", "dan fu jue jin"): "dan fo jue jin",
    ("佛罗伦", "fu luo lun"): "fo luo lun",
    ("刻薄寡恩", "ke bao gua en"): "ke bo gua en",
    ("口角流涎", "kou jue liu xian"): "kou jiao liu xian",
    ("奥利佛", "ao li fu"): "ao li fo",
    ("宋嬷嬷", "song ma ma"): "song mo mo",
    ("寡情薄意", "gua qing bao yi"): "gua qing bo yi",
    ("李嬷嬷", "li ma ma"): "li mo mo",
    ("浅见薄识", "qian jian bao shi"): "qian jian bo shi",
    ("浑不似", "hun bu shi"): "hun bu si",
    ("王嬷嬷", "wang ma ma"): "wang mo mo",
    ("薄情无义", "bao qing wu yi"): "bo qing wu yi",
    ("赖嬷嬷", "lai ma ma"): "lai mo mo",
    ("轻徭薄赋", "qing yao bao fu"): "qing yao bo fu",
    ("轻薄无知", "qing bao wu zhi"): "qing bo wu zhi",
    ("轻薄无礼", "qing bao wu li"): "qing bo wu li",
    ("郭嵩焘", "guo song dao"): "guo song tao",
    ("门衰祚薄", "men shuai zuo bao"): "men shuai zuo bo",
    ("世情薄", "shi qing bao"): "shi qing bo",
    ("两面佛", "liang mian fu"): "liang mian fo",
    ("佛世界", "fu shi jie"): "fo shi jie",
    ("佛慧山", "fu hui shan"): "fo hui shan",
    ("佛有缘", "fu you yuan"): "fo you yuan",
    ("佛罗伦斯", "fu luo lun si"): "fo luo lun si",
    ("佛道之争", "fu dao zhi zheng"): "fo dao zhi zheng",
    ("哈佛大学医学院", "ha fu da xue yi xue yuan"): "ha fo da xue yi xue yuan",
    ("哈佛大学商学院", "ha fu da xue shang xue yuan"): "ha fo da xue shang xue yuan",
    ("美国哈佛大学", "mei guo ha fu da xue"): "mei guo ha fo da xue",
    ("势孤力薄", "shi gu li bao"): "shi gu li bo",
    ("本小利薄", "ben xiao li bao"): "ben xiao li bo",
    ("舌苔薄白", "she tai bao bai"): "she tai bo bai",
    ("金属薄板", "jin shu bao ban"): "jin shu bo ban",
    ("热情似火", "re qing shi huo"): "re qing si huo",
    ("背俞穴", "bei yu xue"): "bei shu xue",
    ("语音转文字", "yu yin zhuai wen zi"): "yu yin zhuan wen zi",
    ("鬼女红叶", "gui nv gong ye"): "gui nv hong ye",
    ("大黄页", "dai huang ye"): "da huang ye",
    ("八爪鱼", "ba zhao yu"): "ba zhua yu",
    ("椎拳崇", "chui quan chong"): "zhui quan chong",
    ("流血涂野草", "liu xie tu ye cao"): "liu xue tu ye cao",
}

EXT_DELETE_WORDS: set[str] = {
    # Typos
    "融汇贯通", "墨守陈规", "消声匿迹", "按步就班", "宁缺勿滥", "走头无路",
    "金榜提名", "全神灌注", "杀鸡警猴", "不记前嫌", "杀一警百",
    "齐恒公", "黑耀石", "照像馆", "疯疯颠颠", "对薄公堂",
    # Leading-得 & digit-stripped & broken fragments (74818721 + 3f37fbc7)
    "得很好", "得不行",
    "元左右", "万左右", "年以来", "及以上", "篇文章", "岁以上", "月中旬", "岁的时候",
    "所学校", "万以上", "分左右", "万美金", "亿美金", "门课程", "岁以下", "岁左右",
    "支球队", "类产品", "元以上", "型糖尿病", "个多月", "元以下",
    "哈哈哈哈哈哈哈哈", "一个大", "为一个", "现在在", "些什么", "变得更", "在这一",
    "才是最", "中使用", "方法来", "思考和", "专门为", "里没有", "以我的", "方式和",
    "世界上最", "里的人", "音乐为什么", "一个好", "我和我", "问为什么", "以此为",
    "可以不", "上可以", "后才能", "要求和", "史上最", "最最最",
    "魏国大", "鸣人刚", "鸣人当", "鹿晗发", "黑斯廷", "大眼瞪", "联通新", "虎谋皮", "阿尔巴尼",
    "生㨃", "针㨃", "水㨃", "词㨃", "战㨃", "超㨃", "唯㨃", "条㨃", "仔㨃",
    "最牛逼的", "然并卵", "都是耍流氓",
}

EXT_REWEIGHT: dict[str, int] = {
    "放我出去": 200,
    "知乎上": 800,
    "题主的问题": 200,
    "肖秀荣": 500,
    "贝吉塔": 400,
    "古美门": 300,
    "张麻子": 300,
    "吴亦凡": 200,
    "弗利萨": 300,
    "杀生丸": 300,
    "黄四郎": 300,
    "脑残粉": 200,
    "一脸懵逼": 300,
    "骚操作": 300,
    "我特么": 150,
}

LEXICAL_LEADING_DE = {
    "的确", "的话", "的士", "的卢", "的哥", "的姐", "的当", "的黎波里", "的的喀喀湖", "的确良",
    "的笃", "的溜", "的砾", "的然", "的实", "的真", "的证", "的字", "的字结构",
}


def is_leading_de_fragment(word: str, py: str) -> bool:
    if not word.startswith("的") or len(word) < 2:
        return False
    if word in LEXICAL_LEADING_DE:
        return False
    if any(word.startswith(p) for p in ("的士", "的确", "的卢", "的哥", "的姐", "的黎波里", "的的喀喀")):
        return False
    return py.startswith("de ")


def is_leading_le_fragment(word: str, py: str) -> bool:
    return word.startswith("了") and len(word) >= 2 and py.startswith("le ")


# ---------------------------------------------------------------------------
# Per-file cleaners
# ---------------------------------------------------------------------------

def clean_8105(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    reweight_map = {
        ("盛", "sheng"): 1200,
        ("盛", "cheng"): 350,
        ("和", "hu"): 80,
        ("和", "huo"): 350,
        ("咯", "ka"): 120,
        ("咯", "luo"): 80,
        ("咯", "lo"): 300,
        ("咯", "ge"): 400,
        ("给", "ji"): 250,
        ("约", "yao"): 60,
        ("嚼", "jue"): 120,
        ("忒", "tui"): 40,
        ("血", "xie"): 800,
        ("降", "xiang"): 450,
        ("缪", "miao"): 80,
        ("缪", "miu"): 60,
        ("缪", "mou"): 100,
        ("撮", "zuo"): 15,
        ("於", "yu"): 250,
        ("卻", "que"): 40,
        ("麽", "mo"): 80,
        ("祐", "you"): 40,
        ("昇", "sheng"): 80,
        ("車", "ju"): 30,
        ("得", "dei"): 3000,
        ("行", "hang"): 1800,
        ("勒", "lei"): 200,
        ("拓", "ta"): 30,
        ("屮", "cao"): 20,
        # Colloquial / habit readings kept at non-hijacking tolerance weights
        ("哟", "you"): 150,
        ("铬", "luo"): 15,
    }
    out = list(hdr)
    seen = set()
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        if (w, py) == ("芔", "cao"):
            py = "hui"
            stats["fixed_py"] += 1
        if (w, py) in reweight_map:
            new_wt = str(reweight_map[(w, py)])
            if wt != new_wt:
                wt = new_wt
                stats["reweighted"] += 1
        seen.add((w, py))
        out.append(format_entry(w, py, wt, extra))

    # Missing standard Putonghua readings from 《现代汉语词典》第7版
    additions = [
        ("芔", "hu", "1"),
        ("屮", "che", "50"),
        ("呇", "qi", "2"),
        ("颤", "zhan", "50"),
        ("暴", "pu", "30"),
        ("汤", "shang", "20"),
        ("町", "ting", "200"),
        ("属", "zhu", "30"),
        ("般", "bo", "30"),
        ("若", "re", "30"),
        ("六", "lu", "30"),
        ("房", "pang", "20"),
        ("谷", "yu", "20"),
        ("蛇", "yi", "20"),
        ("叶", "she", "20"),
        ("嘬", "chuai", "10"),
        ("椎", "chui", "10"),
        ("酢", "cu", "10"),
        ("噱", "jue", "10"),
        ("辗", "nian", "10"),
        ("窨", "xun", "10"),
        ("潦", "lao", "10"),
        ("阏", "e", "10"),
        ("饧", "tang", "10"),
        ("薁", "yu", "10"),
        ("姥", "mu", "10"),
        ("被", "pi", "10"),
        ("射", "ye", "10"),
        ("邪", "ye", "10"),
        ("邪", "ya", "10"),
        ("宛", "yuan", "10"),
        ("遗", "wei", "10"),
        ("氓", "meng", "10"),
        ("掸", "shan", "10"),
        ("嗑", "he", "10"),
        ("孱", "can", "10"),
        ("砉", "xu", "5"),
        ("袷", "jia", "5"),
        ("繇", "yao", "5"),
        ("傀", "gui", "5"),
        ("焘", "dao", "5"),
        ("镦", "dui", "5"),
        ("酂", "cuo", "5"),
        ("隗", "kui", "5"),
        ("車", "che", "10"),
    ]
    to_add = [(w, py, wt) for (w, py, wt) in additions if (w, py) not in seen]
    if to_add:
        out.append("# 补充标准普通话读音")
        for w, py, wt in to_add:
            out.append(f"{w}\t{py}\t{wt}")
            seen.add((w, py))
            stats["added"] += 1
    return out


def clean_base(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    shei_wt: dict[str, int] = {}
    for line in body:
        p = parse_entry(line)
        if p and p[0] in BASE_SHUI_SCALE_WORDS and "shei" in p[1].split():
            shei_wt[p[0]] = max(shei_wt.get(p[0], 0), w_int(p[2]))
    out = list(hdr)
    added_shide = False
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in BASE_DELETE_WORDS:
            stats["deleted_noise_or_typo"] += 1
            continue
        if (w, py) in BASE_PY_FIXES:
            new_py = BASE_PY_FIXES[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        if (w, py) in BASE_REWEIGHT:
            new_wt = str(BASE_REWEIGHT[(w, py)])
            if wt != new_wt:
                wt = new_wt
                stats["reweighted"] += 1
        elif w in BASE_XIE_DOWNWEIGHT_WORDS and "xie" in py.split():
            old_w = w_int(wt)
            if old_w > 200:
                wt = str(min(max(old_w // 8, 1), 200))
                stats["reweighted"] += 1
        elif w in BASE_SHOU_DOWNWEIGHT_WORDS and "shou" in py.split():
            old_w = w_int(wt)
            if old_w > 80:
                wt = str(min(max(old_w // 8, 1), 80))
                stats["reweighted"] += 1
        elif w in BASE_SHUI_SCALE_WORDS and "shui" in py.split():
            ref = shei_wt.get(w, 0)
            old_w = w_int(wt)
            if ref > 0:
                target = max(ref // 4, 1)
                if old_w > target:
                    wt = str(target)
                    stats["reweighted"] += 1
        if (w, py) == ("是的", "shi de"):
            added_shide = True
        out.append(format_entry(w, py, wt, extra))

    if not added_shide:
        out.append("# 补充高频常用词")
        out.append("是的\tshi de\t35000")
        stats["added"] += 1
    return out


EXT_TOLERANCE_REWEIGHT: dict[tuple[str, str], int] = {
    ("熟练度", "shou lian du"): 15,
    ("成熟度", "cheng shou du"): 15,
    ("熟练地", "shou lian de"): 15,
    ("熟悉程度", "shou xi cheng du"): 15,
    ("成熟稳重", "cheng shou wen zhong"): 15,
    ("熟练程度", "shou lian cheng du"): 15,
    ("都熟悉", "dou shou xi"): 15,
    ("熟悉度", "shou xi du"): 15,
    ("熟悉的感觉", "shou xi de gan jue"): 15,
    ("熟悉的地方", "shou xi de di fang"): 15,
    ("变得成熟", "bian de cheng shou"): 15,
    ("拿着微薄的工资", "na zhe wei bao de gong zi"): 10,
    ("拿着微薄的薪水", "na zhe wei bao de xin shui"): 10,
}


def clean_ext(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in EXT_DELETE_WORDS or is_leading_de_fragment(w, py) or is_leading_le_fragment(w, py):
            stats["deleted_noise_or_typo"] += 1
            continue
        if (w, py) in EXT_PY_FIXES:
            new_py = EXT_PY_FIXES[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        if (w, py) in EXT_TOLERANCE_REWEIGHT and w_int(wt) > EXT_TOLERANCE_REWEIGHT[(w, py)]:
            wt = str(EXT_TOLERANCE_REWEIGHT[(w, py)])
            stats["reweighted"] += 1
        # Downweight medical xie clones in ext (idempotent: threshold > 50)
        if "血" in w and "xie" in py.split() and w_int(wt) > 50:
            wt = str(min(w_int(wt) // 8, 50))
            stats["reweighted"] += 1
        if w in EXT_REWEIGHT and w_int(wt) > EXT_REWEIGHT[w]:
            wt = str(EXT_REWEIGHT[w])
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_others(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    # Build line-indexed map for legacy block removal (L72-L247 in original file)
    orig_body_start = len(hdr) + 1
    others_py_fixes = {
        ("本传", "ben chuan"): "ben zhuan",
        ("点校", "dian xiao"): "dian jiao",
        ("高弹", "gao dan"): "gao tan",
        ("颉利", "jie li"): "xie li",
        ("率土", "lv tu"): "shuai tu",
        ("弹速", "tan su"): "dan su",
        ("爪机", "zhao ji"): "zhua ji",
        ("丢勒", "diu lei"): "diu le",
        ("广佛", "guang fu"): "guang fo",
        ("缺觉", "que jue"): "que jiao",
        ("杀降", "sha jiang"): "sha xiang",
        ("豉油", "shi you"): "chi you",
        ("庶长", "shu chang"): "shu zhang",
        ("券门", "quan men"): "xuan men",
        ("麻爪", "ma zhao"): "ma zhua",
        ("扒制", "ba zhi"): "pa zhi",
        ("甜薄撑", "tian bo cheng"): "tian bao cheng",
        ("鸭脯", "ya fu"): "ya pu",
        ("心脏压塞", "xin zang ya se"): "xin zang ya sai",
    }
    others_word_fixes = {
        "溝呂木": ("沟吕木", "gou lv mu"),
        "马伊俐": ("马伊琍", "ma yi li"),
        "王抒": ("王忬", "wang yu"),
    }
    others_delete_words = {
        "滔博", "原贴", "肉沫", "延用", "颠佬", "自醒",
        "二刺", "租宝", "分裤", "性价", "触式",
    }
    tolerance_reweight = {
        ("坐骑", "zuo ji"): 150,
        ("铁骑", "tie ji"): 80,
        ("一骑绝尘", "yi ji jue chen"): 80,
        ("扑街", "pu gai"): 80,
    }
    out = list(hdr)
    seen = set()
    in_legacy_block = False
    for line in body:
        stripped = line.strip()
        if stripped.startswith("##### 错音错字提示"):
            in_legacy_block = True
            continue
        if in_legacy_block:
            if stripped.startswith("##### 叠字"):
                in_legacy_block = False
            else:
                if parse_entry(line):
                    stats["deleted_legacy_hijack"] += 1
                continue
        if "这里额外加上 hao 音" in line:
            out.append("# 这里的「镐」规范读音为 hao，补充 gao 容错读音")
            continue
        parsed = parse_entry(line)
        if not parsed:
            if stripped.startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in others_delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if w in others_word_fixes:
            w, py = others_word_fixes[w]
            stats["fixed_word_or_trad"] += 1
        if (w, py) in others_py_fixes:
            py = others_py_fixes[(w, py)]
            stats["fixed_py"] += 1
        if (w, py) in tolerance_reweight:
            new_wt = str(tolerance_reweight[(w, py)])
            if wt != new_wt:
                wt = new_wt
                stats["reweighted"] += 1
        seen.add((w, py))
        out.append(format_entry(w, py, wt, extra))

    additions = [
        ("蚌住", "beng zhu", "0"),
        ("我勒个", "wo le ge", "0"),
        ("软弹", "ruan tan", "0"),
    ]
    to_add = [(w, py, wt) for (w, py, wt) in additions if (w, py) not in seen]
    if to_add:
        out.append("# 补充常用口语词")
        for w, py, wt in to_add:
            out.append(f"{w}\t{py}\t{wt}")
            stats["added"] += 1
    return out


# Calibrated positive weights for common mispronunciations / habits in corrections.dict.yaml:
# - Zero/rare-collision codes rank #1 with [corrector] hint (50-350)
# - Real-word collision codes sit right below the #1 legitimate word (page-1 #2/#3, 1-key ';' selectable)
CORRECTIONS_WEIGHTS: dict[tuple[str, str], int] = {
    # Tier 1: zero/rare collision -> #1 with gentle hint
    ("角色", "jiao se"): 200,
    ("模板", "mo ban"): 200,
    ("模样", "mo yang"): 200,
    ("一模一样", "yi mo yi yang"): 200,
    ("有模有样", "you mo you yang"): 100,
    ("装模作样", "zhuang mo zuo yang"): 100,
    ("人模狗样", "ren mo gou yang"): 100,
    ("模具", "mo ju"): 150,
    ("给予", "gei yu"): 200,
    ("关卡", "guan ka"): 200,
    ("供给", "gong gei"): 200,
    ("卡脖子", "ka bo zi"): 150,
    ("藤蔓", "teng man"): 150,
    ("抹布", "mo bu"): 350,
    ("下调", "xia diao"): 150,
    ("躯壳", "qu ke"): 150,
    ("裸露", "luo lou"): 150,
    ("深藏不露", "shen cang bu lou"): 100,
    ("魔爪", "mo zhua"): 150,
    ("爪哇", "zhua wa"): 100,
    ("强劲", "qiang jin"): 150,
    ("埋怨", "mai yuan"): 150,
    ("槟榔", "bin lang"): 150,
    ("木讷", "mu na"): 100,
    ("偌大", "nuo da"): 100,
    ("脖颈", "bo jing"): 100,
    ("暖和", "nuan he"): 150,
    ("结扎", "jie zha"): 100,
    ("调换", "tiao huan"): 100,
    ("掺和", "chan he"): 150,
    ("掺和", "can huo"): 100,
    ("厚朴", "hou pu"): 50,
    ("龇牙", "ci ya"): 50,
    ("殷红", "yin hong"): 100,
    ("应该", "yin gai"): 200,
    ("粘贴", "nian tie"): 150,
    ("优惠券", "you hui juan"): 150,
    ("烘焙", "hong pei"): 150,
    ("曾经", "ceng jin"): 150,
    ("凑合", "cou huo"): 150,
    ("崩溃", "ben kui"): 150,
    ("仿佛", "fang fo"): 150,
    ("按捺", "an nai"): 100,
    ("按捺不住", "an nai bu zhu"): 150,
    ("血脉偾张", "xue mai pen zhang"): 100,
    ("契诃夫", "qi ke fu"): 100,
    ("螺蛳粉", "luo shi fen"): 150,
    ("摩羯座", "mo xie zuo"): 100,
    ("刹那", "sha na"): 100,
    ("一刹那", "yi sha na"): 100,
    ("吐蕃", "tu fan"): 50,
    ("泊松分布", "po song fen bu"): 50,
    ("便宜坊", "pian yi fang"): 50,
    ("镀铬", "du luo"): 50,
    ("张柏芝", "zhang bai zhi"): 100,
    ("鸭绿江", "ya lv jiang"): 100,
    ("雪佛兰", "xue fo lan"): 100,
    ("贾平凹", "jia ping ao"): 100,
    ("阿弥陀佛", "a mi tuo fo"): 100,
    ("荨麻", "xun ma"): 80,
    ("荨麻疹", "qian ma zhen"): 80,
    ("草薙", "cao zhi"): 50,
    ("草薙京", "cao zhi jing"): 80,
    ("太行山", "tai xing shan"): 100,
    ("歇斯底里", "jie si di li"): 100,
    ("模棱两可", "mo ling liang ke"): 100,
    ("鄱阳湖", "pan yang hu"): 100,
    ("海参崴", "hai shen wei"): 100,
    ("头皮屑", "tou pi xue"): 100,
    ("心宽体胖", "xin kuan ti pang"): 100,
    ("虚与委蛇", "xu yu wei she"): 100,
    ("大腹便便", "da fu bian bian"): 100,
    ("力能扛鼎", "li neng kang ding"): 50,
    ("独乐乐", "du le le"): 50,
    ("众乐乐", "zhong le le"): 50,
    ("角斗士", "jiao dou shi"): 80,
    ("高句丽", "gao ju li"): 80,
    ("哺乳", "pu ru"): 80,
    ("脑卒中", "nao zu zhong"): 80,
    ("六合区", "liu he qu"): 50,
    ("南京六合", "nan jing liu he"): 50,
    # Tier 2: real-word collision -> #2/#3 on page 1 behind #1 legitimate word
    ("主角", "zhu jiao"): 1000,       # 助教 2210 #1 | 主角 #2 | 主教 645
    ("说服", "shui fu"): 500,         # 税负 1052 #1 | 说服 #2 | 税赋 239
    ("馄饨", "hun dun"): 500,         # 混沌 2615 #1 | 馄饨 #2
    ("道行", "dao hang"): 500,        # 导航 3481 #1 | 道行 #2
    ("比萨", "pi sa"): 300,           # 披萨 1825 #1 | 比萨 #2
    ("弄堂", "nong tang"): 150,       # 浓汤 273  #1 | 弄堂 #2
    ("胴体", "tong ti"): 280,         # 通体 330  #1 | 胴体 #2 | 酮体 260
    ("补给", "bu gei"): 500,          # 不给 6605 #1 | 补给 #2
    ("游说", "you shuo"): 800,        # 又说 2507 #1 | 有说 1338 | 游说 #3
    ("单薄", "dan bao"): 800,         # 担保 3213 #1 | 单薄 #2
    ("轻薄", "qing bao"): 800,        # 情报 2913 #1 | 轻薄 #2
    ("外露", "wai lou"): 150,         # 歪楼 227  #1 | 外露 #2
    ("脉脉", "mai mai"): 500,         # 买卖 5588 #1 | 脉脉 #2
    ("扛鼎", "kang ding"): 50,        # 康定      #1 | 扛鼎 #2
    ("薄膜", "bao mo"): 80,           # 包膜 137  #1 | 薄膜 #2
    ("刘禅", "liu chan"): 300,        # 流产 822  #1 | 刘禅 #2
    ("吱声", "zhi sheng"): 800,       # 只剩 3982 #1 | 吱声 #2
    ("掺和", "can he"): 110,          # 餐盒 139  #1 | 掺和 #2 | 参合 103
    ("称职", "cheng zhi"): 300,       # 橙汁 441  #1 | 称职 #2
    ("发酵", "fa xiao"): 500,         # 发小 1032 #1 | 发酵 #2
    ("阈值", "fa zhi"): 850,          # 法治 1023 #1 | 阈值 #2
    ("六安", "liu an"): 150,          # 刘安 347  #1 | 六安 #2
}


def clean_corrections(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    seen = set()
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        # Broken homophone + wrong zhang
        if w == "源远流长" and py == "yuan yuan liu zhang":
            stats["deleted_wrong_py"] += 1
            continue
        # Triggers on exact correct pinyin
        if w == "㹴犬" and py == "geng quan":
            stats["deleted_wrong_py"] += 1
            continue
        # Contradicts 血脉偾张
        if w == "血脉贲张" and py == "xue mai pen zhang":
            stats["deleted_noise_or_typo"] += 1
            continue
        if w == "血脉偾张" and py == "xue mai pen zhang" and extra != ["血脉喷张 | 血脉偾(fèn)张"]:
            extra = ["血脉喷张 | 血脉偾(fèn)张"]
            stats["fixed_comment"] += 1
        if w == "咖喱" and py == "ka li" and extra != ["咖(gā)喱(lí)"]:
            extra = ["咖(gā)喱(lí)"]
            stats["fixed_comment"] += 1
        if w == "仿佛" and py == "pang fo" and extra != ["仿(fǎng)佛(fú)"]:
            extra = ["仿(fǎng)佛(fú)"]
            stats["fixed_comment"] += 1
        if (w, py) in CORRECTIONS_WEIGHTS:
            new_wt = str(CORRECTIONS_WEIGHTS[(w, py)])
            if wt != new_wt:
                wt = new_wt
                stats["reweighted"] += 1
        seen.add((w, py))
        out.append(format_entry(w, py, wt, extra))

    # Calibrated common mispronunciation & habit entries
    additions = [
        ("仿佛", "fang fo", "150", "仿(fǎng)佛(fú)"),
        ("仿佛", "pang fu", "0", "仿(fǎng)佛(fú)"),
        ("纨绔子弟", "wan kua zi di", "0", "纨(wán)绔(kù)子弟"),
        ("比萨", "pi sa", "300", "比(bǐ)萨(sà)"),
        ("给予", "gei yu", "200", "给(jǐ)予(yǔ)"),
        ("张柏芝", "zhang bai zhi", "100", "张柏(bó)芝"),
        ("藤蔓", "teng man", "150", "藤蔓(wàn)"),
        ("吱声", "zhi sheng", "800", "吱(zī)声"),
        ("调换", "tiao huan", "100", "调(diào)换"),
        ("六安", "liu an", "150", "六(lù)安"),
        ("六合区", "liu he qu", "50", "六(lù)合区"),
        ("南京六合", "nan jing liu he", "50", "南京六(lù)合"),
        ("关卡", "guan ka", "200", "关(guān)卡(qiǎ)"),
        ("供给", "gong gei", "200", "供(gōng)给(jǐ)"),
        ("补给", "bu gei", "500", "补(bǔ)给(jǐ)"),
        ("抹布", "mo bu", "350", "抹(mā)布"),
        ("游说", "you shuo", "800", "游(yóu)说(shuì)"),
        ("下调", "xia diao", "150", "下调(tiáo)"),
        ("单薄", "dan bao", "800", "单薄(bó)"),
        ("轻薄", "qing bao", "800", "轻薄(bó)"),
        ("躯壳", "qu ke", "150", "躯壳(qiào)"),
        ("裸露", "luo lou", "150", "裸露(lù)"),
        ("外露", "wai lou", "150", "外露(lù)"),
        ("深藏不露", "shen cang bu lou", "100", "深藏不露(lù)"),
        ("魔爪", "mo zhua", "150", "魔爪(zhǎo)"),
        ("爪哇", "zhua wa", "100", "爪(zhǎo)哇"),
        ("脉脉", "mai mai", "500", "脉(mò)脉"),
        ("扛鼎", "kang ding", "50", "扛(gāng)鼎"),
        ("薄膜", "bao mo", "80", "薄(bó)膜"),
        ("刘禅", "liu chan", "300", "刘禅(shàn)"),
        ("吐蕃", "tu fan", "50", "吐蕃(bō)"),
        ("泊松分布", "po song fen bu", "50", "泊(bó)松分布"),
        ("便宜坊", "pian yi fang", "50", "便(biàn)宜坊"),
        ("镀铬", "du luo", "50", "镀铬(gè)"),
        ("凑合", "cou huo", "150", "凑活(合he)"),
        ("契诃夫", "qi ke fu", "100", "契科(诃hē)夫"),
    ]
    to_add = [(w, py, wt, cmt) for (w, py, wt, cmt) in additions if (w, py) not in seen]
    if to_add:
        out.append("# 常用易错音与习惯读音提示")
        for w, py, wt, cmt in to_add:
            out.append(f"{w}\t{py}\t{wt}\t{cmt}")
            seen.add((w, py))
            stats["added"] += 1
    return out


def clean_food(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    poi_span = find_entry_span(body, ("阿巴尼", "a ba ni"), ("昨重", "zuo zhong"), next_word="阿宝面")
    out = list(hdr)
    braise_markers = ("扒菜", "扒鸡", "扒鸭", "扒鱼", "扒肉", "扒肘", "扒翅", "扒鲍", "扒海", "扒豆腐", "扒白菜", "扒菇")
    word_fixes = {
        "玫瑰凉糕": ("玫瑰凉糕", "mei gui liang gao"),
        "东江酿豆付": ("东江酿豆腐", "dong jiang niang dou fu"),
        "东譬龙珠": ("东壁龙珠", "dong bi long zhu"),
    }
    py_fixes = {
        ("芫爆肚丝", "yuan bao du si"): "yan bao du si",
        ("劲爆鸡米花", "jing bao ji mi hua"): "jin bao ji mi hua",
        ("煲仔鱼丸", "bao zi yu wan"): "bao zai yu wan",
        ("贝丝扒菜胆", "bei si ba cai dan"): "bei si pa cai dan",
        ("奶油扒菜芯", "nai you ba cai xin"): "nai you pa cai xin",
    }
    for offset, line in enumerate(body):
        if poi_span and poi_span[0] <= offset <= poi_span[1]:
            if parse_entry(line):
                stats["deleted_poi_dump"] += 1
            continue
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in word_fixes:
            w, py = word_fixes[w]
            stats["fixed_word_or_trad"] += 1
        if (w, py) in py_fixes:
            py = py_fixes[(w, py)]
            stats["fixed_py"] += 1
        # Fix 粿 hua -> guo
        new_py = replace_syl_at(w, py, "粿", "hua", "guo")
        if new_py != py:
            py = new_py
            stats["fixed_py"] += 1
        # Fix 参 can -> shen in dishes (ginseng / sea cucumber)
        new_py = replace_syl_at(w, py, "参", "can", "shen")
        if new_py != py:
            py = new_py
            stats["fixed_py"] += 1
        # Fix culinary braising 扒 ba -> pa
        if any(m in w for m in braise_markers):
            new_py = replace_syl_at(w, py, "扒", "ba", "pa")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_place(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    hk_span = find_entry_span(body, ("欣澳", "xin ao"), ("烏溪沙", "wu xi sha"))
    dump_span = find_entry_span(body, ("分洪区", "fen hong qu"), ("鼠白胜处", "shu bai sheng chu"))
    out = list(hdr)

    untypable_re = re.compile(r"[0-9A-Z()]")
    explicit_fixes = {
        ("什刹海", "shen sha hai"): "shi cha hai",
        ("小什字", "xiao shen zi"): "xiao shi zi",
        ("沃罗涅什", "wo luo nie shen"): "wo luo nie shi",
        ("萨勒赫城", "sa lei he cheng"): "sa le he cheng",
        ("马家堡", "ma jia bao"): "ma jia pu",
        ("饶乐府", "rao yue fu"): "rao le fu",
        ("七莘路", "qi shen lu"): "qi xin lu",
        ("虹莘路", "hong shen lu"): "hong xin lu",
        ("区庄", "qu zhuang"): "ou zhuang",
        ("黄陂", "huang pi"): "huang bei",
        ("民乐", "min yue"): "min le",
        ("长岭陂", "zhang ling bei"): "chang ling pi",
        ("沌阳大道", "dun yang da dao"): "zhuan yang da dao",
        ("谌家矶", "chen jia ji"): "shen jia ji",
        ("大王庄", "dai wang zhuang"): "da wang zhuang",
        ("大王基", "dai wang ji"): "da wang ji",
        ("六合开发区", "liu he kai fa qu"): "lu he kai fa qu",
        ("石湫", "shi jiao"): "shi qiu",
        ("尖沙咀", "jian sha ju"): "jian sha zui",
        ("石咀", "shi ju"): "shi zui",
        ("调景岭", "diao jing ling"): "tiao jing ling",
        ("曾家岩", "ceng jia yan"): "zeng jia yan",
        ("川藏立交", "chuan cang li jiao"): "chuan zang li jiao",
        ("龙爪堰", "long zhao yan"): "long zhua yan",
        ("大差市", "da cha shi"): "da chai shi",
        ("宝幢", "bao chuang"): "bao zhuang",
        ("查桥", "cha qiao"): "zha qiao",
        ("蛤地", "ha di"): "ge di",
        ("闵行开发区", "min xing kai fa qu"): "min hang kai fa qu",
        ("刘行", "liu xing"): "liu hang",
        ("小行", "xiao xing"): "xiao hang",
        ("河海大学·佛城西路", "he hai da xue fu cheng xi lu"): "he hai da xue fo cheng xi lu",
    }
    chang_words = {
        "长椿街", "长阳", "长清路", "汉溪长隆", "长湴", "长港路", "长岭山",
        "长芦", "长沙湾", "长福路", "长影世纪城", "长广溪", "长淮",
    }
    du_words = {"银都路", "花都广场", "花都汽车城", "梦都大街", "广都", "航都大街"}
    xia_words = {"厦滘", "岗厦", "湾厦", "岗厦北", "石厦", "江厦桥东", "寮厦"}
    fo_words = {"佛图关", "佛子岭", "白佛"}
    chao_words = {"朝阳门", "朝阳公园", "朝阳", "朝阳桥", "朝阳山", "朝阳广场"}
    chong_words = {"低涌", "东涌", "大涌", "沙涌", "鲗鱼涌"}

    for offset, line in enumerate(body):
        if dump_span and dump_span[0] <= offset <= dump_span[1]:
            if parse_entry(line):
                stats["deleted_suffix_dump"] += 1
            continue
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        # Drop untypable ASCII digit / paren / uppercase codes
        if untypable_re.search(py):
            stats["deleted_untypable"] += 1
            continue
        # Convert HK MTR Traditional block
        if hk_span and hk_span[0] <= offset <= hk_span[1]:
            sim_w = CC_T2S.convert(w)
            if sim_w != w:
                w = sim_w
                stats["fixed_word_or_trad"] += 1
        # Explicit fixes
        if (w, py) in explicit_fixes:
            py = explicit_fixes[(w, py)]
            stats["fixed_py"] += 1
        if w in chang_words:
            new_py = replace_syl_at(w, py, "长", "zhang", "chang")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if w in du_words:
            new_py = replace_syl_at(w, py, "都", "dou", "du")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if w in xia_words:
            new_py = replace_syl_at(w, py, "厦", "sha", "xia")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if w in fo_words:
            new_py = replace_syl_at(w, py, "佛", "fu", "fo")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if w in chao_words:
            new_py = replace_syl_at(w, py, "朝", "zhao", "chao")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if w in chong_words:
            new_py = replace_syl_at(w, py, "涌", "yong", "chong")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        # Fix 民乐 weight inflation (716 was from folk music min yue)
        if w == "民乐" and py == "min le":
            wt = "20"
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_chess2(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    sec3_span = find_entry_span(body, ("八平", "ba ping"), ("卒五个", "zu wu ge"), next_word="八卒")
    out = list(hdr)
    trad_pieces = re.compile(r"[車俥馬傌砲將帥]")
    move_re = re.compile(r"(车|前车|后车|中车).*(进|退|平)")
    delete_words = {
        "黑进路卒转中炮对屏风马", "黑弃路卒", "象棋实战精妙杀法例",
        "中国象棋兵法种", "中国象棋入门与提高问答",
    }
    word_fixes = {
        "葛维浦": ("葛维蒲", "ge wei pu"),
        "双闲酒杯": ("双献酒杯", "shuang xian jiu bei"),
        "中炮过和车对屏风马横车": ("中炮过河车对屏风马横车", "zhong pao guo he ju dui ping feng ma heng ju"),
    }
    py_fixes = {
        ("边马对还中炮", "bian ma dui hai zhong pao"): "bian ma dui huan zhong pao",
        ("二打二还打", "er da er hai da"): "er da er huan da",
        ("二将二还将", "er jiang er hai jiang"): "er jiang er huan jiang",
        ("过宫炮对还中炮", "guo gong pao dui hai zhong pao"): "guo gong pao dui huan zhong pao",
        ("还中炮", "hai zhong pao"): "huan zhong pao",
        ("挺兵对还中炮", "ting bing dui hai zhong pao"): "ting bing dui huan zhong pao",
        ("卜凤波", "bo feng bo"): "bu feng bo",
        ("单霞丽", "dan xia li"): "shan xia li",
        ("落子无悔", "lao zi wu hui"): "luo zi wu hui",
        ("审局度势", "shen ju du shi"): "shen ju duo shi",
        ("算度深远", "suan du shen yuan"): "suan duo shen yuan",
        ("象棋业余陆级", "xiang qi ye yu lu ji"): "xiang qi ye yu liu ji",
        ("运调", "yun tiao"): "yun diao",
    }
    reweight = {
        ("起着", "qi zhao"): 20,
        ("闲着", "xian zhao"): 20,
        ("停着", "ting zhao"): 10,
        ("应着", "ying zhao"): 10,
    }
    existing = set()
    for line in body:
        p = parse_entry(line)
        if p:
            existing.add((p[0], normalize_lue_nue(p[1])))
    ju_additions = []
    for offset, line in enumerate(body):
        if sec3_span and sec3_span[0] <= offset <= sec3_span[1]:
            if parse_entry(line):
                stats["deleted_ngram_garbage"] += 1
            continue
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if trad_pieces.search(w):
            stats["deleted_trad_piece"] += 1
            continue
        if w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if w in word_fixes:
            w, py = word_fixes[w]
            stats["fixed_word_or_trad"] += 1
        if (w, py) in py_fixes:
            py = py_fixes[(w, py)]
            stats["fixed_py"] += 1
        if (w, py) in reweight:
            new_wt = str(reweight[(w, py)])
            if wt != new_wt:
                wt = new_wt
                stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
        if move_re.search(w) and "che" in py.split():
            ju_py = replace_syl_at(w, py, "车", "che", "ju")
            if ju_py != py and (w, ju_py) not in existing:
                ju_additions.append(format_entry(w, ju_py, wt, extra))
                existing.add((w, ju_py))
    if ju_additions:
        out.append("# 象棋「车」标准 ju 读音")
        out.extend(ju_additions)
        stats["added"] += len(ju_additions)
    return out


def clean_chess(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    existing = set()
    for line in body:
        p = parse_entry(line)
        if p:
            existing.add((p[0], normalize_lue_nue(p[1])))
    out = list(hdr)
    ju_additions = []
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in ("双车挫", "双車挫"):
            stats["deleted_noise_or_typo"] += 1
            continue
        if w == "太监追黄帝":
            w, py = "太监追皇帝", "tai jian zhui huang di"
            stats["fixed_word_or_trad"] += 1
        elif w == "双车协士":
            w, py = "双车胁士", "shuang ju xie shi"
            stats["fixed_word_or_trad"] += 1
        elif (w, py) == ("送佛归殿", "song fu gui dian"):
            py = "song fo gui dian"
            stats["fixed_py"] += 1
        elif (w, py) == ("长连禁手", "zhang lian jin shou"):
            py = "chang lian jin shou"
            stats["fixed_py"] += 1
        elif (w, py) == ("长星", "zhang xing"):
            py = "chang xing"
            stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
        if "车" in w and "che" in py.split():
            ju_py = replace_syl_at(w, py, "车", "che", "ju")
            if ju_py != py and (w, ju_py) not in existing:
                ju_additions.append(format_entry(w, ju_py, wt, extra))
                existing.add((w, ju_py))
    if ju_additions:
        out.append("# 象棋「车」标准 ju 读音")
        out.extend(ju_additions)
        stats["added"] += len(ju_additions)
    return out


def clean_geography(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    de_to_di_words = {
        "初始地应力", "发展地理学", "反射地震波法", "技术地理学", "机械地震源",
        "历史地图集", "民族地理学", "模拟地震动", "普通地理学", "普通地图集",
        "普通地图学", "潜在地震区", "软地幔", "医学地理学", "中心地学说", "综合地图集",
    }
    py_fixes = {
        ("句章", "ju zhang"): "gou zhang",
        ("莎车国", "sha che guo"): "suo che guo",
        ("沙羡", "sha xian"): "sha yi",
        ("酰罗城", "xian luo cheng"): "xi luo cheng",
        ("酰罗山", "xian luo shan"): "xi luo shan",
        ("阳夏", "yang xia"): "yang jia",
        ("冤句", "yuan ju"): "yuan qu",
        ("朱提", "zhu ti"): "shu shi",
        ("冰川补给", "bing chuan bu gei"): "bing chuan bu ji",
        ("补给区", "bu gei qu"): "bu ji qu",
        ("给水度", "gei shui du"): "ji shui du",
        ("薄煤层", "bo mei ceng"): "bao mei ceng",
        ("不称河", "bu cheng he"): "bu chen he",
        ("城市蔓生", "cheng shi wan sheng"): "cheng shi man sheng",
        ("巨大都会带", "ju da dou hui dai"): "ju da du hui dai",
        ("累积频数曲线", "lei ji pin shuo qu xian"): "lei ji pin shu qu xian",
        ("挽近地壳运动", "wan jin di ke yun dong"): "wan jin di qiao yun dong",
    }
    word_fixes = {
        "波所黎各": ("波多黎各", "bo duo li ge"),
        "地图编缉": ("地图编辑", "di tu bian ji"),
        "扭称": ("扭秤", "niu cheng"),
        "彭纳没影": ("彭纳投影", "peng na tou ying"),
        "仙女木时间": ("仙女木事件", "xian nv mu shi jian"),
    }
    delete_words = {
        "形谷", "勘察加火", "大陆车阀说", "叙利至沙洛呐", "有方廷斯",
        "霍拉圣巴拉巴", "佩乔尔斯克院", "两座老城", "地形要素划分标准及分值表", "地学知识介绍牌",
    }
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if w in word_fixes:
            w, py = word_fixes[w]
            stats["fixed_word_or_trad"] += 1
        if w in de_to_di_words:
            new_py = replace_syl_at(w, py, "地", "de", "di")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if (w, py) in py_fixes:
            py = py_fixes[(w, py)]
            stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_industry_product(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    new_hdr = [
        ("name: industry_product" if l.strip() == "name: alibaba_product" else l)
        for l in hdr
    ]
    out = list(new_hdr)
    delete_words = {
        "型荧光灯管", "型扳手", "烙铁咀",
        "永奇昱祥", "乾祥", "乾祥服饰", "乾祥服饰旗舰店", "乔丹篮球鞋",
        "裳尚芊", "炎焱妖", "炎焱妖服饰", "多款供选", "博缘轩貔貅",
        "家用竹", "塑料桶罐", "纸桶罐", "烟灰缸袋", "墨盒水",
    }
    word_fixes = {
        "冷墩钢": ("冷镦钢", "leng dun gang"),
        "耐侯钢": ("耐候钢", "nai hou gang"),
        "晴纶围巾": ("腈纶围巾", "jing lun wei jin"),
        "摇立绒手套": ("摇粒绒手套", "yao li rong shou tao"),
        "粉粹机": ("粉碎机", "fen sui ji"),
    }
    py_fixes = {
        ("模切机", "mu qie ji"): "mo qie ji",
        ("热轧板卷", "re ya ban juan"): "re zha ban juan",
        ("仪表壳体", "yi biao qiao ti"): "yi biao ke ti",
        ("壳体加工", "qiao ti jia gong"): "ke ti jia gong",
        ("甲壳素纤维", "jia ke su xian wei"): "jia qiao su xian wei",
        ("隔离栅", "ge li shan"): "ge li zha",
        ("呢类系列", "ne lei xi lie"): "ni lei xi lie",
        ("平纹呢", "ping wen ne"): "ping wen ni",
        ("扎染布", "zha ran bu"): "za ran bu",
        ("扎带", "zha dai"): "za dai",
        ("扎把机", "zha ba ji"): "za ba ji",
        ("扎口机", "zha kou ji"): "za kou ji",
        ("伺服阀", "ci fu fa"): "si fu fa",
        ("伺服定位系统", "ci fu ding wei xi tong"): "si fu ding wei xi tong",
        ("密封垫圈", "mi feng dian juan"): "mi feng dian quan",
        ("切削电动工具", "qie xiao dian dong gong ju"): "qie xue dian dong gong ju",
        ("重氮化合物", "zhong dan hua he wu"): "chong dan hua he wu",
        ("曝气设备", "bao qi she bei"): "pu qi she bei",
    }
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        # Strip 1688 UI boilerplate
        if (
            w.startswith(("其他", "其它", "二手", "库存"))
            or w.endswith(("代理", "项目合作"))
            or w in delete_words
        ):
            stats["deleted_boilerplate_or_spam"] += 1
            continue
        if w in word_fixes:
            w, py = word_fixes[w]
            stats["fixed_word_or_trad"] += 1
        if w.endswith("匙扣"):
            new_py = replace_syl_at(w, py, "匙", "chi", "shi")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if (w, py) in py_fixes:
            py = py_fixes[(w, py)]
            stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_shulihua(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    tw_span = find_entry_span(body, ("愛殺松", "ai sha song"), ("重鉻酸鈉", "zhong ge suan na"))
    news_span = find_entry_span(body, ("阿拉斯加上空", "a la si jia shang kong"), ("左右的结果", "zuo you de jie guo"))
    out = list(hdr)
    py_fixes = {
        ("和厚朴酚", "he hou pu fen"): None,
        ("行向量", "xing xiang liang"): "hang xiang liang",
        ("子模型", "zi mu xing"): "zi mo xing",
        ("脯氨酸", "fu an suan"): "pu an suan",
        ("胡罗卜素", "hu luo bu su"): None,
        ("没药醇", "mei yao chun"): None,
        ("单丁基氧化锡", "shan ding ji yang hua xi"): None,
        ("重铬酸钾", "zhong ge suan jia"): "chong ge suan jia",
        ("重铬酸铵", "zhong ge suan an"): "chong ge suan an",
        ("重铬酸钠", "zhong ge suan na"): "chong ge suan na",
        ("重氮甲烷", "zhong dan jia wan"): "chong dan jia wan",
        ("还原型辅酶", "hai yuan xing fu mei"): None,
        ("茄碱度", "jia jian du"): None,
        ("茄尼醇", "jia ni chun"): None,
        ("茄替胶", "jia ti jiao"): None,
        ("硫酸多粘菌素", "liu suan duo zhan jun su"): None,
        ("羟脯氨酸", "qiang fu an suan"): "qiang pu an suan",
        ("消旋山莨菪碱", "xiao xuan shan liang dang jian"): None,
        ("乙炔发生器", "yi gui fa sheng qi"): "yi que fa sheng qi",
        ("苯胺红", "ben an gong"): "ben an hong",
    }
    word_fixes = {
        "胡罗卜素": ("胡萝卜素", "hu luo bo su"),
        "三角架": ("三脚架", "san jiao jia"),
        "菸硷": ("烟碱", "yan jian"),
        "异菸肼": ("异烟肼", "yi yan jing"),
        "葡聚糖凝膠": ("葡聚糖凝胶", "pu ju tang ning jiao"),
    }
    reweight = {"标碳烷": 5, "标键烷": 5, "水磁双阻": 5, "赛罗": 100}
    for offset, line in enumerate(body):
        if news_span and news_span[0] <= offset <= news_span[1]:
            if parse_entry(line):
                stats["deleted_news_block"] += 1
            continue
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if tw_span and tw_span[0] <= offset <= tw_span[1]:
            sim_w = CC_T2S.convert(w)
            if sim_w != w:
                w = sim_w
                stats["fixed_word_or_trad"] += 1
        if w in ("滴滴滴", "同担"):
            stats["deleted_noise_or_typo"] += 1
            continue
        if w in word_fixes:
            w, py = word_fixes[w]
            stats["fixed_word_or_trad"] += 1
        if (w, py) in py_fixes:
            new_py = py_fixes[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        if w in reweight:
            wt = str(reweight[w])
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_medication(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    ad_span = find_entry_span(body, ("百香", "bai xiang"), ("左旋维生素", "zuo xuan wei sheng su"), next_word="百香御")
    out = list(hdr)

    # All verified medication fixes & DELETE_DUPs from c1b5d1b8 Parts 1 & 2 + c8d9c24d
    med_py_fixes = {
        ("蓝圆鲹", "lan yuan can"): "lan yuan shen",
        ("缗钱状", "mian qian zhuang"): "min qian zhuang",
        ("江西樟树化工厂维生素分厂", "jiang xi zhang shu hua gong chang wei sheng e fen chang"): "jiang xi zhang shu hua gong chang wei sheng su fen chang",
        ("賫百年之寿命", "lai bai nian zhi shou ming"): None,
        ("薄膜", "bao mo"): None,
        ("薄膜包衣预混剂", "bao mo bao yi yu hun ji"): "bo mo bao yi yu hun ji",
        ("甲杓肌", "jia biao ji"): "jia shao ji",
        ("乐派", "yue pai"): "le pai",
        ("乐沙定", "yue sha ding"): "le sha ding",
        ("白参", "bai can"): "bai shen",
        ("独参汤", "du can tang"): "du shen tang",
        ("生晒参", "sheng shai can"): "sheng shai shen",
        ("土人参", "tu ren can"): "tu ren shen",
        ("元参", "yuan can"): "yuan shen",
        ("参附注射液", "can fu zhu she ye"): "shen fu zhu she ye",
        ("参桂理中丸", "can gui li zhong wan"): "shen gui li zhong wan",
        ("参苓", "can ling"): "shen ling",
        ("参苓白术丸", "can ling bai zhu wan"): "shen ling bai zhu wan",
        ("参杞", "can qi"): "shen qi",
        ("参松养心胶囊", "can song yang xin jiao nang"): "shen song yang xin jiao nang",
        ("肺栓塞", "fei shuan sai"): "fei shuan se",
        ("动脉栓塞", "dong mai shuan sai"): "dong mai shuan se",
        ("脑栓塞", "nao shuan sai"): "nao shuan se",
        ("血栓栓塞", "xue shuan shuan sai"): "xue shuan shuan se",
        ("还原型辅酶", "hai yuan xing fu mei"): "huan yuan xing fu mei",
        ("还原型谷胱甘肽", "hai yuan xing gu guang gan tai"): "huan yuan xing gu guang gan tai",
        ("术数", "zhu shu"): "shu shu",
        ("功能固着", "gong neng gu zhe"): "gong neng gu zhuo",
        ("厚朴", "hou pu"): "hou po",
        ("疗养地", "liao yang de"): "liao yang di",
        ("膻中", "shan zhong"): "dan zhong",
        ("膻中穴", "shan zhong xue"): "dan zhong xue",
        ("射干", "she gan"): "ye gan",
        ("颜色饱和度", "yan shai bao he du"): "yan se bao he du",
        ("柞蚕蛹", "zuo can yong"): "zha can yong",
        ("酢浆草", "zuo jiang cao"): "cu jiang cao",
        ("没药", "mei yao"): "mo yao",
        ("神藏", "shen zang"): "shen cang",
        ("陈香露白露", "chen xiang lou bai lu"): "chen xiang lu bai lu",
        ("陈香露白露片", "chen xiang lou bai lu pian"): "chen xiang lu bai lu pian",
        ("陈香露白露胶囊", "chen xiang lou bai lu jiao nang"): None,
        ("脯氨酸", "fu an suan"): "pu an suan",
        ("羟脯氨酸", "qiang fu an suan"): "qiang pu an suan",
        ("士的宁", "shi de ning"): "shi di ning",
        ("粘蛋白", "zhan dan bai"): "nian dan bai",
        ("重铬酸钾", "zhong ge suan jia"): "chong ge suan jia",
        ("重吸收", "zhong xi shou"): "chong xi shou",
        ("口角", "kou jue"): "kou jiao",
        ("克什克腾", "ke shen ke teng"): "ke shi ke teng",
        ("利什曼原虫", "li shen man yuan chong"): "li shi man yuan chong",
        ("流调人员", "liu tiao ren yuan"): "liu diao ren yuan",
        ("输精管结扎术", "shu jing guan jie zha shu"): "shu jing guan jie za shu",
        ("急性荨麻疹", "ji xing qian ma zhen"): "ji xing xun ma zhen",
        ("荨麻疹", "qian ma zhen"): None,
        ("肋间神经", "le jian shen jing"): None,
        ("股薄肌", "gu bao ji"): None,
        ("脊髓型颈椎病", "ji sui xing jing chui bing"): None,
    }
    med_delete_dups = {
        # Bug A参 dups
        ("参苓白术扁豆陈", "can ling bai zhu bian dou chen"),
        ("参苓白术颗粒", "can ling bai zhu ke li"),
        ("干姜甘草与人参", "gan jiang gan cao yu ren can"),
        ("猫人参", "mao ren can"),
        ("墨元参", "mo yuan can"),
        ("全须生晒参", "quan xu sheng shai can"),
        ("生脉麦味与人参", "sheng mai mai wei yu ren can"),
        ("实者枳壳易人参", "shi zhe zhi ke yi ren can"),
        ("参苓白术胶囊", "can ling bai zhu jiao nang"),
        ("参苓白术口服液", "can ling bai zhu kou fu ye"),
        ("参苓白术片", "can ling bai zhu pian"),
        ("丹参保心茶", "dan can bao xin cha"),
        ("人参保肺", "ren can bao fei"),
        ("人参保肺丸", "ren can bao fei wan"),
        # Bug B 俞=yu dups
        ("白环俞穴", "bai huan yu xue"), ("胆俞穴", "dan yu xue"), ("督俞穴", "du yu xue"),
        ("肩外俞穴", "jian wai yu xue"), ("肩中俞穴", "jian zhong yu xue"), ("经络府俞", "jing luo fu yu"),
        ("巨阙俞", "ju que yu"), ("胃脘下俞", "wei wan xia yu"), ("下极俞", "xia ji yu"),
        ("心俞穴", "xin yu xue"), ("腰俞穴", "yao yu xue"), ("中膂俞", "zhong lv yu"),
        ("关元俞穴", "guan yuan yu xue"), ("厥阴俞穴", "jue yin yu xue"),
        ("气海俞穴", "qi hai yu xue"), ("三焦俞穴", "san jiao yu xue"),
        # Bug C 塞 dups
        ("栓塞材料", "shuan sai cai liao"), ("鼻塞病", "bi sai bing"), ("伤风鼻塞病", "shang feng bi sai bing"),
        ("肾动脉栓塞", "shen dong mai shuan sai"), ("肾动脉栓塞术", "shen dong mai shuan sai shu"),
        ("肠系膜栓塞", "chang xi mo shuan sai"), ("血块栓塞", "xie kuai shuan sai"),
        ("痔疮栓塞", "zhi chuang shuan sai"), ("肢体栓塞", "zhi ti shuan sai"),
        ("一次性使用导光鼻塞", "yi ci xing shi yong dao guang bi se"),
        ("一次性使用输氧管输出管加鼻塞", "yi ci xing shi yong shu yang guan shu chu guan jia bi se"),
        # Bug D 还原型 dups
        ("还原型谷胱甘肽滴眼液", "hai yuan xing gu guang gan tai di yan ye"),
        ("还原型谷胱甘肽钠", "hai yuan xing gu guang gan tai na"),
        ("还原型谷胱甘肽片", "hai yuan xing gu guang gan tai pian"),
        ("还原型谷胱甘肽注射液", "hai yuan xing gu guang gan tai zhu she ye"),
        ("注射用还原型谷胱甘肽", "zhu she yong hai yuan xing gu guang gan tai"),
        # Bug E 术 dups
        ("泔茅术", "gan mao shu"), ("麻黄加术汤", "ma huang jia shu tang"),
        ("术附汤", "shu fu tang"), ("枳术汤", "zhi shu tang"), ("枳术丸", "zhi shu wan"),
        ("白内障针拨套出术", "bai nei zhang zhen bo tao chu zhu"),
        # Other verified dups
        ("缝扎法重睑成形术", "feng zha fa zhong jian cheng xing shu"),
        ("鹘眼凝睛病", "gu yan ning jing bing"),
        ("悸眩瞤惕急煎尝", "ji xuan shun ti ji jian chang"),
        ("埋线法重睑成形术", "mai xian fa zhong jian cheng xing shu"),
        ("切开法重睑成形术", "qie kai fa zhong jian cheng xing shu"),
        ("人禀五常以有五藏", "ren bing wu chang yi you wu cang"),
        ("受调分泌", "shou diao fen mi"),
        ("胎萎不长病", "tai wei bu chang bing"),
        ("颜色方程", "yan shai fang cheng"), ("颜色恒常性", "yan shai heng chang xing"),
        ("颜色宽容度", "yan shai kuan rong du"), ("颜色三角", "yan shai san jiao"),
        ("以有五藏", "yi you wu cang"),
        ("人造石面地柜", "ren zao shi mian de gui"),
        ("薄厥病", "bao jue bing"), ("高风雀目病", "gao feng qiao mu bing"),
        ("天行赤眼病", "tian hang chi yan bing"), ("天行赤眼暴翳病", "tian hang chi yan bao yi bing"),
        ("神藏穴", "shen zang xue"),
        ("氨来呫诺", "an lai che nuo"), ("氨来呫诺糊剂", "an lai che nuo hu ji"),
        ("楤木胃痛", "cong mu wei tong"), ("楤木胃痛颗粒", "cong mu wei tong ke li"),
        ("鸢都感冒颗粒", "yuan dou gan mao ke li"), ("鸢都寒痹药酒料", "yuan dou han bi yao jiu liao"),
        ("鸢都寒痹液", "yuan dou han bi ye"),
        ("姜汤调服止嗽频", "jiang tang diao fu zhi sou pin"),
        ("胫前着色斑", "jing qian zhe se ban"),
        ("人体对称美", "ren ti dui cheng mei"),
        ("眼用粘弹剂", "yan yong zhan dan ji"),
        ("枣汤调服益脾神", "zao tang diao fu yi pi shen"),
        ("中以保身长全", "zhong yi bao shen zhang quan"),
        ("冷荨麻疹", "leng qian ma zhen"),
        ("石荠苧", "shi ji zhu"),
    }
    word_fixes = {
        "五维他囗服溶液": ("五维他口服溶液", "wu wei ta kou fu rong ye"),
        "地尔硫艹卓": ("地尔硫䓬", "di er liu zhuo"),
        "氯氮艹卓": ("氯氮䓬", "lv dan zhuo"),
        "菸碱型受体": ("烟碱型受体", "yan jian xing shou ti"),
    }
    delete_words = {"海尔洗衣机", "海咯因检测试剂", "种氨基酸", "牛羊等", "尅伐", "派蒙"}

    # Pre-scan which medical words already have an 'xue' version so we can drop redundant 'xie' clones
    has_xue = set()
    for line in body:
        p = parse_entry(line)
        if p and "血" in p[0] and "xue" in p[1].split():
            has_xue.add(p[0])

    for offset, line in enumerate(body):
        if ad_span and ad_span[0] <= offset <= ad_span[1]:
            if parse_entry(line):
                stats["deleted_cosmetics_or_ad_dump"] += 1
            continue
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        # Drop remaining 参苓/参麦/洋参 can dups that have shen counterparts
        if (w.startswith(("参苓", "参麦", "洋参保肺")) and "can" in py.split() and w_int(wt) == 0):
            stats["deleted_wrong_py"] += 1
            continue
        if (w, py) in med_delete_dups:
            stats["deleted_wrong_py"] += 1
            continue
        if w in word_fixes:
            w, py = word_fixes[w]
            stats["fixed_word_or_trad"] += 1
        if (w, py) in med_py_fixes:
            new_py = med_py_fixes[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        # Unify xie -> xue inside medical dict (delete xie dup if xue exists, else fix)
        if "血" in w and "xie" in py.split():
            if w in has_xue:
                stats["deleted_xie_dup"] += 1
                continue
            else:
                new_py = replace_syl_at(w, py, "血", "xie", "xue")
                if new_py != py:
                    py = new_py
                    stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_game(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    va_span = find_entry_span(body, ("爱心巧克力", "ai xin qiao ke li"), ("团啊", "tuan a"))
    d3_span = find_entry_span(body, ("阿卡蘭斯之星", "a ka lan si zhi xing"), ("左克林的凝視", "zuo ke lin de ning shi"))
    out = list(hdr)
    game_py_fixes = {
        ("陶泥", "bai tao ni"): "tao ni",
        ("渡辺明乃", "du dao ming nai"): "du bian ming nai",
        ("田辺留依", "tian dao liu yi"): "tian bian liu yi",
        ("関根明良", "wan gen ming liang"): "guan gen ming liang",
        ("関根瞳", "wan gen tong"): "guan gen tong",
        ("畠中祐", "zai zhong you"): "tian zhong you",
        ("攲斜弥亘树", "yi xie mi gen shu"): "qi xie mi gen shu",
        ("奴隸鐐銬", "nu dai liao kao"): "nu li liao kao",
        ("柏咚乄", "bai dong shi"): "bai dong wu",
        ("参宿", "can su"): "shen xiu",
        ("横扫六合", "heng sao lu he"): "heng sao liu he",
        ("楞伽经", "leng jia jing"): "leng qie jing",
        ("迷云重重", "mi yun zhong zhong"): None,
        ("膻中", "shan zhong"): "dan zhong",
        ("骑兵队长", "qi bing dui chang"): "qi bing dui zhang",
        ("兰若寺", "lan ruo si"): "lan re si",
        ("千夫长", "qian fu chang"): "qian fu zhang",
        ("十夫长", "shi fu chang"): "shi fu zhang",
        ("巴尔的摩", "ba er de mo"): "ba er di mo",
        ("补给", "bu gei"): "bu ji",
        ("吐蕃", "tu fan"): None,  # base already owns tu bo 2136
        ("阿什坎迪", "a shen kan di"): "a shi kan di",
        ("阿什兰", "a shen lan"): "a shi lan",
        ("加尔鲁什", "jia er lu shen"): "jia er lu shi",
        ("角斗士", "jiao dou shi"): "jue dou shi",
        ("骑士队长", "qi shi dui chang"): "qi shi dui zhang",
        ("艾蒂安", "yi di an"): "ai di an",
        ("月神圣地废墟", "yue shen sheng de fei xu"): None,
        ("月神圣地密室", "yue shen sheng de mi shi"): None,
        ("太阿剑", "tai a jian"): "tai e jian",
        ("大宛马", "da wan ma"): "da yuan ma",
        ("天姥", "tian lao"): "tian mu",
        ("安弹", "an tan"): None,
        ("拆弹装备", "chai tan zhuang bei"): None,
        ("长乐坊", "chang yue fang"): "chang le fang",
        ("对酒行", "dui jiu hang"): None,
        ("厚朴", "hou pu"): "hou po",
        ("劲松", "jin song"): "jing song",
        ("巡逻队长", "xun luo dui chang"): "xun luo dui zhang",
        ("胆小的哥布林", "dan xiao di ge bu lin"): None,
        ("参水猿", "can shui yuan"): "shen shui yuan",
        ("迦叶", "jia ye"): "jia she",
        ("霓裳羽衣曲", "ni shang yu yi qu"): "ni chang yu yi qu",
        ("觜火猴", "zui huo hou"): "zi huo hou",
        ("传说中的勋章", "chuan shuo zhong di xun zhang"): None,
        ("十夫长的标记", "shi fu chang de biao ji"): None,
        ("还圣奥迹", "hai sheng ao ji"): None,
        ("破破弹片", "po po tan pian"): None,
        ("云杉木", "yun sha mu"): "yun shan mu",
        ("杉木", "shan mu"): "sha mu",
        ("试作澹月", "shi zuo tan yue"): None,
        ("大宛", "da wan"): "da yuan",
        ("乐进", "le jin"): "yue jin",
        ("校场", "xiao chang"): "jiao chang",
        ("大还丹", "da hai dan"): None,
        ("角色名", "jiao se ming"): "jue se ming",
        ("小还丹", "xiao hai dan"): "xiao huan dan",
        ("野山参", "ye shan can"): "ye shan shen",
        ("曾书书", "ceng shu shu"): "zeng shu shu",
        ("曾小贤", "ceng xiao xian"): "zeng xiao xian",
        ("阿尔忒弥斯", "a er tei mi si"): "a er te mi si",
        ("的的喀喀湖", "de de ka ka hu"): "di di ka ka hu",
        ("的黎波里", "de li bo li"): "di li bo li",
        ("露脊鲸", "lou ji jing"): "lu ji jing",
        ("酆都", "feng dou"): "feng du",
        ("清平乐", "qing ping le"): "qing ping yue",
        ("八荒六合", "ba huang lu he"): "ba huang liu he",
        ("怪我咯", "guai wo ge"): "guai wo lo",
        ("光禄大夫", "guang lu dai fu"): "guang lu da fu",
        ("纤手", "qian shou"): "xian shou",
        ("拓印", "tuo yin"): "ta yin",
        ("云裳", "yun shang"): "yun chang",
        ("春秋公羊传", "chun qiu gong yang chuan"): "chun qiu gong yang zhuan",
        ("谏议大夫", "jian yi dai fu"): "jian yi da fu",
        ("刘禅", "liu chan"): "liu shan",
        ("太阿", "tai a"): "tai e",
        ("龟壳", "gui qiao"): "gui ke",
        ("张说", "zhang shuo"): "zhang yue",
        ("船長", "chuan chang"): "chuan zhang",
        ("百夫長", "bai fu chang"): "bai fu zhang",
        ("單手", "shan shou"): "dan shou",
    }
    delete_words = {
        "虚无飘渺", "震摄", "莣鋽壹苆", "叽叽叽叽叽叽叽叽叽叽", "咩咩咩咩咩咩咩",
        "求伞啊啊啊啊", "装比", "吃藕",
    }
    reweight = {
        "男神": 400, "维拉": 100, "锈湖": 150, "阿布": 150, "赤练": 50,
        "伍德": 200, "塔克": 150, "莫雷": 80, "春娇": 100, "邦邦": 100,
    }
    for offset, line in enumerate(body):
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if (w, py) in game_py_fixes:
            new_py = game_py_fixes[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        if (d3_span and d3_span[0] <= offset <= d3_span[1]) or (va_span and va_span[0] <= offset <= va_span[1]):
            sim_w = jp_t2s(w)
            if sim_w != w:
                w = sim_w
                stats["fixed_word_or_trad"] += 1
        if w in reweight and w_int(wt) > reweight[w]:
            wt = str(reweight[w])
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_sport(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    orig_body_start = len(hdr) + 1
    out = list(hdr)
    py_fixes = {
        ("铦矛", "gua mao"): "xian mao",
        ("单晓娜", "dan xiao na"): "shan xiao na",
        ("朝彻", "chao che"): "zhao che",
        ("克里斯波什", "ke li si bo shen"): "ke li si bo shi",
        ("约什", "yue shen"): None,
        ("约什鲍威尔", "yue shen bao wei er"): None,
        ("约什布恩", "yue shen bu en"): None,
        ("约什卡尔迪伦", "yue shen ka er di lun"): None,
        ("弹腿", "dan tui"): "tan tui",
        ("阿什顿", "a shen dun"): "a shi dun",
        ("皮什切克", "pi shen qie ke"): "pi shi qie ke",
    }
    word_fixes = {
        "迈凯轮": ("迈凯伦", "mai kai lun"),
        "瑜珈": ("瑜伽", "yu jia"),
        "奥巴梅杨": ("奥巴梅扬", "ao ba mei yang"),
        "歧伯": ("岐伯", "qi bo"),
        "稲本潤一": ("稻本润一", "dao ben run yi"),
    }
    reweight = {
        "热刺": 200, "罗本": 300, "球友": 60, "维拉": 100, "伍德": 200,
        "塔克": 150, "圈速": 150, "耶伦": 100, "中圈": 150, "球后": 40,
    }
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in word_fixes:
            w, py = word_fixes[w]
            stats["fixed_word_or_trad"] += 1
        if (w, py) in py_fixes:
            new_py = py_fixes[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        if w in reweight and w_int(wt) > reweight[w]:
            wt = str(reweight[w])
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_literature(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    lit_py_fixes = {
        # Syllable mismatches in Zhuangzi merge
        ("曰是不是", "shi bu shi"): "yue shi bu shi",
        ("儵与忽时相与遇于浑沌之地", "shu yu hu shi xiang yu yu hun dun zhi di"): "shu yu hu shi xiang yu yu yu hun dun zhi di",
        ("螳螂捕蝉", "guo fu tang lang bu chan"): "tang lang bu chan",
        # Part 1 strict errors (c1b5d1b8)
        ("倪偁", "ni chen"): "ni cheng",
        ("啜菽饮水", "shu shu yin shui"): "chuo shu yin shui",
        ("王禹偁", "wang yu chen"): "wang yu cheng",
        ("肤受之愬", "fu shou zhi shuo"): "fu shou zhi su",
        ("公伯寮愬子路于季孙", "gong bo liao shuo zi lu yu ji sun"): "gong bo liao su zi lu yu ji sun",
        ("信如君不君臣不臣父不父子不子", "xin ru jun bu jun chen bu chen fu bu fu zi dun zi"): "xin ru jun bu jun chen bu chen fu bu fu zi bu zi",
        ("有荷蒉而过孔氏之门者", "you he kuai er guo kong shi zhi men zhe"): "you he kui er guo kong shi zhi men zhe",
        ("封之有庳", "feng zhi you bei"): "feng zhi you bi",
        ("风之有庳", "feng zhi you bei"): None,  # typo of 封之有庳
        ("哿矣富人", "jia yi fu ren"): "ge yi fu ren",
        ("愬武古通作牙爪", "shuo wu gu tong zuo ya zhao"): "su wu gu tong zuo ya zhao",
        ("以政接于有庳", "yi zheng jie yu you bei"): "yi zheng jie yu you bi",
        ("有庳之人奚罪焉", "you bei zhi ren xi zui yan"): "you bi zhi ren xi zui yan",
        ("在灯前攲枕", "zai deng qian yi zhen"): "zai deng qian qi zhen",
        ("民湿寝则腰疾偏死", "ming shi qin ze yao ji pian si"): "min shi qin ze yao ji pian si",
        ("民食刍豢", "ming shi chu huan"): "min shi chu huan",
        ("而丘也何足以知之", "qie qiu ye he zu yi zhi zhi"): "er qiu ye he zu yi zhi zhi",
        ("挟宇宙", "xia yu zhou"): "xie yu zhou",
        ("梦饮酒者", "ming yin jiu zhe"): "meng yin jiu zhe",
        ("梦哭泣者", "ming ku qi zhe"): "meng ku qi zhe",
        ("且若亦知夫德之所荡", "qi ruo yi zhi fu de zhi suo dang"): "qie ruo yi zhi fu de zhi suo dang",
        ("且鸟高飞以避矰弋之害", "qi niao gao fei yi bi zeng yi zhi hai"): "qie niao gao fei yi bi zeng yi zhi hai",
        ("胥易技系", "kuai yi ji xi"): "xu yi ji xi",
        ("乐出虚", "le chu xu"): "yue chu xu",
        ("恶乎然", "e hu ran"): "wu hu ran",
        ("恶乎至", "e hu zhi"): "wu hu zhi",
        ("予恶乎知说生之非惑邪", "yu e hu zhi shuo sheng zhi fei huo ye"): "yu wu hu zhi yue sheng zhi fei huo ye",
        ("予恶乎知恶死之非弱丧而不知归者邪", "yu e hu zhi wu si zhi fei ruo sang er bu zhi gui zhe ye"): "yu wu hu zhi wu si zhi fei ruo sang er bu zhi gui zhe ye",
        ("予恶乎知夫死者不悔其始之蕲生乎", "yu e hu zhi fu si zhe bu hui qi shi zhi qi sheng hu"): "yu wu hu zhi fu si zhe bu hui qi shi zhi qi sheng hu",
        ("张说", "zhang shuo"): "zhang yue",
        # Part 2 conflicts (c1b5d1b8)
        ("浅草才能没马蹄", "qian cao cai neng mei ma ti"): "qian cao cai neng mo ma ti",
        ("更行更远还生", "geng xing geng yuan huan sheng"): "geng xing geng yuan hai sheng",
        ("槛菊愁烟兰泣露", "kan ju chou yan lan qi lu"): "jian ju chou yan lan qi lu",
        ("轻解罗裳", "qing jie luo shang"): "qing jie luo chang",
        ("清平乐", "qing ping le"): "qing ping yue",
        ("无奈朝来寒雨晚来风", "wu nai chao lai han yu wan lai feng"): "wu nai zhao lai han yu wan lai feng",
        ("不薄今人爱古人", "bu bao jin ren ai gu ren"): None,
        ("长孙氏", "chang sun shi"): "zhang sun shi",
        ("朝避猛虎", "chao bi meng hu"): "zhao bi meng hu",
        ("此生此夜不长好", "ci sheng ci ye bu zhang hao"): "ci sheng ci ye bu chang hao",
        ("对酒行", "dui jiu hang"): "dui jiu xing",
        ("伐木丁丁", "fa mu ding ding"): "fa mu zheng zheng",
        ("凤栖梧桐", "feng xi wu tong"): "feng qi wu tong",
        ("贾生才调更无伦", "jia sheng cai tiao geng wu lun"): "jia sheng cai diao geng wu lun",
        ("江表传", "jiang biao chuan"): "jiang biao zhuan",
        ("今夜鄜州月", "jin ye lu zhou yue"): "jin ye fu zhou yue",
        ("槛外长江空自流", "kan wai chang jiang kong zi liu"): "jian wai chang jiang kong zi liu",
        ("履至尊而制六合", "lv zhi zun er zhi lu he"): "lv zhi zun er zhi liu he",
        ("明朝驿使发", "ming chao yi shi fa"): None,
        ("明朝游上苑", "ming chao you shang yuan"): "ming zhao you shang yuan",
        ("青山朝别暮还见", "qing shan chao bie mu hai jian"): None,
        ("数罟不入洿池", "shu gu bu ru hu chi"): "cu gu bu ru wu chi",
        ("闲花落地听无声", "xian hua luo de ting wu sheng"): "xian hua luo di ting wu sheng",
        ("携手日同行", "xie shou ri tong hang"): "xie shou ri tong xing",
        ("衣裳楚楚", "yi shang chu chu"): "yi chang chu chu",
        ("以吾从大夫之后", "yi wu cong dai fu zhi hou"): None,
        ("又得浮生一日凉", "you dei fu sheng yi ri liang"): "you de fu sheng yi ri liang",
        ("犹似霓裳羽衣舞", "you si ni shang yu yi wu"): "you si ni chang yu yi wu",
        ("与子同裳", "yu zi tong shang"): "yu zi tong chang",
        ("越人语天姥", "yue ren yu tian lao"): "yue ren yu tian mu",
        ("张旭三杯草圣传", "zhang xu san bei cao sheng zhuan"): "zhang xu san bei cao sheng chuan",
        ("赵令畤", "zhao ling chou"): "zhao ling zhi",
        ("直道相思了无益", "zhi dao xiang si le wu yi"): "zhi dao xiang si liao wu yi",
        ("周行而不殆", "zhou hang er bu dai"): "zhou xing er bu dai",
        ("自大夫出", "zi dai fu chu"): None,
        ("鲁人为长府", "lu ren wei zhang fu"): None,
        ("默而识之", "mo er shi zhi"): "mo er zhi zhi",
        ("未见颜色而言谓之瞽", "wei jian yan shai er yan wei zhi gu"): None,
        ("以吾一日长乎尔", "yi wu yi ri chang hu er"): None,
        ("巴山楚水凄凉地", "ba shan chu shui qi liang de"): "ba shan chu shui qi liang di",
        ("裨谌草创之", "bi shen cao chuang zhi"): None,
        ("不重生男重生女", "bu chong sheng nan chong sheng nv"): "bu zhong sheng nan zhong sheng nv",
        ("才了蚕桑又插田", "cai le can sang you cha tian"): "cai liao can sang you cha tian",
        ("曾益其所不能", "ceng yi qi suo bu neng"): "zeng yi qi suo bu neng",
        ("春风拂槛露华浓", "chun feng fu kan lu hua nong"): "chun feng fu jian lu hua nong",
        ("狐裘不暖锦衾薄", "hu qiu bu nuan jin qin bao"): None,
        ("躬自厚而薄责于人", "gong zi hou er bao ze yu ren"): None,
        ("汉文有道恩犹薄", "han wen you dao en you bao"): None,
        ("春情只到梨花薄", "chun qing zhi dao li hua bao"): None,
        ("此所谓率土地而食人肉", "ci suo wei lv tu di er shi ren rou"): "ci suo wei shuai tu di er shi ren rou",
        ("箪食壶浆以迎王师", "dan si hu jiang yi ying wang shi"): "dan shi hu jiang yi ying wang shi",
        ("道行之而成", "dao heng zhi er cheng"): "dao xing zhi er cheng",
        ("呱呱而泣", "gua gua er qi"): "gu gu er qi",
        ("狐貉之厚以居", "hu hao zhi hou yi ju"): None,
        ("疾风知劲草", "ji feng zhi jin cao"): "ji feng zhi jing cao",
        ("惊破霓裳羽衣曲", "jing po ni shang yu yi qu"): "jing po ni chang yu yi qu",
        ("临邛道士鸿都客", "lin qiong dao shi hong dou ke"): "lin qiong dao shi hong du ke",
        ("千磨万击还坚劲", "qian mo wan ji hai jian jin"): "qian mo wan ji hai jian jing",
        ("深巷明朝卖杏花", "shen xiang ming chao mai xing hua"): "shen xiang ming zhao mai xing hua",
        ("通邑大都", "tong yi da dou"): "tong yi da du",
        ("文之以礼乐", "wen zhi yi li le"): None,
        ("先天地生", "xian tian de sheng"): "xian tian di sheng",
        ("晓驾炭车辗冰辙", "xiao jia tan che zhan bing zhe"): "xiao jia tan che nian bing zhe",
        ("寻声暗问弹者谁", "xun sheng an wen dan zhe shui"): "xun sheng an wen tan zhe shui",
        ("幼有所长", "you you suo chang"): "you you suo zhang",
        # Zhuangzi earlier-block wrong duplicates (correct w=70 lines live at L35554+)
        ("哀乐不能入也", "ai yue bu neng ru ye"): None,
        ("彼且恶乎待哉", "bi qie e hu dai zai"): None,
        ("朝三而暮四", "chao san er mu si"): None,
        ("其正色邪", "qi zheng se xie"): None,
        ("未数数然也", "wei shu shu ran ye"): None,
        ("斥鴳笑之曰", "chi e xiao zhi yue"): None,
        ("道恶乎往而不存", "dao e hu wang er bu cun"): None,
        ("道恶乎隐而有真伪", "dao e hu yin er you zhen wei"): None,
        ("而曾二虫之无知", "er ceng er chong zhi wu zhi"): None,
        ("而待彼也邪", "er dai bi ye xie"): None,
        ("而果非也邪", "er guo fei ye xie"): None,
        ("非夫子之友邪", "fei fu zi zhi you xie"): None,
        ("果有言邪", "guo you yan xie"): None,
        ("可不哀邪", "ke bu ai xie"): None,
        ("淖约若处子", "nao yue ruo chu zi"): None,
        ("怒者其谁邪", "nu zhe qi shui xie"): None,
        ("其或非也邪", "qi huo fei ye xie"): None,
        ("其俱非也邪", "qi ju fei ye xie"): None,
        ("其未尝有言邪", "qi wei chang you yan xie"): None,
        ("其远而无所至极邪", "qi yuan er wu suo zhi ji xie"): None,
        ("前者唱于而随者唱喁", "qian zhe chang yu er sui zhe chang yu"): None,
        ("且有大觉而后知此其大梦也", "qie you da jiao er hou zhi ci qi da meng ye"): None,
        ("然则朝四而暮三", "ran ze chao si er mu san"): None,
        ("然则物无知邪", "ran ze wu wu zhi xie"): None,
        ("是之谓两行", "shi zhi wei liang hang"): None,
        ("我果非也邪", "wo guo fei ye xie"): None,
        ("吾所待又有待而然者邪", "wu suo dai you you dai er ran zhe xie"): None,
        ("吾有待而然者邪", "wu you dai er ran zhe xie"): None,
        ("言恶乎存而不可", "yan e hu cun er bu ke"): None,
        ("言恶乎隐而有是非", "yan e hu yin er you shi fei"): None,
        ("庸讵知吾所谓不知之非知邪", "yong ju zhi wu suo wei bu zhi zhi fei zhi xie"): None,
        ("庸讵知吾所谓知之非不知邪", "yong ju zhi wu suo wei zhi zhi fei bu zhi xie"): None,
        ("予恶乎知说生之非惑邪", "yu e hu zhi shuo sheng zhi fei huo xie"): None,
        ("子知子之所不知邪", "zi zhi zi zhi suo bu zhi xie"): None,
    }
    delete_words = {"朙月", "𤭢了", "鞦韆", "回㨃", "我们这里"}
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        # Drop OCR 囗 placeholder lines & single-char entries (owned by 8105)
        if "囗" in w or w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if len(w) == 1:
            stats["deleted_single_char_dup"] += 1
            continue
        if w == "甕㼜大瘿":
            w = "瓮㼜大瘿"
            stats["fixed_word_or_trad"] += 1
        if (w, py) in lit_py_fixes:
            new_py = lit_py_fixes[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        if w == "甄后" and w_int(wt) > 40:
            wt = "40"
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_idiom(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    idiom_py_fixes = {
        # Part 1 strict errors (c1b5d1b8)
        ("倪偁", "ni chen"): "ni cheng",
        ("啜菽饮水", "shu shu yin shui"): "chuo shu yin shui",
        ("王禹偁", "wang yu chen"): "wang yu cheng",
        ("闭门扫迹", "bi men sao gui"): "bi men sao ji",
        ("东观西望", "dong guang xi wang"): "dong guan xi wang",
        ("动中窾要", "dong zhong kua yao"): "dong zhong kuan yao",
        ("断鹤继凫", "duan he xu fu"): "duan he ji fu",
        ("隳高堙庳", "hui gao yin bei"): "hui gao yin bi",
        ("磨棱刓角", "mo leng liang jiao"): "mo leng wan jiao",
        ("铅刀为铦", "qian dao wei kuo"): "qian dao wei xian",
        ("擒奸擿伏", "qin jian zhe fu"): "qin jian ti fu",
        ("刓方为圆", "shu fang wei yuan"): "wan fang wei yuan",
        ("摘瑕指瑜", "ti xia zhi yu"): "zhai xia zhi yu",
        ("杨花水性", "yang hu shui xing"): "yang hua shui xing",
        ("湛恩汪濊", "zhan en wang hun"): "zhan en wang hui",
        ("枕石漱流", "zhen shi shou liu"): "zhen shi shu liu",
        ("肤受之愬", "fu shou zhi shuo"): "fu shou zhi su",
        ("公伯寮愬子路于季孙", "gong bo liao shuo zi lu yu ji sun"): "gong bo liao su zi lu yu ji sun",
        ("信如君不君臣不臣父不父子不子", "xin ru jun bu jun chen bu chen fu bu fu zi dun zi"): "xin ru jun bu jun chen bu chen fu bu fu zi bu zi",
        ("有荷蒉而过孔氏之门者", "you he kuai er guo kong shi zhi men zhe"): "you he kui er guo kong shi zhi men zhe",
        # Part 2 conflicts + ffe1e944 + c8d9c24d
        ("哀乐不能入也", "ai yue bu neng ru ye"): "ai le bu neng ru ye",
        ("彼且恶乎待哉", "bi qie e hu dai zai"): "bi qie wu hu dai zai",
        ("长孙氏", "chang sun shi"): "zhang sun shi",
        ("朝避猛虎", "chao bi meng hu"): "zhao bi meng hu",
        ("朝三而暮四", "chao san er mu si"): "zhao san er mu si",
        ("此生此夜不长好", "ci sheng ci ye bu zhang hao"): "ci sheng ci ye bu chang hao",
        ("对酒行", "dui jiu hang"): "dui jiu xing",
        ("伐木丁丁", "fa mu ding ding"): "fa mu zheng zheng",
        ("凤栖梧桐", "feng xi wu tong"): "feng qi wu tong",
        ("贾生才调更无伦", "jia sheng cai tiao geng wu lun"): "jia sheng cai diao geng wu lun",
        ("江表传", "jiang biao chuan"): "jiang biao zhuan",
        ("今夜鄜州月", "jin ye lu zhou yue"): "jin ye fu zhou yue",
        ("槛外长江空自流", "kan wai chang jiang kong zi liu"): "jian wai chang jiang kong zi liu",
        ("履至尊而制六合", "lv zhi zun er zhi lu he"): "lv zhi zun er zhi liu he",
        ("明朝驿使发", "ming chao yi shi fa"): "ming zhao yi shi fa",
        ("明朝游上苑", "ming chao you shang yuan"): "ming zhao you shang yuan",
        ("其正色邪", "qi zheng se xie"): "qi zheng se ye",
        ("青山朝别暮还见", "qing shan chao bie mu hai jian"): "qing shan zhao bie mu hai jian",
        ("数罟不入洿池", "shu gu bu ru hu chi"): "cu gu bu ru wu chi",
        ("未数数然也", "wei shu shu ran ye"): "wei shuo shuo ran ye",
        ("闲花落地听无声", "xian hua luo de ting wu sheng"): "xian hua luo di ting wu sheng",
        ("携手日同行", "xie shou ri tong hang"): "xie shou ri tong xing",
        ("衣裳楚楚", "yi shang chu chu"): "yi chang chu chu",
        ("以吾从大夫之后", "yi wu cong dai fu zhi hou"): None,
        ("又得浮生一日凉", "you dei fu sheng yi ri liang"): "you de fu sheng yi ri liang",
        ("犹似霓裳羽衣舞", "you si ni shang yu yi wu"): "you si ni chang yu yi wu",
        ("与子同裳", "yu zi tong shang"): "yu zi tong chang",
        ("越人语天姥", "yue ren yu tian lao"): "yue ren yu tian mu",
        ("张旭三杯草圣传", "zhang xu san bei cao sheng zhuan"): "zhang xu san bei cao sheng chuan",
        ("赵令畤", "zhao ling chou"): "zhao ling zhi",
        ("直道相思了无益", "zhi dao xiang si le wu yi"): "zhi dao xiang si liao wu yi",
        ("周行而不殆", "zhou hang er bu dai"): "zhou xing er bu dai",
        ("自大夫出", "zi dai fu chu"): None,
        ("阿保之功", "a bao zhi gong"): "e bao zhi gong",
        ("聱牙诘屈", "ao ya ji qu"): "ao ya jie qu",
        ("不着边际", "bu zhao bian ji"): "bu zhuo bian ji",
        ("草率将事", "cao lv jiang shi"): "cao shuai jiang shi",
        ("丑媳妇总得见公婆", "chou xi fu zong de jian gong po"): "chou xi fu zong dei jian gong po",
        ("大模大样", "da mo da yang"): "da mu da yang",
        ("大模厮样", "da mo si yang"): "da mu si yang",
        ("箪食壶浆", "dan si hu jiang"): "dan shi hu jiang",
        ("箪食瓢饮", "dan si piao yin"): "dan shi piao yin",
        ("栋折榱崩", "dong she cui beng"): "dong zhe cui beng",
        ("拊背扼吭", "fu bei e keng"): "fu bei e hang",
        ("辅世长民", "fu shi chang min"): "fu shi zhang min",
        ("浮收勒折", "fu shou le she"): "fu shou le zhe",
        ("怪模怪样", "guai mo guai yang"): "guai mu guai yang",
        ("怪腔怪调", "guai qiang guai tiao"): "guai qiang guai diao",
        ("好恶不同", "hao e bu tong"): "hao wu bu tong",
        ("豪商巨贾", "hao shang ju jia"): "hao shang ju gu",
        ("壶浆箪食", "hu jiang dan si"): "hu jiang dan shi",
        ("疾风知劲草", "ji feng zhi jin cao"): "ji feng zhi jing cao",
        ("诘屈聱牙", "ji qu ao ya"): "jie qu ao ya",
        ("挟势弄权", "jia shi nong quan"): "xie shi nong quan",
        ("家长理短", "jia zhang li duan"): "jia chang li duan",
        ("劲骨丰肌", "jin gu feng ji"): "jing gu feng ji",
        ("钧天之乐", "jun tian zhi le"): "jun tian zhi yue",
        ("扛鼎之作", "kang ding zhi zuo"): "gang ding zhi zuo",
        ("了不相干", "le bu xiang gan"): "liao bu xiang gan",
        ("敛声屏息", "lian sheng ping xi"): "lian sheng bing xi",
        ("两豆塞耳", "liang dou sai er"): "liang dou se er",
        ("良贾深藏", "liang jia shen cang"): "liang gu shen cang",
        ("默而识之", "mo er shi zhi"): "mo er zhi zhi",
        ("暮鼓朝钟", "mu gu chao zhong"): "mu gu zhao zhong",
        ("木强则折", "mu jiang ze zhe"): "mu qiang ze zhe",
        ("暮雨朝云", "mu yu chao yun"): "mu yu zhao yun",
        ("泥而不滓", "ni er bu zi"): "nie er bu zi",
        ("品竹调弦", "pin zhu diao xian"): "pin zhu tiao xian",
        ("青松落色", "qing song lao shai"): "qing song luo se",
        ("犬牙差互", "quan ya cha hu"): "quan ya ci hu",
        ("人给家足", "ren gei jia zu"): "ren ji jia zu",
        ("三人同行", "san ren tong hang"): "san ren tong xing",
        ("善善恶恶", "shan shan e e"): "shan shan wu e",
        ("山行海宿", "shan xing hai xiu"): "shan xing hai su",
        ("折箭为誓", "she jian wei shi"): "zhe jian wei shi",
        ("桃李成蹊", "tao li cheng qi"): "tao li cheng xi",
        ("桃蹊柳陌", "tao qi liu mo"): "tao xi liu mo",
        ("五藏六府", "wu cang liu fu"): "wu zang liu fu",
        ("一见了然", "yi jian le ran"): "yi jian liao ran",
        ("一力降十会", "yi li jiang shi hui"): "yi li xiang shi hui",
        ("赭衣塞路", "zhe yi sai lu"): "zhe yi se lu",
        ("鲁人为长府", "lu ren wei zhang fu"): "lu ren wei chang fu",
        ("未见颜色而言谓之瞽", "wei jian yan shai er yan wei zhi gu"): "wei jian yan se er yan wei zhi gu",
        ("以吾一日长乎尔", "yi wu yi ri chang hu er"): None,
        ("一模一样", "yi mo yi yang"): "yi mu yi yang",
        ("装模作样", "zhuang mo zuo yang"): "zhuang mu zuo yang",
        ("一针见血", "yi zhen jian xue"): "yi zhen jian xie",
        ("张说", "zhang shuo"): "zhang yue",
        ("溱洧", "qin wei"): "zhen wei",
    }
    delete_words = {
        "对薄公堂", "宽洪大量", "矜矜业业",
        "瑞文戴尔", "军团要塞", "暮色森林", "剑刃风暴", "时光之穴", "扭曲虚空",
        "千针石林", "山岭巨人", "暗冰反射", "混世冥牛", "昏睡药水",
        "冯诺依曼", "面向对象程序设计", "初级临时驾驶执照",
        "臭不要脸", "砖家叫兽", "婊子无情",
    }
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if w == "清官能断家务事":
            w = "清官难断家务事"
            stats["fixed_word_or_trad"] += 1
        elif w == "蓴羹鲈脍":
            w = "莼羹鲈脍"
            stats["fixed_word_or_trad"] += 1
        if (w, py) in idiom_py_fixes:
            new_py = idiom_py_fixes[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_history(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    hist_py_fixes = {
        # Part 1 strict (c1b5d1b8)
        ("大玮瑎", "da wei jie"): "da wei xie",
        ("萧瓛", "xiao ya"): "xiao huan",
        ("刘玱琳", "liu cang lin"): "liu qiang lin",
        ("奕詝", "yi nuo"): None,
        ("胤禵", "yin zhi"): None,
        ("陈璂卿", "chen ji qing"): "chen qi qing",
        ("陈鳣", "chen shan"): "chen zhan",
        ("陈玉璂", "chen yu ji"): "chen yu qi",
        ("东缗", "dong mian"): "dong min",
        ("眭固", "gui gu"): "sui gu",
        ("眭元进", "gui yuan jin"): "sui yuan jin",
        ("何世璂", "he shi ji"): "he shi qi",
        ("姬缗", "ji mian"): None,
        ("蒋攸铦", "jiang you gua"): "jiang you xian",
        ("晋闵公姬缗", "jin min gong ji mian"): "jin min gong ji min",
        ("王偁", "wang chen"): "wang cheng",
        ("汪禔", "wang ti"): "wang zhi",
        ("王禔", "wang ti"): "wang zhi",
        ("姚培偁", "yao pei chen"): "yao pei cheng",
        ("庄钟瀞", "zhuang zhong cheng"): "zhuang zhong jing",
        ("饮食赏赐与觽有异", "yin shi shang ci yu wei you yi"): "yin shi shang ci yu xi you yi",
        # Part 2 conflicts + ffe1e944
        ("不降", "bu xiang"): "bu jiang",
        ("刘禅", "liu chan"): "liu shan",
        ("张玄靓", "zhang xuan liang"): None,
        ("夫差", "fu cha"): "fu chai",
        ("姬辟方", "ji bi fang"): None,
        ("姬重耳", "ji zhong er"): "ji chong er",
        ("田辟彊", "tian bi jiang"): None,
        ("张重华", "zhang zhong hua"): None,
        ("重华", "zhong hua"): None,
        ("曾天养", "ceng tian yang"): "zeng tian yang",
        ("嵇曾筠", "ji ceng jun"): "ji zeng yun",
        ("拉藏汗", "la cang han"): "la zang han",
        ("上衣下裳", "shang yi xia shang"): "shang yi xia chang",
        ("与子同裳", "yu zi tong shang"): "yu zi tong chang",
        ("东阿", "dong a"): "dong e",
        ("海都", "hai dou"): "hai du",
        ("孛儿只斤", "bei er zhi jin"): "bo er zhi jin",
        ("曾铸", "ceng zhu"): "zeng zhu",
        ("仇兆鳌", "chou zhao ao"): "qiu zhao ao",
        ("大宛", "da wan"): "da yuan",
        ("倓虚", "dan xu"): "tan xu",
        ("琅邪", "lang xie"): "lang ya",
        ("乐进", "le jin"): "yue jin",
        ("缪昌期", "miu chang qi"): "miao chang qi",
        ("缪荃孙", "miu quan sun"): "miao quan sun",
        ("缪希雍", "miu xi yong"): "miao xi yong",
        ("朴趾源", "pu zhi yuan"): "piao zhi yuan",
        ("区星", "qu xing"): "ou xing",
        ("什伐赤", "shen fa chi"): "shi fa chi",
        ("蜀后主刘禅", "shu hou zhu liu chan"): "shu hou zhu liu shan",
        ("宋辟公", "song pi gong"): None,
        ("王庭筠", "wang ting jun"): "wang ting yun",
        ("伍长华", "wu zhang hua"): "wu chang hua",
        ("下大夫", "xia dai fu"): "xia da fu",
        ("徐师曾", "xu shi ceng"): "xu shi zeng",
        ("召陵", "zhao ling"): "shao ling",
        ("重泉", "zhong quan"): "chong quan",
        ("诸葛靓", "zhu ge liang"): "zhu ge jing",
        ("褚民谊", "zhu min yi"): "chu min yi",
        ("褚人获", "zhu ren huo"): "chu ren huo",
    }
    delete_words = {"许诸", "张颌", "秃发偄檀", "肯能"}
    word_fixes = {
        "孔亻由": ("孔伷", "kong zhou"),
        "鬱林王": ("郁林王", "yu lin wang"),
        "鬱林王萧昭业": ("郁林王萧昭业", "yu lin wang xiao zhao ye"),
        "宫絳": ("宫绛", "gong jiang"),
        "刘準": ("刘准", "liu zhun"),
        "宋顺帝刘準": ("宋顺帝刘准", "song shun di liu zhun"),
        "邹凌澣": ("邹凌瀚", "zou ling han"),
    }
    reweight = {"糜芳": 100, "暴王": 50, "吴军": 200, "李旦": 150, "刘贺": 150, "朱温": 60, "张恒": 80}
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if w in word_fixes:
            w, py = word_fixes[w]
            stats["fixed_word_or_trad"] += 1
        if (w, py) in hist_py_fixes:
            new_py = hist_py_fixes[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        if w in reweight and w_int(wt) > reweight[w]:
            wt = str(reweight[w])
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_name(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    name_py_fixes = {
        ("李泌", "li mi"): "li bi",
        ("顾曾", "gu ceng"): "gu zeng",
        ("曾哥", "ceng ge"): "zeng ge",
        ("柏辽兹", "bai liao zi"): "bo liao zi",
        ("文格勒", "wen ge lei"): "wen ge le",
        ("朱重八", "zhu zhong ba"): "zhu chong ba",
        ("埃勒里", "ai lei li"): "ai le li",
        ("曹名长", "cao ming zhang"): "cao ming chang",
        ("胡三省", "hu san sheng"): "hu san xing",
        ("阿代勒吉", "a dai lei ji"): "a dai le ji",
        ("阿勒曼尼", "a lei man ni"): "a le man ni",
        ("韦克斯勒", "wei ke si lei"): "wei ke si le",
        ("耶律重元", "ye lv zhong yuan"): "ye lv chong yuan",
        ("伊什特万", "yi shen te wan"): "yi shi te wan",
        ("陈省身", "chen sheng shen"): "chen xing shen",
        ("李重润", "li zhong run"): "li chong run",
        ("米勒特", "mi lei te"): "mi le te",
        ("塞莱什", "sai lai shen"): "sai lai shi",
        ("王曾瑜", "wang ceng yu"): "wang zeng yu",
        ("阿伽松", "a ga song"): "a jia song",
        ("王重荣", "wang zhong rong"): "wang chong rong",
        ("佛索威", "fu suo wei"): "fo suo wei",
        ("依什卡", "yi shen ka"): "yi shi ka",
        ("于长平", "yu zhang ping"): "yu chang ping",
        ("艾勒里", "ai lei li"): "ai le li",
        ("宋世泊", "song shi po"): "song shi bo",
        ("缪德树", "mou de shu"): "miao de shu",
        ("于省吾", "yu sheng wu"): "yu xing wu",
        ("博伽茹", "bo ga ru"): "bo jia ru",
        ("佛母", "fu mu"): "fo mu",
    }
    delete_words = {
        # Typos (real forms exist in base/ext)
        "缪尔塞思", "席慕容", "欧阳峰", "歌德巴赫", "马嘎尔尼", "狄俄涅索斯", "赛尔达",
        # NSFW troll names
        "季伯", "季伯长", "季伯常", "季伯英", "季伯达", "季伯初",
        # Truncated name & text fragments (56f50fb5)
        "小林多喜", "阿波利奈", "维尼亚夫", "成濑巳喜", "阿尔玛格", "赫梅尔尼",
        "普罗霍洛", "叶尔莫洛", "登美彦", "田冈茂", "堀口悠", "鲇川哲", "瓦尔拉",
        "闵可夫", "霍亨索", "德米特", "柯尔莫", "萨拉班", "格雷茨", "阿布辛",
        "克特西", "洛丝罗", "安哲罗", "卡尔达", "格尔利", "帕夫利", "伊纳里",
        "莫里亚", "梅丽桑", "施托克", "伊斯玛", "阿格里", "杜布切", "克里普",
        "施莱歇", "霍亨斯", "萨拉曼", "阿尔帕", "马斯塔", "狄奥尼", "阿尔伯",
        "莫霍利", "弗洛依", "铁木辛", "斯坎德", "施可汗", "那托列", "依克多",
        "阿赫梅", "霍扬斯克镇",
        "元起", "二看", "拉斯", "斯塔夫", "里亚诺", "什维利", "伦斯基", "切夫斯基",
        "斯菲尔德", "武帝纪", "尼乌斯", "孔明曰", "斯巴赫", "斯托夫", "王弼注",
        "西莫夫", "王霸之", "同同家", "梁直导", "季耶夫", "施特拉", "利亚诺",
        "罗斯塔", "浩司案", "奥巴", "基里",
        # Non-name words
        "短短的", "没地去", "骨相", "花材", "炖菜", "带教", "墓主", "打本", "实车", "花活", "石乐志",
    }
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#") and not line.strip().startswith("#Q薰"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if w == "梁文峰":
            w = "梁文锋"
            stats["fixed_word_or_trad"] += 1
        elif "薫" in w:
            w = w.replace("薫", "薰")
            stats["fixed_word_or_trad"] += 1
        elif w == "浜田省吾":
            w = "滨田省吾"
            stats["fixed_word_or_trad"] += 1
        if (w, py) in name_py_fixes:
            py = name_py_fixes[(w, py)]
            stats["fixed_py"] += 1
        # Respect header `# 名字 要降频`: cap weights at 150 so names don't hijack base words
        if w_int(wt) > 150:
            wt = "150"
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_name2(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    akb_span = find_entry_span(body, ("阿部瑪利亞", "a bu ma li ya"), ("佐佐木優佳里", "zuo zuo mu you jia li"))
    out = list(hdr)
    name2_py_fixes = {
        ("鲹坂长实", "can ban chang shi"): "shen ban chang shi",
        ("朝比奈泰煕", "zhao bi nai tai yi"): "zhao bi nai tai xi",
        ("河岾面", "he zai mian"): "he zhan mian",
        ("渡辺麻友", "du dao ma you"): "du bian ma you",
        ("渡辺茉莉絵", "du dao mo li hui"): "du bian mo li hui",
        ("叄舞白刃", "cen wu bai ren"): "san wu bai ren",
        ("瀞灵壁", "cheng ling bi"): None,
        ("本多重次", "ben duo chong ci"): None,
        ("小西行长", "xiao xi hang zhang"): "xiao xi xing chang",
        ("朴灿烈", "pu can lie"): "piao can lie",
        ("朴初珑", "pu chu long"): "piao chu long",
        ("朴炯植", "pu jiong zhi"): "piao jiong zhi",
        ("朴娜莱", "pu na lai"): "piao na lai",
        ("朴世荣", "pu shi rong"): "piao shi rong",
        ("朴孝敏", "pu xiao min"): "piao xiao min",
        ("朴秀荣", "pu xiu rong"): "piao xiu rong",
        ("朴叙俊", "pu xu jun"): "piao xu jun",
        ("朴宥拉", "pu you la"): "piao you la",
        ("朴珍荣", "pu zhen rong"): "piao zhen rong",
        ("朴智旻", "pu zhi min"): "piao zhi min",
        ("朴智妍", "pu zhi yan"): "piao zhi yan",
        ("朴光贤", "pu guang xian"): "piao guang xian",
        ("朴璐美", "pu lu mei"): "piao lu mei",
        ("曾根昌世", "ceng gen chang shi"): None,
        ("神保长城", "shen bao zhang cheng"): None,
        ("神保长住", "shen bao zhang zhu"): None,
        ("李劲松", "li jin song"): "li jing song",
        ("恩奇都", "en qi dou"): "en qi du",
        ("神鎗", "shen cheng"): None,
        ("王栎鑫", "wang yue xin"): "wang li xin",
        ("藏人", "cang ren"): "zang ren",
        ("沙都", "sha dou"): "sha du",
        ("味噌", "wei ceng"): "wei zeng",
        ("梁翘柏", "liang qiao bai"): "liang qiao bo",
        ("闵玧其", "min men qi"): "min yun qi",
        ("都暻秀", "dou jing xiu"): "du jing xiu",
    }
    word_fixes = {
        "阿褔": ("阿福", "a fu"),
        "辜靖潔": ("辜靖洁", "gu jing jie"),
        "吴克羣": ("吴克群", "wu ke qun"),
        "高木渉": ("高木涉", "gao mu she"),
        "朝比奈泰煕": ("朝比奈泰熙", "zhao bi nai tai xi"),
    }
    for offset, line in enumerate(body):
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        # Fix all 39+ 畠 zai -> tian
        if "畠" in w and "zai" in py.split():
            new_py = replace_syl_at(w, py, "畠", "zai", "tian")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if (w, py) in name2_py_fixes:
            new_py = name2_py_fixes[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        if w in word_fixes:
            w, py = word_fixes[w]
            stats["fixed_word_or_trad"] += 1
        if akb_span and akb_span[0] <= offset <= akb_span[1]:
            sim_w = jp_t2s(w)
            if sim_w != w:
                w = sim_w
                stats["fixed_word_or_trad"] += 1
        # Respect header `# 需要降频`
        if w_int(wt) > 150:
            wt = "150"
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_exthot(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    new_hdr = [
        ("use_preset_vocabulary: false" if l.strip() == "use_preset_vocabulary: true" else l)
        for l in hdr
    ]
    out = list(new_hdr)
    py_fixes = {
        ("暗河传", "an he chuan"): "an he zhuan",
        ("玱玹", "cang xuan"): "qiang xuan",
        ("曾三仙", "ceng san xian"): "zeng san xian",
        ("曾婉之", "ceng wan zhi"): "zeng wan zhi",
        ("仇白", "chou bai"): "qiu bai",
        ("弹反", "dan fan"): None,
        ("单依纯", "dan yi chun"): None,
        ("莞莞类卿", "guan guan lei qing"): "wan wan lei qing",
        ("活侠传", "huo xia chuan"): "huo xia zhuan",
        ("眯觉", "mi jue"): "mi jiao",
        ("女仆长", "nv pu chang"): "nv pu zhang",
        ("褪色者", "tui shai zhe"): None,
        ("与辉同行", "yu hui tong hang"): "yu hui tong xing",
        ("朝阳站", "zhao yang zhan"): "chao yang zhan",
    }
    delete_words = {
        # Typos & 的/得 hijackers
        "玩的开心", "一摸一样的", "查的严", "到的早", "近的很", "考的高", "累的很",
        "起来的早", "热的很", "热的我", "下的大吗", "下的太大了", "大差不大", "掉称",
        "度年华", "对不己", "卡摸", "俩个月", "俩件", "炉岩碳", "同协", "一但",
        "真的会写", "现眼包", "解班", "泰国丸美", "为什么不虐泉",
        # Profanity / toxic / NSFW
        "沟槽的", "勾石", "牛魔的", "网暴死", "卧草", "厚礼蟹", "鸡哔你",
        "吊五", "依托答辩", "紫狗", "河北彩花", "劳资蜀道山", "雌小鬼",
        # Broken fragments & weight anomaly
        "什金", "大于五个字", "登记的", "降的", "链接地", "榴莲的", "其妙的",
        "如果我", "若月亮", "有个小卖部", "云边的", "云边有个",
        # Ephemeral mid-2024 Weibo/Douyin hot-search headlines
        "阿黛尔采访", "霸王茶姬口令", "帮我助力一下", "博纳财报", "长相思断更",
        "陈泽抽奖", "错位开播", "邓为提灯剧照", "迪丽热巴活动",
        "歌手出场顺序", "歌手突围赛", "歌手直播", "贵女杀青", "杭盖替身",
        "欢迎普京", "黄宣秒了", "金九封面预告", "金九含金量", "肯德基原神联动",
        "蓝盈莹演技", "李梦承认恋情", "林俊杰原唱", "名字快闪挑战",
        "那英第一", "那英天后回归", "七夜雪预约", "七月啦", "人鱼已杀青",
        "三砖移步挑战", "省力版爬泰山", "挑战做神仙鱼", "童话镇慢动作",
        "网剧错位", "汪苏泷唱氧气", "乌克兰契约", "武磊两射两传", "无名毛利率",
        "夏日整活日记", "相柳黑衣银发", "香缇莫唱错词", "相信波音",
        "原神火神首曝", "原神肯德基", "原神纳塔全员", "张凌赫赵今麦",
        "中餐厅杀青", "周深起名天才", "周深新歌缝合", "抓娃娃点映",
    }
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if (w, py) in py_fixes:
            new_py = py_fixes[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        if w == "预瞄" and w_int(wt) > 120:
            wt = "120"
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_animal(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    new_hdr = [
        ("use_preset_vocabulary: false" if l.strip() == "use_preset_vocabulary: true" else l)
        for l in hdr
    ]
    out = list(new_hdr)
    py_fixes = {
        ("威尔斯牧畜犬", "wei er si mu xu quan"): "wei er si mu chu quan",
        ("华乐", "hua le"): "hua yue",
        ("华乐蛋白石基因", "hua le dan bai shi ji yin"): "hua yue dan bai shi ji yin",
        ("华乐基因", "hua le ji yin"): "hua yue ji yin",
        ("黄裳凤蝶", "huang shang feng die"): "huang chang feng die",
        ("金裳凤蝶", "jin shang feng die"): "jin chang feng die",
        ("裳凤蝶", "shang feng die"): "chang feng die",
    }
    word_fixes = {
        "美国史塔副郡㹴": ("美国史塔福郡㹴", "mei guo shi ta fu jun geng"),
        "史塔副郡牛头㹴": ("史塔福郡牛头㹴", "shi ta fu jun niu tou geng"),
        "米尼雪纳瑞犬": ("迷你雪纳瑞犬", "mi ni xue na rui quan"),
        "挪威糜提": ("挪威麋提", "nuo wei mi ti"),
        "挪威糜缇": ("挪威麋缇", "nuo wei mi ti"),
        "彭布罗克歌基犬": ("彭布罗克柯基犬", "peng bu luo ke ke ji quan"),
        "小史揉查犬": ("小史柔查犬", "xiao shi rou cha quan"),
        "英国小型猎免犬": ("英国小型猎兔犬", "ying guo xiao xing lie tu quan"),
        "约瑟猩": ("约瑟㹴", "yue se geng"),
        "桅子灰蝶": ("栀子灰蝶", "zhi zi hui die"),
        "甄蝶": ("珍蝶", "zhen die"),
        "眼碟": ("眼蝶", "yan die"),
    }
    delete_words = {
        "阿拉斯加雪撬犬", "西伯利亚雪撬犬", "黄寻猎犬", "惠比犬特", "秦得圣赫伯特犬",
        "日本仲", "中国冠毛犬犬", "榺凤蝶", "八哥犬", "拉不拉多", "马耳济斯犬",
        "迷你雪那瑞", "迷你雪娜瑞犬", "小雪娜瑞犬", "路路", "短毛正常毛质阿拉斯加",
    }
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if w in word_fixes:
            w, py = word_fixes[w]
            stats["fixed_word_or_trad"] += 1
        if (w, py) in py_fixes:
            py = py_fixes[(w, py)]
            stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_inputmethod(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    delete_words = {
        "爱次漏的小栏还", "光華", "星陳", "亾师", "蔃师", "蒻师", "爱师", "鲸师", "苗师", "介介",
        "王旁青头戋五一土士二干十寸雨一二还有革字底大犬三羊古石厂木丁西工戈草头右框七",
        "墨奇音形的作者是伽布里克", "白霜拼音的作者是伽布里克", "小鹤音形作者是何海峰",
        "汉心码作者晡时之光", "天码输入法的作者是宋天", "声笔输入法作者戴石麟",
        "五笔输入法作者是王永民", "宇浩输入法作者是朱宇浩", "冰雪拼音作者蓝落萧",
    }
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if (w, py) == ("九重魔鹤", "jiu zhong mo he"):
            py = "jiu chong mo he"
            stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_music(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        if (w, py) == ("复调音乐", "fu tiao yin le"):
            stats["deleted_wrong_py"] += 1  # correct fu diao yin yue 233 already in ext
            continue
        if w == "复调" and w_int(wt) > 200:
            wt = "200"
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_composite(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    tail_span = find_entry_span(body, ("晒伤没", "shai shang mei"), ("挨没挨住", "ai mei ai zhu"), next_word="没晒伤")
    out = list(hdr)
    comp_py_fixes = {
        ("双马尾", "shuang ma yi"): "shuang ma wei",
        ("马尾发型", "ma yi fa xing"): "ma wei fa xing",
        ("有嚼劲", "you jue jin"): "you jiao jin",
        ("往哪个方向", "wang nei ge fang xiang"): "wang na ge fang xiang",
        ("哪个牌子好", "nei ge pai zi hao"): "na ge pai zi hao",
        ("女红军", "nv gong jun"): "nv hong jun",
        ("鬼女红叶", "gui nv gong ye"): "gui nv hong ye",
        ("大黄页", "dai huang ye"): "da huang ye",
        ("八爪鱼", "ba zhao yu"): "ba zhua yu",
        ("椎拳崇", "chui quan chong"): "zhui quan chong",
        ("热情似火", "re qing shi huo"): "re qing si huo",
        ("红似火", "hong shi huo"): "hong si huo",
        ("花开似锦", "hua kai shi jin"): "hua kai si jin",
        ("如封似闭", "ru feng shi bi"): "ru feng si bi",
        ("尚书右仆射", "shang shu you pu she"): "shang shu you pu ye",
        ("尚书左仆射", "shang shu zuo pu she"): "shang shu zuo pu ye",
        ("干咳少痰", "gan hai shao tan"): "gan ke shao tan",
        ("慕容廆", "mu rong gui"): "mu rong wei",
        ("耙耙柑", "ba ba gan"): "pa pa gan",
        ("背俞穴", "bei yu xue"): "bei shu xue",
        ("龈下刮治", "ken xia gua zhi"): "yin xia gua zhi",
        ("世情薄", "shi qing bao"): "shi qing bo",
        ("势孤力薄", "shi gu li bao"): "shi gu li bo",
        ("厚彼薄此", "hou bi bao ci"): "hou bi bo ci",
        ("厚积而薄发", "hou ji er bao fa"): "hou ji er bo fa",
        ("本小利薄", "ben xiao li bao"): "ben xiao li bo",
        ("薄今厚古", "bao jin hou gu"): "bo jin hou gu",
        ("薄宦梗犹泛", "bao huan geng you fan"): "bo huan geng you fan",
        ("舌苔薄白", "she tai bao bai"): "she tai bo bai",
        ("金属薄板", "jin shu bao ban"): "jin shu bo ban",
        ("流血涂野草", "liu xie tu ye cao"): "liu xue tu ye cao",
    }
    delete_words = {
        # Classic & grammatical typos
        "雪中送碳", "感同深受", "相形见拙", "不屈不饶", "相辅相承", "变换莫测",
        "一股作气", "一相情愿", "一泄千里", "不可思意", "涛涛不绝", "如火如茶",
        "仗义直言", "汗流夹背", "好高务远", "一上悠亚", "通俗的讲", "清楚的知道",
        "墙裂推荐", "举个栗子",
        # Vulgar / junk / fragments (c8d9c24d + 3f37fbc7)
        "真特么", "逼格高", "牛逼哄哄", "有多牛逼", "谁特么", "卧槽卧槽", "心机婊",
        "医生说", "我们说", "同学说", "老板说", "领导说", "我爸说", "同事说",
        "最高人民法院关于", "国家税务总局关于", "空气炸", "转载请", "不论你是",
        "几乎无", "说中国", "一个全新的", "不熟悉的", "出版社出版", "㨃回去",
        "王菲真", "墙安装", "墙涂料", "墙面装", "一下把", "一下放", "一不能",
        "一专业", "一专线", "一专门", "一丝不", "大河田", "少主子", "吉普号", "天眼妹",
    }
    promo_substrings = (
        "关注我的公众号", "点击下方", "点击右上角", "点个赞", "欢迎私信", "私信问我",
        "加我微信", "评论区留言", "图片来自网络", "图片来源于网络", "转载请注明出处",
        "欢迎大家关注", "欢迎关注公众号", "可以关注公众号", "请关注公众号",
        "后台回复", "本文首发", "点赞收藏", "点赞关注", "一键三连", "私信我",
    )
    rep4_re = re.compile(r"(.)\1{3,}")

    for offset, line in enumerate(body):
        if tail_span and tail_span[0] <= offset <= tail_span[1]:
            if parse_entry(line):
                stats["deleted_template_tail"] += 1
            continue
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if (
            w in delete_words
            or is_leading_de_fragment(w, py)
            or is_leading_le_fragment(w, py)
            or rep4_re.search(w)
            or any(sub in w for sub in promo_substrings)
        ):
            stats["deleted_noise_or_typo"] += 1
            continue
        # Fix 157 质+的=di -> de
        if "质的" in w and "di" in py.split():
            new_py = replace_syl_at(
                w, py, "的", "di", "de",
                cond=lambda wd, sy, i: i > 0 and wd[i - 1] == "质" and i + 1 < len(wd),
            )
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        # Fix 193 non-仿佛/彷佛 佛=fu -> fo
        if "佛" in w and "fu" in py.split():
            new_py = replace_syl_at(
                w, py, "佛", "fu", "fo",
                cond=lambda wd, sy, i: not (i > 0 and wd[i - 1] in "仿彷"),
            )
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        # Fix 4 转文字 zhuai -> zhuan
        if "转文字" in w and "zhuai" in py.split():
            new_py = replace_syl_at(w, py, "转", "zhuai", "zhuan")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if (w, py) in comp_py_fixes:
            py = comp_py_fixes[(w, py)]
            stats["fixed_py"] += 1
        if w == "科技布" and w_int(wt) > 150:
            wt = "150"
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_luna(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    luna_py_fixes = {
        # 4 invalid Mandarin syllables
        ("骨崖崖", "gu yai yai"): "gu ya ya",
        ("视觉悬崖", "shi jue xuan yai"): "shi jue xuan ya",
        ("蕃娈", "fan lvan"): "fan luan",
        ("挛挛", "lvan lvan"): "luan luan",
        # 23 verified genuine typos even in Taiwan MOE (c1b5d1b8) + 3f37fbc7
        ("中山高速公路", "zhong shan gao shu gong lu"): "zhong shan gao su gong lu",
        ("出火炕", "chu huo keng"): "chu huo kang",
        ("夭邪", "yao xia"): "yao xie",
        ("安静自在", "an xian zi zai"): "an jing zi zai",
        ("忠言奇谋", "zhong yan qi mo"): "zhong yan qi mou",
        ("悉率", "xi shuo"): "xi shuai",
        ("攀车拒轮", "pan che che lun"): "pan che ju lun",
        ("斫鲙", "zhuo kui"): "zhuo kuai",
        ("沙鸡", "cha ji"): "sha ji",
        ("潘金莲给武松敬酒", "pan jin lian gei wu song jin jiu"): "pan jin lian gei wu song jing jiu",
        ("素女弦", "su nv xuan"): "su nv xian",
        ("绁袢", "xie ban"): "xie pan",
        ("经济怪兽", "jing ji guai chou"): "jing ji guai shou",
        ("繁塔", "bo ta"): "po ta",
        ("罗夏克墨渍测验", "luo xia ke mo ze ce yan"): "luo xia ke mo zi ce yan",
        ("羊须疮", "yang xu cang"): "yang xu chuang",
        ("葫芦里卖的甚么药", "hu lu li mai de shen men yao"): "hu lu li mai de shen me yao",
        ("逻辑闸", "luo ji jia"): "luo ji zha",
        ("邾娄", "zhu lv"): "zhu lou",
        ("阿毗昙", "a pi tian"): "a pi tan",
        ("雁头鸱劳嘴", "yan tou zhi lao zui"): "yan tou chi lao zui",
        ("鸥波", "o bo"): "ou bo",
        ("伽利略·伽利雷", "jia li lve ga li lei"): "jia li lve jia li lei",
        ("凯茜·弗里曼", "kai qian fu li man"): "kai xi fu li man",
        ("罗伯特·佛洛斯特", "luo bo te fu luo si te"): "luo bo te fo luo si te",
        ("叶面对称", "ye mian dui cheng"): None,
    }
    delete_words = {
        # 27 classic typos from 10_classic_typo_hits.txt + c8d9c24d + 3f37fbc7
        "鬼计多端", "震憾", "重迭", "趋之若骛", "美仑美奂", "维妙维肖", "立杆见影",
        "神彩奕奕", "直接了当", "留连忘返", "焕然冰释", "混水摸鱼", "气慨", "毛骨耸然",
        "无精打彩", "无庸置疑", "悬梁刺骨", "恰如其份", "幅射", "展露头角", "寒喧",
        "委屈求全", "如法泡制", "前扑后继", "别出新裁", "冒然", "兴高彩烈", "不醒人事",
        "冯诺以曼", "驼鸟", "驼鸟政策", "骑土", "驻戌", "搭挡", "侏㑩纪", "夏洛特·勃良特",
        "干逼", "了鸟",
    }
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in delete_words:
            stats["deleted_noise_or_typo"] += 1
            continue
        if (w, py) == ("灵桩", "ling chun"):
            w = "灵椿"
            stats["fixed_word_or_trad"] += 1
        if (w, py) in luna_py_fixes:
            new_py = luna_py_fixes[(w, py)]
            if new_py is None:
                stats["deleted_wrong_py"] += 1
                continue
            py = new_py
            stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_generic(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        new_py = normalize_lue_nue(py)
        if new_py != py:
            py = new_py
            stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


# ---------------------------------------------------------------------------
# English & OpenCC cleaners
# ---------------------------------------------------------------------------

def clean_en_dicts(manifest: dict) -> None:
    en_dir = DST_ROOT / "en_dicts"
    en_dir.mkdir(parents=True, exist_ok=True)

    # Per melt_eng.dict.yaml: en_ext is imported BEFORE en (to preserve alias ordering like PS -> Photoshop).
    # Therefore clean en_ext first, then deduplicate en against en_ext!

    # 1. en_ext.dict.yaml
    ext_fixes = {
        ("Btitish", "Btitish"): ("British", "British"),
        ("PlistEdit", "pliPlistEdit"): ("PlistEdit", "PlistEdit"),
        ("itsdangerours", "itsdangerours"): ("itsdangerous", "itsdangerous"),
        ("Philppines", "Philppines"): ("Philippines", "Philippines"),
        ("RFT", "RFT"): ("RTF", "RTF"),
        ("Rich Text Format", "RFT"): ("Rich Text Format", "RTF"),
        ("Lens Protocal", "LensProtocal"): ("Lens Protocol", "LensProtocol"),
    }
    ext_delete = {"Italilian", "unfo", "Negro", "heil", "hading", "limon", "Kuromis", "fuckity", "shitwork", "beyatch", "fo"}
    ext_lines = (SRC_ROOT / "en_dicts/en_ext.dict.yaml").read_text(encoding="utf-8").splitlines()
    hdr, body = split_header_body(ext_lines)
    ext_out = list(hdr)
    ext_seen = set()
    ext_fixed = 0
    ext_del = 0
    ext_dedup = 0
    for line in body:
        p = parse_entry(line)
        if not p:
            ext_out.append(line)
            continue
        w, code, wt, extra = p
        if w in ext_delete:
            ext_del += 1
            continue
        if (w, code) in ext_fixes:
            w, code = ext_fixes[(w, code)]
            ext_fixed += 1
        if (w, code) in ext_seen:
            ext_dedup += 1
            continue
        ext_seen.add((w, code))
        ext_out.append(format_entry(w, code, wt, extra))
    (en_dir / "en_ext.dict.yaml").write_text("\n".join(ext_out) + "\n", encoding="utf-8", newline="\n")
    manifest["files"]["en_dicts/en_ext.dict.yaml"] = {
        "before": len(ext_lines), "after": len(ext_out), "fixed": ext_fixed, "deleted": ext_del, "deduped": ext_dedup
    }

    # 2. en.dict.yaml (deduped against en_ext, preserving valid English word 'nous')
    en_bad = {
        # Typos
        "amature", "beastiality", "definately", "Ffremont", "millenium", "RFT",
        "transexual", "transexuals",
        # Foreign non-English words (note: 'nous' IS valid English, kept!)
        "Auch", "Bilder", "der", "deutsch", "deutschland", "dicke", "fetisch",
        "filme", "impressum", "neu", "Oder", "telefonsex",
        "centro", "espanol", "hoteles", "lesbianas", "Musica", "transexuales", "zoofilia",
        "Faire", "gratuit", "recherche",
        # Web-crawl porn/pharma/SDK spam
        "acdbentity", "AcDbLine", "Bizjournalshire", "ChillSeph", "knowledgestorm",
        "livesex", "milfseeker", "pichunter", "sexcam", "starsmerchant", "worldsex",
        "adipex", "cameltoe", "cialis", "ladyboy", "levitra", "phentermine", "tranny",
    }
    en_lines = (SRC_ROOT / "en_dicts/en.dict.yaml").read_text(encoding="utf-8").splitlines()
    hdr, body = split_header_body(en_lines)
    en_out = list(hdr)
    en_seen = set(ext_seen)
    en_del = 0
    en_dedup = 0
    for line in body:
        p = parse_entry(line)
        if not p:
            en_out.append(line)
            continue
        w, code, wt, extra = p
        if w in en_bad:
            en_del += 1
            continue
        if (w, code) in en_seen:
            en_dedup += 1
            continue
        en_seen.add((w, code))
        en_out.append(format_entry(w, code, wt, extra))
    (en_dir / "en.dict.yaml").write_text("\n".join(en_out) + "\n", encoding="utf-8", newline="\n")
    manifest["files"]["en_dicts/en.dict.yaml"] = {
        "before": len(en_lines), "after": len(en_out), "deleted": en_del, "deduped_against_en_ext": en_dedup
    }

    # 3. cn_en.txt & cn_en_double_pinyin.txt (kept 100% 1:1 synced)
    cn_en_1 = (SRC_ROOT / "en_dicts/cn_en.txt").read_text(encoding="utf-8").splitlines()
    cn_en_2 = (SRC_ROOT / "en_dicts/cn_en_double_pinyin.txt").read_text(encoding="utf-8").splitlines()
    assert len(cn_en_1) == len(cn_en_2), "cn_en line count mismatch"
    cn_en_delete = {"n遍", "动L", "e仔", "k他命"}
    cn_en_rename = {"Up主": "UP主", "Cinity厅": "CINITY厅", "Papi酱": "papi酱"}
    out1, out2 = [], []
    del_cnt, fix_cnt = 0, 0
    for l1, l2 in zip(cn_en_1, cn_en_2):
        if not l1.strip() or l1.strip().startswith("#"):
            out1.append(l1)
            out2.append(l2)
            continue
        p1 = l1.split("\t")
        p2 = l2.split("\t")
        w = p1[0]
        if w in cn_en_delete:
            del_cnt += 1
            continue
        if w in cn_en_rename:
            p1[0] = cn_en_rename[w]
            p2[0] = cn_en_rename[w]
            fix_cnt += 1
        out1.append("\t".join(p1))
        out2.append("\t".join(p2))
    (en_dir / "cn_en.txt").write_text("\n".join(out1) + "\n", encoding="utf-8", newline="\n")
    (en_dir / "cn_en_double_pinyin.txt").write_text("\n".join(out2) + "\n", encoding="utf-8", newline="\n")
    manifest["files"]["en_dicts/cn_en.txt"] = {"before": len(cn_en_1), "after": len(out1), "fixed": fix_cnt, "deleted": del_cnt}
    manifest["files"]["en_dicts/cn_en_double_pinyin.txt"] = {"before": len(cn_en_2), "after": len(out2), "fixed": fix_cnt, "deleted": del_cnt}


def clean_opencc_texts(manifest: dict) -> None:
    occ_dir = DST_ROOT / "opencc"
    occ_dir.mkdir(parents=True, exist_ok=True)

    # 1. opencc/others.txt
    src_lines = (SRC_ROOT / "opencc/others.txt").read_text(encoding="utf-8").splitlines()
    has_sigma_ma = any(l.startswith("西格玛\t") for l in src_lines)
    out = []
    fixes = 0
    for line in src_lines:
        orig = line
        if line == "匚部\t匚部":
            line = "匚部\t匚部 匚"
        elif line == "春字头\t春字头 春":
            line = "春字头\t春字头 𡗗"
        elif line == "爱原沙耶\t爱原沙耶 爱原さえ":
            line = "爱原沙耶\t爱原沙耶 愛原さえ"
        elif line == "铃原爱蜜莉\t铃原爱蜜莉 铃原エミリ":
            line = "铃原爱蜜莉\t铃原爱蜜莉 鈴原エミリ"
        elif line == "崎惠梨香\t崎惠梨香 尾崎えりか":
            line = "尾崎惠梨香\t尾崎惠梨香 尾崎えりか"
        elif line == "桐谷茉莉\t桐谷茉莉  桐谷まつり":
            line = "桐谷茉莉\t桐谷茉莉 桐谷まつり"
        elif line == "未步奈奈\t未歩奈奈 未歩なな":
            line = "未步奈奈\t未步奈奈 未歩なな"
        elif line == "tab\ttab ⇥ \t":
            line = "tab\ttab ⇥"
        elif line == "两个竟\t两个竟 竸":
            line = "两个竞\t两个竞 竸"
        elif line == "亚硫酸钠\t亚硫酸钠 NaSO₃":
            line = "亚硫酸钠\t亚硫酸钠 Na₂SO₃"
        elif line == "蓝矾\t蓝矾 CuSO₄·₅H₂O":
            line = "蓝矾\t蓝矾 CuSO₄·5H₂O"
        elif line.startswith("V肤色\t") and line != "V肤色\tV肤色 🏻 🏼 🏽 🏾 🏿":
            line = "V肤色\tV肤色 🏻 🏼 🏽 🏾 🏿"
        elif line.startswith("V动物\t"):
            k, v = line.split("\t", 1)
            toks = v.split()
            dedup_toks = list(dict.fromkeys(toks))
            line = f"{k}\t{' '.join(dedup_toks)}"
        elif line == "克西\t克西 ξ Ξ":
            line = "克西\t克西 xi ξ Ξ"
        elif line == "西格马\t西格马 sigma σ/ς Σ":
            line = "西格马\t西格马 sigma σ ς Σ"
            out.append(line)
            fixes += 1
            if not has_sigma_ma:
                out.append("西格玛\t西格玛 sigma σ ς Σ")
                fixes += 1
            continue
        elif "  " in line and "\t" in line:
            k, v = line.split("\t", 1)
            line = f"{k}\t{' '.join(v.split())}"
        if line != orig:
            fixes += 1
        out.append(line)
    (occ_dir / "others.txt").write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    manifest["files"]["opencc/others.txt"] = {"before": len(src_lines), "after": len(out), "fixed": fixes}

    # 2. opencc/chinese_english.txt (clean archaic slurs)
    ce_path = SRC_ROOT / "opencc/chinese_english.txt"
    if ce_path.exists():
        ce_lines = ce_path.read_text(encoding="utf-8").splitlines()
        ce_out = []
        ce_fixed = 0
        for line in ce_lines:
            if line == "黑人\t黑人 Ethiopian Negro negroid blackamoor black unregistered\u00a0person":
                line = "黑人\t黑人 black\u00a0person black unregistered\u00a0person"
                ce_fixed += 1
            ce_out.append(line)
        (occ_dir / "chinese_english.txt").write_text("\n".join(ce_out) + "\n", encoding="utf-8", newline="\n")
        manifest["files"]["opencc/chinese_english.txt"] = {"before": len(ce_lines), "after": len(ce_out), "fixed": ce_fixed}

    # 3. opencc/english_chinese.txt (remove multi-word space-containing keys that split echo tokens)
    ec_path = SRC_ROOT / "opencc/english_chinese.txt"
    if ec_path.exists():
        ec_lines = ec_path.read_text(encoding="utf-8").splitlines()
        ec_out = []
        ec_del = 0
        for line in ec_lines:
            if "\t" in line and " " in line.split("\t", 1)[0]:
                ec_del += 1
                continue
            ec_out.append(line)
        (occ_dir / "english_chinese.txt").write_text("\n".join(ec_out) + "\n", encoding="utf-8", newline="\n")
        manifest["files"]["opencc/english_chinese.txt"] = {"before": len(ec_lines), "after": len(ec_out), "deleted": ec_del}


# ---------------------------------------------------------------------------
# Main pipeline + global cross-file deduplication + invariant verification
# ---------------------------------------------------------------------------

def main() -> None:
    global SRC_ROOT, DST_ROOT
    ap = argparse.ArgumentParser(description="Clean and deduplicate rime-chth1z dictionaries in place.")
    ap.add_argument("--src-dir", type=pathlib.Path, default=REPO_ROOT)
    ap.add_argument("--out-dir", type=pathlib.Path, default=None, help="Defaults to --src-dir (in-place)")
    ap.add_argument("--manifest", type=pathlib.Path, default=None, help="Optional path to write JSON summary")
    args = ap.parse_args()

    SRC_ROOT = args.src_dir.resolve()
    DST_ROOT = (args.out_dir or args.src_dir).resolve()
    (DST_ROOT / "cn_dicts").mkdir(parents=True, exist_ok=True)
    (DST_ROOT / "cn_dicts_cell").mkdir(parents=True, exist_ok=True)

    manifest: dict = {"files": {}, "summary": {}}

    # Ordered by global deduplication precedence
    cn_plan = [
        ("cn_dicts/8105.dict.yaml", clean_8105),
        ("cn_dicts/base.dict.yaml", clean_base),
        ("cn_dicts/ext.dict.yaml", clean_ext),
        ("cn_dicts/others.dict.yaml", clean_others),
        ("cn_dicts/corrections.dict.yaml", clean_corrections),
        ("cn_dicts_cell/literature.dict.yaml", clean_literature),
        ("cn_dicts_cell/idiom.dict.yaml", clean_idiom),
        ("cn_dicts_cell/history.dict.yaml", clean_history),
        ("cn_dicts_cell/geography.dict.yaml", clean_geography),
        ("cn_dicts_cell/place.dict.yaml", clean_place),
        ("cn_dicts_cell/shulihua.dict.yaml", clean_shulihua),
        ("cn_dicts_cell/medication.dict.yaml", clean_medication),
        ("cn_dicts_cell/industry_product.dict.yaml", clean_industry_product),
        ("cn_dicts_cell/sport.dict.yaml", clean_sport),
        ("cn_dicts_cell/animal.dict.yaml", clean_animal),
        ("cn_dicts_cell/chess.dict.yaml", clean_chess),
        ("cn_dicts_cell/chess2.dict.yaml", clean_chess2),
        ("cn_dicts_cell/music.dict.yaml", clean_music),
        ("cn_dicts_cell/computer.dict.yaml", clean_generic),
        ("cn_dicts_cell/media.dict.yaml", clean_generic),
        ("cn_dicts_cell/inputmethod.dict.yaml", clean_inputmethod),
        ("cn_dicts_cell/food.dict.yaml", clean_food),
        ("cn_dicts_cell/game.dict.yaml", clean_game),
        ("cn_dicts_cell/name.dict.yaml", clean_name),
        ("cn_dicts_cell/name2.dict.yaml", clean_name2),
        ("cn_dicts_cell/exthot.dict.yaml", clean_exthot),
        ("cn_dicts_cell/composite.dict.yaml", clean_composite),
        ("cn_dicts_cell/luna.dict.yaml", clean_luna),
    ]

    # Step 1: per-file cleaning + within-file deduplication (keep highest weight)
    cleaned_files: dict[str, list[str]] = {}
    file_stats: dict[str, Counter] = {}
    before_entries_total = 0
    for rel, cleaner in cn_plan:
        raw_lines = (SRC_ROOT / rel).read_text(encoding="utf-8").splitlines()
        before_entries = sum(1 for l in raw_lines if parse_entry(l) is not None)
        before_entries_total += before_entries
        st: Counter = Counter()
        st["before_entries"] = before_entries
        out_lines = cleaner(raw_lines, st)

        # Within-file dedup (keep max weight for exact (word, py))
        hdr, body = split_header_body(out_lines)
        best_wt: dict[tuple[str, str], int] = {}
        for l in body:
            p = parse_entry(l)
            if p:
                k = (p[0], p[1])
                v = w_int(p[2])
                if k not in best_wt or v > best_wt[k]:
                    best_wt[k] = v
        dedup_body = []
        emitted = set()
        for l in body:
            p = parse_entry(l)
            if not p:
                dedup_body.append(l)
                continue
            k = (p[0], p[1])
            if k in emitted:
                st["dedup_within_file"] += 1
                continue
            emitted.add(k)
            wt_str = str(best_wt[k]) if p[2] != "" else ""
            dedup_body.append(format_entry(p[0], p[1], wt_str, p[3]))
        cleaned_files[rel] = hdr + dedup_body
        file_stats[rel] = st

    # Step 2: global cross-file deduplication (excluding corrections.dict.yaml from polluting global_seen,
    # and excluding luna.dict.yaml from global_seen since luna is disabled in backup rime_frost.dict.yaml)
    global_seen: set[tuple[str, str]] = set()
    after_entries_total = 0
    after_active_entries_total = 0

    for rel, _ in cn_plan:
        lines = cleaned_files[rel]
        hdr, body = split_header_body(lines)
        st = file_stats[rel]
        is_corrections = rel == "cn_dicts/corrections.dict.yaml"
        is_luna = rel == "cn_dicts_cell/luna.dict.yaml"
        final_body = []
        for l in body:
            p = parse_entry(l)
            if not p:
                final_body.append(l)
                continue
            k = (p[0], p[1])
            if not is_corrections and k in global_seen:
                st["dedup_cross_file"] += 1
                continue
            if not is_corrections and not is_luna:
                global_seen.add(k)
            final_body.append(l)
        final_lines = hdr + final_body
        after_entries = sum(1 for l in final_body if parse_entry(l) is not None)
        st["after_entries"] = after_entries
        after_entries_total += after_entries
        if not is_luna:
            after_active_entries_total += after_entries
        (DST_ROOT / rel).write_text("\n".join(final_lines) + "\n", encoding="utf-8", newline="\n")
        manifest["files"][rel] = dict(st)

    # Step 3: ensure cn_dicts_cell/luna is disabled in rime_frost.dict.yaml
    rf_lines = (SRC_ROOT / "rime_frost.dict.yaml").read_text(encoding="utf-8").splitlines()
    rf_out = []
    for l in rf_lines:
        if l.strip() == "- cn_dicts_cell/luna":
            rf_out.append("  # - cn_dicts_cell/luna  # 繁体异体与冗余词条较多，默认关闭")
        else:
            rf_out.append(l)
    (DST_ROOT / "rime_frost.dict.yaml").write_text("\n".join(rf_out) + "\n", encoding="utf-8", newline="\n")

    # Step 4: English & OpenCC
    clean_en_dicts(manifest)
    clean_opencc_texts(manifest)

    # Step 5: Post-cleanup invariant verification across ALL 27 CN dicts in DST_ROOT
    valid_syls = set()
    for l in (DST_ROOT / "cn_dicts/8105.dict.yaml").read_text(encoding="utf-8").splitlines():
        p = parse_entry(l)
        if p:
            valid_syls.add(p[1])
    valid_syls.update({"hm", "hng", "m", "n", "ng"})

    v_invalid_syls = []
    v_len_mismatch = []
    v_lue_nue = []
    v_within_dups = 0
    v_cross_dups = 0
    v_global = set()

    for rel, _ in cn_plan:
        local_seen = set()
        is_corr = rel == "cn_dicts/corrections.dict.yaml"
        is_luna = rel == "cn_dicts_cell/luna.dict.yaml"
        for idx, l in enumerate((DST_ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            p = parse_entry(l)
            if not p:
                continue
            w, py, _, _ = p
            syls = py.split()
            if re.search(r"\b[ln]ue\b", py):
                v_lue_nue.append((rel, idx, w, py))
            for sy in syls:
                if sy not in valid_syls:
                    v_invalid_syls.append((rel, idx, w, py, sy))
            # Allow middle dot · in length check; skip intentional typo-triggers in corrections.dict.yaml
            w_nodot = w.replace("·", "")
            if not is_corr and len(syls) != len(w_nodot):
                v_len_mismatch.append((rel, idx, w, py))
            k = (w, py)
            if k in local_seen:
                v_within_dups += 1
            local_seen.add(k)
            if not is_corr and not is_luna:
                if k in v_global:
                    v_cross_dups += 1
                v_global.add(k)

    manifest["summary"] = {
        "before_cn_entries_28_files": before_entries_total,
        "after_cn_entries_all_28_files": after_entries_total,
        "after_cn_entries_active_27_files_excl_luna": after_active_entries_total,
        "verification": {
            "invalid_syllables": len(v_invalid_syls),
            "invalid_syllable_samples": v_invalid_syls[:10],
            "len_mismatches": len(v_len_mismatch),
            "len_mismatch_samples": v_len_mismatch[:10],
            "remaining_lue_nue": len(v_lue_nue),
            "within_file_dups": v_within_dups,
            "cross_file_dups_active_27": v_cross_dups,
        },
    }
    if args.manifest:
        args.manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )

    print("=== CLEANUP SUMMARY ===")
    print(f"Before (28 CN dicts):        {before_entries_total:>10,}")
    print(f"After  (28 CN dicts):        {after_entries_total:>10,}")
    print(f"After  (27 active, -luna):   {after_active_entries_total:>10,}")
    print(f"Delta  (active vs before):   {after_active_entries_total - before_entries_total:>+10,}")
    print("=== POST-CLEANUP INVARIANTS ===")
    print(json.dumps(manifest["summary"]["verification"], ensure_ascii=False, indent=2))
    print("\n=== PER-FILE DELTAS ===")
    for rel, st in manifest["files"].items():
        if "before_entries" in st:
            b, a = st["before_entries"], st["after_entries"]
            extras = {k: v for k, v in st.items() if k not in ("before_entries", "after_entries") and v}
            if b != a or extras:
                print(f"  {rel:42s}: {b:>7,} -> {a:>7,} ({a-b:>+8,})  {extras}")
        else:
            print(f"  {rel:42s}: {st}")

    ver = manifest["summary"]["verification"]
    if (
        ver["invalid_syllables"]
        or ver["len_mismatches"]
        or ver["remaining_lue_nue"]
        or ver["within_file_dups"]
        or ver["cross_file_dups_active_27"]
    ):
        raise SystemExit("Post-cleanup invariant check failed!")


if __name__ == "__main__":
    main()
