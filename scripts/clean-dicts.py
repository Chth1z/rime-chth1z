#!/usr/bin/env python3
"""
Deterministic, idempotent dictionary and OpenCC data cleaner for rime-chth1z.
Applies structural/algorithmic cleaners, loads declarative overrides from rules/
(see docs/DICTIONARY_SPEC.md), deduplicates across active tables, and verifies
post-cleanup invariants.

Run directly after syncing upstream rime-frost dictionaries:
    python scripts/clean-dicts.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import Counter

import build_cn_en
import dict_rules

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT
DST_ROOT = REPO_ROOT

# ---------------------------------------------------------------------------
# Traditional / Japanese Shinjitai -> Simplified Chinese character map
# ---------------------------------------------------------------------------

_TRAD_JP_BASE_MAP: dict[str, str] = {
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
    "錘": "锤", "錦": "锦", "錫": "锡", "錳": "锰", "鍺": "锗", "鎂": "镁", "鎖": "锁",
    "鎘": "镉", "鎚": "锤", "鎢": "钨", "鎧": "铠", "鎮": "镇", "鎳": "镍", "鐐": "镣", "鐘": "钟",
    "鐮": "镰", "鐵": "铁", "鑄": "铸", "鑰": "钥", "鑼": "锣", "鑽": "钻", "長": "长", "門": "门",
    "間": "间", "関": "关", "陸": "陆", "陽": "阳", "隸": "隶", "雙": "双", "難": "难", "雲": "云",
    "靈": "灵", "響": "响", "頂": "顶", "項": "项", "順": "顺", "須": "须", "預": "预", "頑": "顽",
    "頭": "头", "願": "愿", "顧": "顾", "顯": "显", "顱": "颅", "風": "风", "颯": "飒", "飚": "飙",
    "飛": "飞", "飯": "饭", "飾": "饰", "餘": "余", "館": "馆", "馬": "马", "馭": "驭", "駒": "驹",
    "騎": "骑", "驕": "骄", "髏": "髅", "髙": "高", "髮": "发", "鬥": "斗", "魚": "鱼", "鯨": "鲸",
    "鰂": "鲗", "鱗": "鳞", "鴉": "鸦", "鷹": "鹰", "鹼": "碱", "鹽": "盐", "麗": "丽", "麥": "麦",
    "黃": "黄", "黒": "黑", "點": "点", "齋": "斋", "齒": "齿", "龍": "龙",
}

_TRAD_JP_EXTRA_MAP: dict[str, str] = {
    "鳥": "鸟", "飼": "饲", "風": "风", "結": "结", "緒": "绪", "鷺": "鹭",
    "頼": "赖", "詩": "诗", "広": "广", "厳": "严", "竜": "龙", "飛": "飞",
    "撃": "击", "賊": "贼", "鉄": "铁", "剣": "剑", "貴": "贵", "樹": "树",
    "來": "来", "俠": "侠", "嗎": "吗", "鈉": "钠", "澤": "泽", "櫻": "樱",
    "國": "国", "學": "学", "會": "会", "體": "体", "點": "点", "與": "与",
    "華": "华", "東": "东", "萬": "万", "無": "无", "開": "开", "關": "关",
    "門": "门", "長": "长", "馬": "马", "魚": "鱼", "龍": "龙", "齊": "齐",
    "齒": "齿", "龜": "龟", "葉": "叶", "夢": "梦", "實": "实", "寶": "宝",
    "將": "将", "專": "专", "對": "对", "導": "导", "層": "层", "歲": "岁",
    "島": "岛", "嶺": "岭", "師": "师", "帳": "帐", "幣": "币", "廣": "广",
    "張": "张", "強": "强", "歸": "归", "錄": "录", "當": "当", "後": "后",
    "從": "从", "復": "复", "憶": "忆", "應": "应", "懷": "怀", "懸": "悬",
    "戰": "战", "戲": "戏", "戶": "户", "撲": "扑", "據": "据", "擇": "择",
    "擊": "击", "擬": "拟", "擴": "扩", "擾": "扰", "攝": "摄", "數": "数",
    "敵": "敌", "斷": "断", "時": "时", "書": "书", "術": "术", "條": "条",
    "構": "构", "槍": "枪", "樣": "样", "標": "标", "樂": "乐", "樓": "楼",
    "橋": "桥", "機": "机", "橫": "横", "檔": "档", "檢": "检", "權": "权",
    "歡": "欢", "歷": "历", "殘": "残", "殺": "杀", "毀": "毁", "氣": "气",
    "決": "决", "沒": "没", "沖": "冲", "況": "况", "測": "测", "溫": "温",
    "準": "准", "溝": "沟", "滅": "灭", "滿": "满", "漁": "渔", "漢": "汉",
    "漲": "涨", "漸": "渐", "漿": "浆", "潔": "洁", "潛": "潜", "潤": "润",
    "濟": "济", "濤": "涛", "濱": "滨", "濺": "溅", "濾": "滤", "瀉": "泻",
    "灣": "湾", "災": "灾", "為": "为", "烏": "乌", "煙": "烟", "煩": "烦",
    "熱": "热", "燈": "灯", "燒": "烧", "營": "营", "燦": "灿", "爐": "炉",
    "爛": "烂", "爭": "争", "爾": "尔", "牆": "墙", "獎": "奖", "獨": "独",
    "獄": "狱", "獵": "猎", "獸": "兽", "獻": "献", "現": "现", "環": "环",
    "電": "电", "畫": "画", "療": "疗", "發": "发", "監": "监", "盡": "尽",
    "盤": "盘", "盧": "卢", "眾": "众", "睜": "睁", "確": "确", "碼": "码",
    "礎": "础", "礦": "矿", "禮": "礼", "稱": "称", "種": "种", "穀": "谷",
    "積": "积", "穩": "稳", "競": "竞", "筆": "笔", "築": "筑", "簡": "简",
    "籌": "筹", "簽": "签", "籃": "篮", "糧": "粮", "糰": "团", "約": "约",
    "紅": "红", "級": "级", "紀": "纪", "純": "纯", "紙": "纸", "紛": "纷",
    "納": "纳", "細": "细", "紳": "绅", "紹": "绍", "終": "终", "組": "组",
    "絕": "绝", "絞": "绞", "絡": "络", "給": "给", "統": "统", "絲": "丝",
    "經": "经", "綜": "综", "綠": "绿", "維": "维", "綱": "纲", "網": "网",
    "綴": "缀", "緊": "紧", "線": "线", "練": "练", "編": "编", "緩": "缓",
    "緬": "缅", "緯": "纬", "總": "总", "績": "绩", "縮": "缩", "縱": "纵",
    "縫": "缝", "織": "织", "繞": "绕", "繪": "绘", "繳": "缴", "繼": "继",
    "續": "续", "纖": "纤", "纜": "缆", "羅": "罗", "罰": "罚", "罵": "骂",
    "罷": "罢", "義": "义", "習": "习", "聖": "圣", "聞": "闻", "聯": "联",
    "聰": "聪", "聲": "声", "職": "职", "聽": "听", "肅": "肃", "腸": "肠",
    "膚": "肤", "腎": "肾", "脹": "胀", "腦": "脑", "腳": "脚", "脫": "脱",
    "臉": "脸", "膽": "胆", "膿": "脓", "膠": "胶", "膩": "腻", "臟": "脏",
    "臨": "临", "舉": "举", "舊": "旧", "艦": "舰", "艱": "艰", "豔": "艳",
    "藝": "艺", "節": "节", "茲": "兹", "荊": "荆", "莊": "庄", "萊": "莱",
    "蔥": "葱", "蔣": "蒋", "藍": "蓝", "藥": "药", "蘇": "苏", "蘭": "兰",
    "處": "处", "號": "号", "虧": "亏", "蟲": "虫", "蝕": "蚀", "螢": "萤",
    "蟬": "蝉", "蟻": "蚁", "衛": "卫", "衝": "冲", "補": "补", "裝": "装", "製": "制",
    "複": "复", "褲": "裤", "襲": "袭", "見": "见", "規": "规", "視": "视",
    "覽": "览", "覺": "觉", "觀": "观", "觸": "触", "計": "计", "訂": "订",
    "訊": "讯", "討": "讨", "訓": "训", "託": "托", "記": "记", "訪": "访",
    "設": "设", "許": "许", "訴": "诉", "診": "诊", "註": "注", "證": "证",
    "評": "评", "詞": "词", "試": "试", "話": "话", "該": "该", "詳": "详",
    "誇": "夸", "認": "认", "誕": "诞", "誘": "诱", "語": "语", "誠": "诚",
    "誤": "误", "說": "说", "誰": "谁", "課": "课", "調": "调", "談": "谈",
    "請": "请", "論": "论", "諸": "诸", "諾": "诺", "謀": "谋", "謂": "谓",
    "謎": "谜", "謝": "谢", "謹": "谨", "譜": "谱", "識": "识", "議": "议",
    "護": "护", "譽": "誉", "讀": "读", "變": "变", "讓": "让", "讚": "赞",
    "豈": "岂", "豎": "竖", "豐": "丰", "豬": "猪", "貓": "猫", "貝": "贝",
    "貞": "贞", "負": "负", "財": "财", "貢": "贡", "貧": "贫", "貨": "货",
    "販": "贩", "貪": "贪", "貫": "贯", "責": "责", "買": "买", "貸": "贷",
    "費": "费", "貼": "贴", "貿": "贸", "賀": "贺", "資": "资", "賈": "贾",
    "賓": "宾", "賜": "赐", "賞": "赏", "賠": "赔", "賢": "贤", "賣": "卖",
    "賦": "赋", "質": "质", "賬": "账", "賭": "赌", "賴": "赖", "賺": "赚",
    "購": "购", "賽": "赛", "贊": "赞", "贈": "赠", "贏": "赢", "趕": "赶",
    "趙": "赵", "趨": "趋", "躍": "跃", "車": "车", "軌": "轨", "軍": "军",
    "軒": "轩", "軟": "软", "軸": "轴", "較": "较", "載": "载", "輔": "辅",
    "輕": "轻", "輛": "辆", "輝": "辉", "輩": "辈", "輪": "轮", "輯": "辑",
    "輸": "输", "轉": "转", "轟": "轰", "辭": "辞", "辯": "辩", "農": "农",
    "這": "这", "進": "进", "遠": "远", "違": "违", "連": "连", "遲": "迟",
    "運": "运", "過": "过", "達": "达", "適": "适", "選": "选", "遺": "遗",
    "還": "还", "邁": "迈", "邊": "边", "邏": "逻", "郵": "邮", "鄉": "乡",
    "鄭": "郑", "鄰": "邻", "醫": "医", "醬": "酱", "釀": "酿", "釋": "释",
    "針": "针", "釣": "钓", "鈣": "钙", "鈍": "钝", "鈔": "钞",
    "鐘": "钟", "鋼": "钢", "錢": "钱", "錦": "锦", "錫": "锡", "錯": "错",
    "鍋": "锅", "鍵": "键", "鍛": "锻", "鎖": "锁", "鎮": "镇", "鏡": "镜",
    "鐵": "铁", "鑒": "鉴", "鑽": "钻", "閃": "闪", "閉": "闭", "問": "问",
    "閒": "闲", "間": "间", "悶": "闷", "閘": "闸", "鬧": "闹", "閱": "阅",
    "闊": "阔", "闆": "板", "闡": "阐", "闢": "辟", "陣": "阵", "陰": "阴",
    "陳": "陈", "陸": "陆", "陽": "阳", "階": "阶", "際": "际", "隨": "随",
    "險": "险", "隱": "隐", "隸": "隶", "隻": "只", "雖": "虽", "雙": "双",
    "雜": "杂", "雞": "鸡", "離": "离", "難": "难", "雲": "云", "霧": "雾",
    "靜": "静", "響": "响", "頁": "页", "頂": "顶", "項": "项", "順": "顺",
    "須": "须", "頌": "颂", "預": "预", "頑": "顽", "頒": "颁", "領": "领",
    "頭": "头", "頻": "频", "顆": "颗", "題": "题", "額": "额", "顏": "颜",
    "願": "愿", "顛": "颠", "類": "类", "顧": "顾", "顯": "显", "飄": "飘",
    "飯": "饭", "飲": "饮", "飾": "饰", "飽": "饱", "餅": "饼", "養": "养",
    "餘": "余", "館": "馆", "驅": "驱", "駐": "驻", "駕": "驾", "駛": "驶",
    "騎": "骑", "騙": "骗", "騷": "骚", "驗": "验", "驚": "惊", "驛": "驿",
    "驟": "骤", "髮": "发", "鬆": "松", "鬥": "斗", "鬱": "郁", "魯": "鲁",
    "鮮": "鲜", "鯨": "鲸", "鳳": "凤", "鳴": "鸣", "鴨": "鸭", "鴻": "鸿",
    "鵝": "鹅", "鷹": "鹰", "鹼": "碱", "鹽": "盐", "麗": "丽", "麥": "麦",
    "麵": "面", "麼": "么", "黃": "黄", "黨": "党", "齡": "龄", "乗": "乘",
    "児": "儿", "団": "团", "図": "图", "売": "卖", "変": "变", "実": "实",
    "専": "专", "対": "对", "戦": "战", "抜": "拔", "択": "择",
    "拠": "据", "挙": "举", "気": "气", "沢": "泽", "済": "济", "満": "满",
    "焼": "烧", "獣": "兽", "発": "发", "県": "县", "穏": "稳", "経": "经",
    "絵": "绘", "続": "续", "総": "总", "縁": "缘", "縄": "绳", "縦": "纵",
    "繊": "纤", "聴": "听", "脳": "脑", "臓": "脏", "薬": "药",
    "処": "处", "蛍": "萤", "覚": "觉", "観": "观", "訳": "译", "証": "证",
    "読": "读", "譲": "让", "豊": "丰", "賛": "赞", "転": "转", "軽": "轻",
    "辺": "边", "遅": "迟", "鉱": "矿", "銭": "钱", "録": "录", "関": "关",
    "険": "险", "隠": "隐", "雑": "杂", "霊": "灵", "顔": "颜", "顕": "显",
    "騒": "骚", "験": "验", "髪": "发", "鶏": "鸡", "麺": "面", "黒": "黑",
    "黙": "默", "歯": "齿", "齢": "龄", "亀": "龟",
}

_TRAD_JP_COMBINED = {**_TRAD_JP_EXTRA_MAP, **_TRAD_JP_BASE_MAP}
TRAD_JP_TO_SIMP = str.maketrans(_TRAD_JP_COMBINED)
SHULIHUA_TW_T2S = str.maketrans({**_TRAD_JP_COMBINED, "醯": "酰"})


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


def fix_non_shenme_shi(word: str, py: str) -> str:
    """Fix systemic foreign-name/title 什 shen -> shi while preserving 什么/甚么."""
    if "什" not in word or "shen" not in py.split():
        return py
    if any(ok in word for ok in ("什么", "甚么")):
        return py
    return replace_syl_at(word, py, "什", "shen", "shi")


def is_game_quantifier_fragment(word: str) -> bool:
    """Identify digit-stripped quantifier fragments inside game quest block."""
    if len(word) < 3 or len(word) > 5:
        return False
    return word[0] in "个名件只点次颗块条张把面匹根段层套枚座辆架艘" and word not in {
        "个人赛", "点金手", "点头哈腰", "面具男", "把戏师",
    }


def normalize_shulihua_corrupted_py(word: str, py: str) -> str:
    """Fix systemic chemical auto-pinyin bugs in shulihua.dict.yaml."""
    out = py
    if "酰" in word and "xi" in out.split():
        out = replace_syl_at(word, out, "酰", "xi", "xian")
    if "缩水" in word and "su" in out.split():
        out = replace_syl_at(
            word, out, "缩", "su", "suo",
            cond=lambda wd, sy, i: i + 1 < len(wd) and wd[i + 1] == "水",
        )
    if "无水" in word and "mo" in out.split():
        out = replace_syl_at(
            word, out, "无", "mo", "wu",
            cond=lambda wd, sy, i: i + 1 < len(wd) and wd[i + 1] == "水",
        )
    if "锗" in word and "du" in out.split():
        out = replace_syl_at(word, out, "锗", "du", "zhe")
    if "纤维" in word and "jian" in out.split():
        out = replace_syl_at(
            word, out, "纤", "jian", "xian",
            cond=lambda wd, sy, i: i + 1 < len(wd) and wd[i + 1] == "维",
        )
    return out


# ---------------------------------------------------------------------------
# Algorithmic structural rule sets (not entry-level overrides)
# ---------------------------------------------------------------------------

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

GAME_CHANG_PREFIXES: tuple[str, ...] = (
    "长角", "长牙剑", "长牙头盔", "长牙战斧", "长牙黑豹",
    "长角恐兽", "长角兽", "长牙帮",
)

LEXICAL_LEADING_DE = {
    "的确", "的话", "的士", "的卢", "的哥", "的姐", "的当", "的黎波里", "的里雅斯特", "的的喀喀湖", "的确良",
    "的笃", "的溜", "的砾", "的然", "的实", "的真", "的证", "的字", "的字结构",
}


def is_leading_de_fragment(word: str, py: str) -> bool:
    if not word.startswith("的") or len(word) < 2:
        return False
    if word in LEXICAL_LEADING_DE:
        return False
    if any(word.startswith(p) for p in ("的士", "的确", "的卢", "的哥", "的姐", "的黎波里", "的里雅斯特", "的的喀喀")):
        return False
    return py.startswith("de ")


def is_leading_le_fragment(word: str, py: str) -> bool:
    return word.startswith("了") and len(word) >= 2 and py.startswith("le ")


# ---------------------------------------------------------------------------
# Per-file structural cleaners (static overrides live in rules/*.tsv)
# ---------------------------------------------------------------------------


def clean_strip_blanks(lines: list[str], stats: dict) -> list[str]:
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


def clean_8105(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        out.append(format_entry(*parsed))
    return out


def clean_base(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    shei_wt: dict[str, int] = {}
    has_zijihai = False
    for line in body:
        p = parse_entry(line)
        if not p:
            continue
        if p[0] in BASE_SHUI_SCALE_WORDS and "shei" in p[1].split():
            shei_wt[p[0]] = max(shei_wt.get(p[0], 0), w_int(p[2]))
        if p[0] == "自己还" and p[1] == "zi ji hai":
            has_zijihai = True

    out = list(hdr)
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        # Preserve upstream '自己还 zi ji huan 969' -> 'zi ji hai 969' while keeping added 'zi ji huan 150' idempotent
        if not has_zijihai and w == "自己还" and py == "zi ji huan":
            py = "zi ji hai"
            stats["fixed_py"] += 1
        if w in BASE_XIE_DOWNWEIGHT_WORDS and "xie" in py.split():
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
        out.append(format_entry(w, py, wt, extra))
    return out


EXT_STANDARD_XIE_MARKERS: tuple[str, ...] = (
    "一针见血", "血淋淋", "血糊糊", "血晕", "流鼻血", "鼻血",
    "鸡血", "狗血", "鸭血", "猪血", "羊血", "毛血旺",
)


def clean_ext(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    has_xue: set[str] = set()
    for line in body:
        p = parse_entry(line)
        if p and "血" in p[0] and any(ch == "血" and sy == "xue" for ch, sy in zip(p[0], p[1].split())):
            has_xue.add(p[0])

    out = list(hdr)
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if is_leading_de_fragment(w, py) or is_leading_le_fragment(w, py):
            stats["deleted_noise_or_typo"] += 1
            continue
        # Downweight medical xie clones in ext only when a xue twin exists and not a standard xiě idiom
        if (
            "血" in w
            and w in has_xue
            and not any(m in w for m in EXT_STANDARD_XIE_MARKERS)
            and any(ch == "血" and sy == "xie" for ch, sy in zip(w, py.split()))
            and w_int(wt) > 50
        ):
            wt = str(min(w_int(wt) // 8, 50))
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_others(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    in_legacy_block = False
    in_diezi_block = False
    for line in body:
        stripped = line.strip()
        if stripped.startswith("##### 错音错字提示"):
            in_legacy_block = True
            continue
        if in_legacy_block:
            if stripped.startswith("##### 叠字"):
                in_legacy_block = False
                in_diezi_block = True
            else:
                if parse_entry(line):
                    stats["deleted_legacy_hijack"] += 1
                continue
        if stripped.startswith("##### 叠字"):
            in_diezi_block = True
        elif stripped.startswith("##### ") and not stripped.startswith("##### 叠字"):
            in_diezi_block = False
        if "这里额外加上 hao 音" in line or "补充 gao 容错读音" in line:
            out.append("# 这里的「镐」规范读音为 hao，补充正音与容错读音")
            continue
        parsed = parse_entry(line)
        if not parsed:
            if stripped.startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if in_diezi_block and w.startswith(("两个", "三个", "四个")) and w_int(wt) > 0:
            wt = "0"
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_corrections(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        out.append(format_entry(*parsed))
    return out


def clean_food(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    poi_span = find_entry_span(body, ("阿巴尼", "a ba ni"), ("昨重", "zuo zhong"), next_word="阿宝面")
    out = list(hdr)
    braise_markers = ("扒菜", "扒鸡", "扒鸭", "扒鱼", "扒肉", "扒肘", "扒翅", "扒鲍", "扒海", "扒豆腐", "扒白菜", "扒菇")
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
        new_py = replace_syl_at(w, py, "粿", "hua", "guo")
        if new_py != py:
            py = new_py
            stats["fixed_py"] += 1
        new_py = replace_syl_at(w, py, "参", "can", "shen")
        if new_py != py:
            py = new_py
            stats["fixed_py"] += 1
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
        if untypable_re.search(py):
            stats["deleted_untypable"] += 1
            continue
        if hk_span and hk_span[0] <= offset <= hk_span[1]:
            sim_w = CC_T2S.convert(w)
            if sim_w != w:
                w = sim_w
                stats["fixed_word_or_trad"] += 1
        for words_set, ch, old_s, new_s in (
            (chang_words, "长", "zhang", "chang"),
            (du_words, "都", "dou", "du"),
            (xia_words, "厦", "sha", "xia"),
            (fo_words, "佛", "fu", "fo"),
            (chao_words, "朝", "zhao", "chao"),
            (chong_words, "涌", "yong", "chong"),
        ):
            if w in words_set:
                new_py = replace_syl_at(w, py, ch, old_s, new_s)
                if new_py != py:
                    py = new_py
                    stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_chess2(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    sec3_span = find_entry_span(body, ("八平", "ba ping"), ("卒五个", "zu wu ge"), next_word="八卒")
    out = list(hdr)
    trad_pieces = re.compile(r"[車俥馬傌砲將帥]")
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
        out.append(format_entry(w, py, wt, extra))
    return out


def post_chess_add_ju(lines: list[str], stats: dict, move_only: bool) -> list[str]:
    """Generate xiangqi '车' standard ju readings after rules/ overlay."""
    hdr, body = split_header_body(lines)
    move_re = re.compile(r"(车|前车|后车|中车).*(进|退|平)")
    existing: set[tuple[str, str]] = set()
    for line in body:
        p = parse_entry(line)
        if p:
            existing.add((p[0], p[1]))
    ju_additions: list[str] = []
    for line in body:
        p = parse_entry(line)
        if not p:
            continue
        w, py, wt, extra = p
        if "车" in w and "che" in py.split():
            if move_only and not move_re.search(w):
                continue
            ju_py = replace_syl_at(w, py, "车", "che", "ju")
            if ju_py != py and (w, ju_py) not in existing:
                ju_additions.append(format_entry(w, ju_py, wt, extra))
                existing.add((w, ju_py))
    out = hdr + body
    if ju_additions:
        if "# 象棋「车」标准 ju 读音" not in out:
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
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w in de_to_di_words:
            new_py = replace_syl_at(w, py, "地", "de", "di")
            if new_py != py:
                py = new_py
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
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if w.startswith(("其他", "其它", "二手", "库存")) or w.endswith(("代理", "项目合作")):
            stats["deleted_boilerplate_or_spam"] += 1
            continue
        if w.endswith("匙扣"):
            new_py = replace_syl_at(w, py, "匙", "chi", "shi")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_shulihua(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    tw_span = find_entry_span(body, ("愛殺松", "ai sha song"), ("重鉻酸鈉", "zhong ge suan na"))
    news_span = find_entry_span(body, ("阿拉斯加上空", "a la si jia shang kong"), ("左右的结果", "zuo you de jie guo"))
    out = list(hdr)
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
            sim_w = w.translate(SHULIHUA_TW_T2S)
            if sim_w != w:
                w = sim_w
                stats["fixed_word_or_trad"] += 1
        norm_py = normalize_shulihua_corrupted_py(w, py)
        if norm_py != py:
            py = norm_py
            stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_medication(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    spam_span_specs = (
        (("百香", "bai xiang"), ("左旋维生素", "zuo xuan wei sheng su"), "百香御"),
        (("参荷舒妍清茵宁", "can he shu yan qing yin ning"), ("滋阳御元贴", "zi yang yu yuan tie"), "焕体妙姿纤秀膏"),
        (("百克舒", "bai ke shu"), ("石上甘抑菌膏", "shi shang gan yi jun gao"), "健华牛敏康"),
        (("安舒清结", "an shu qing jie"), ("安舒清结怡乳贴", "an shu qing jie yi ru tie"), "安舒清结怡"),
        (("黄塔金方痔乐舒", "huang ta jin fang zhi le shu"), ("亿康痔乐舒", "yi kang zhi le shu"), "靖纹清创去痕膏"),
        (("桂苓十香", "gui ling shi xiang"), ("亿康桂苓十香散湿贴", "yi kang gui ling shi xiang san shi tie"), "桂苓十香散湿"),
        (("创薇修痕平纹霜", "chuang wei xiu hen ping wen shuang"), ("意中颜薏仁丸", "yi zhong yan yi ren wan"), "欢颜子益膏"),
        (("佰草固元龟舒康", "bai cao gu yuan gui shu kang"), ("竹参薏根康", "zhu can yi gen kang"), "白叶草蔓姿纤美膏"),
        (("非遗黄塔明时通筋骨膏", "fei yi huang ta ming shi tong jin gu gao"), ("亿康时通筋骨膏", "yi kang shi tong jin gu gao"), "黄塔明时通筋骨膏"),
        (("九妙丰姿莹润膏", "jiu miao feng zi ying run gao"), ("亿康青罗夏清露", "yi kang qing luo xia qing lu"), "九妙丰姿莹润饮"),
        (("白叶轻脂妙姿贴", "bai ye qing zhi miao zi tie"), ("万养堂九味舒宁怡梦膏", "wan yang tang jiu wei shu ning yi meng gao"), "冰莹玉润乳"),
    )
    spam_spans = [
        sp for s_key, e_key, nxt in spam_span_specs
        if (sp := find_entry_span(body, s_key, e_key, next_word=nxt)) is not None
    ]
    out = list(hdr)

    has_xue: set[str] = set()
    for line in body:
        p = parse_entry(line)
        if p and "血" in p[0] and any(ch == "血" and sy == "xue" for ch, sy in zip(p[0], p[1].split())):
            has_xue.add(p[0])

    for offset, line in enumerate(body):
        if any(lo <= offset <= hi for lo, hi in spam_spans):
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
        if w.startswith(("参苓", "参麦", "洋参保肺")) and "can" in py.split() and w_int(wt) == 0:
            stats["deleted_wrong_py"] += 1
            continue
        if "血" in w and any(ch == "血" and sy == "xie" for ch, sy in zip(w, py.split())):
            if w in has_xue:
                stats["deleted_xie_dup"] += 1
                continue
            new_py = replace_syl_at(w, py, "血", "xie", "xue")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def _fix_post_jp_t2s_py(orig_w: str, sim_w: str, py: str, stats: dict) -> str:
    """Repair corrupted upstream auto-pinyin carried over after Trad/JP -> Simplified conversion."""
    rules = (
        ("姫", "姬", "zhen", "ji"),
        ("豊", "丰", "li", "feng"),
        ("無", "无", "mo", "wu"),
        ("紅", "红", "gong", "hong"),
        ("見", "见", "xian", "jian"),
        ("遺", "遗", "wei", "yi"),
    )
    for orig_ch, sim_ch, bad_sy, good_sy in rules:
        if orig_ch in orig_w and bad_sy in py.split():
            new_py = replace_syl_at(sim_w, py, sim_ch, bad_sy, good_sy)
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
    if "強" in orig_w and "倔強" not in orig_w and "jiang" in py.split():
        new_py = replace_syl_at(sim_w, py, "强", "jiang", "qiang")
        if new_py != py:
            py = new_py
            stats["fixed_py"] += 1
    return py


def clean_game(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    quest_span = find_entry_span(body, ("暗虎精", "an hu jing"), ("做任务", "zuo ren wu"))
    out = list(hdr)
    for offset, line in enumerate(body):
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if quest_span and quest_span[0] <= offset <= quest_span[1] and is_game_quantifier_fragment(w):
            stats["deleted_noise_or_typo"] += 1
            continue
        orig_w = w
        sim_w = jp_t2s(w)
        if sim_w != w:
            w = sim_w
            stats["fixed_word_or_trad"] += 1
            py = _fix_post_jp_t2s_py(orig_w, w, py, stats)
        if "角斗士" in w and "jiao" in py.split():
            new_py = replace_syl_at(
                w, py, "角", "jiao", "jue",
                cond=lambda wd, sy, i: wd[i : i + 3] == "角斗士",
            )
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if "角斗士的长刺" in w and "zhang" in py.split():
            new_py = replace_syl_at(
                w, py, "长", "zhang", "chang",
                cond=lambda wd, sy, i: i + 1 < len(wd) and wd[i + 1] == "刺",
            )
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if any(w.startswith(p) for p in GAME_CHANG_PREFIXES) and "zhang" in py.split():
            new_py = replace_syl_at(w, py, "长", "zhang", "chang")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_sport(lines: list[str], stats: dict) -> list[str]:
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
        sim_w = jp_t2s(w)
        if sim_w != w:
            w = sim_w
            stats["fixed_word_or_trad"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_literature(lines: list[str], stats: dict) -> list[str]:
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
        if "囗" in w:
            stats["deleted_noise_or_typo"] += 1
            continue
        if len(w) == 1:
            stats["deleted_single_char_dup"] += 1
            continue
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_name(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    out = list(hdr)
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#") and not line.strip().startswith("#Q薰"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if "薫" in w:
            w = w.replace("薫", "薰")
            stats["fixed_word_or_trad"] += 1
        if w_int(wt) > 150:
            wt = "150"
            stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_name2(lines: list[str], stats: dict) -> list[str]:
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
        if "畠" in w and "zai" in py.split():
            new_py = replace_syl_at(w, py, "畠", "zai", "tian")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        orig_w = w
        sim_w = jp_t2s(w)
        if sim_w != w:
            w = sim_w
            stats["fixed_word_or_trad"] += 1
            py = _fix_post_jp_t2s_py(orig_w, w, py, stats)
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
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        out.append(format_entry(w, py, wt, extra))
    return out


def post_fix_non_shenme_shi(lines: list[str], stats: dict) -> list[str]:
    """Post-overlay pass: normalize non-什么 什 shen -> shi."""
    hdr, body = split_header_body(lines)
    out = list(hdr)
    for line in body:
        p = parse_entry(line)
        if not p:
            out.append(line)
            continue
        w, py, wt, extra = p
        new_py = fix_non_shenme_shi(w, py)
        if new_py != py:
            py = new_py
            stats["fixed_py"] += 1
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_animal(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    new_hdr = [
        ("use_preset_vocabulary: false" if l.strip() == "use_preset_vocabulary: true" else l)
        for l in hdr
    ]
    out = list(new_hdr)
    for line in body:
        parsed = parse_entry(line)
        if not parsed:
            if line.strip().startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        out.append(format_entry(w, py, wt, extra))
    return out


def clean_composite(lines: list[str], stats: dict) -> list[str]:
    hdr, body = split_header_body(lines)
    tail_span = find_entry_span(body, ("晒伤没", "shai shang mei"), ("挨没挨住", "ai mei ai zhu"), next_word="没晒伤")
    r2_suffix_span = find_entry_span(body, ("李副校", "li fu xiao"), ("之会源堂", "zhi hui yuan tang"))
    r2_template_span = find_entry_span(body, ("示之以", "shi zhi yi"), ("晒不伤", "shai bu shang"))
    out = list(hdr)
    promo_substrings = (
        "关注我的公众号", "点击下方", "点击右上角", "点个赞", "欢迎私信", "私信问我",
        "加我微信", "评论区留言", "图片来自网络", "图片来源于网络", "转载请注明出处",
        "欢迎大家关注", "欢迎关注公众号", "可以关注公众号", "请关注公众号",
        "后台回复", "本文首发", "点赞收藏", "点赞关注", "私信我",
    )
    rep4_re = re.compile(r"(.)\1{3,}")
    rep4_whitelist = {"呜呜呜呜", "呵呵呵呵", "嘻嘻嘻嘻", "嘿嘿嘿嘿", "嘿嘿嘿嘿嘿"}

    existing_pairs: set[tuple[str, str]] = set()
    shei_wt: dict[str, int] = {}
    for line in body:
        p = parse_entry(line)
        if not p:
            continue
        w0, py0, wt0, _ = p
        py0 = normalize_lue_nue(py0)
        existing_pairs.add((w0, py0))
        if "谁" in w0 and "shei" in py0.split():
            shei_wt[w0] = max(shei_wt.get(w0, 0), w_int(wt0))

    in_dui_block = False
    shei_additions: list[str] = []
    for offset, line in enumerate(body):
        stripped = line.strip()
        if stripped.startswith("##### 㨃"):
            in_dui_block = True
            continue
        if in_dui_block:
            if stripped.startswith("##### ") and not stripped.startswith("##### 㨃"):
                in_dui_block = False
            else:
                if parse_entry(line):
                    stats["deleted_noise_or_typo"] += 1
                continue
        if (
            (tail_span and tail_span[0] <= offset <= tail_span[1])
            or (r2_suffix_span and r2_suffix_span[0] <= offset <= r2_suffix_span[1])
            or (r2_template_span and r2_template_span[0] <= offset <= r2_template_span[1])
        ):
            if parse_entry(line):
                stats["deleted_template_tail"] += 1
            continue
        parsed = parse_entry(line)
        if not parsed:
            if stripped.startswith("#"):
                out.append(line)
            continue
        w, py, wt, extra = parsed
        py = normalize_lue_nue(py)
        if (
            is_leading_de_fragment(w, py)
            or is_leading_le_fragment(w, py)
            or (rep4_re.search(w) and w not in rep4_whitelist)
            or any(sub in w for sub in promo_substrings)
        ):
            stats["deleted_noise_or_typo"] += 1
            continue
        if "质的" in w and "di" in py.split():
            new_py = replace_syl_at(
                w, py, "的", "di", "de",
                cond=lambda wd, sy, i: i > 0 and wd[i - 1] == "质" and i + 1 < len(wd),
            )
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if "佛" in w and "fu" in py.split():
            new_py = replace_syl_at(
                w, py, "佛", "fu", "fo",
                cond=lambda wd, sy, i: not (i > 0 and wd[i - 1] in "仿彷"),
            )
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if "转文字" in w and "zhuai" in py.split():
            new_py = replace_syl_at(w, py, "转", "zhuai", "zhuan")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if "干咳" in w and "hai" in py.split():
            new_py = replace_syl_at(w, py, "咳", "hai", "ke")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if "哪" in w and "nei" in py.split():
            new_py = replace_syl_at(w, py, "哪", "nei", "na")
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if "马尾" in w and "yi" in py.split():
            new_py = replace_syl_at(
                w, py, "尾", "yi", "wei",
                cond=lambda wd, sy, i: i > 0 and wd[i - 1] == "马",
            )
            if new_py != py:
                py = new_py
                stats["fixed_py"] += 1
        if "谁" in w and "shui" in py.split():
            shei_py = replace_syl_at(w, py, "谁", "shui", "shei")
            if shei_py != py:
                old_w = w_int(wt)
                if (w, shei_py) not in existing_pairs and old_w >= 10:
                    shei_additions.append(format_entry(w, shei_py, wt, extra))
                    existing_pairs.add((w, shei_py))
                    shei_wt[w] = max(shei_wt.get(w, 0), old_w)
                ref = shei_wt.get(w, 0)
                if ref > 0:
                    target = min(max(ref // 6, 1), 40)
                    if old_w > target:
                        wt = str(target)
                        stats["reweighted"] += 1
        out.append(format_entry(w, py, wt, extra))

    if shei_additions:
        out.append("# 补充常用口语「谁(shei)」读音")
        out.extend(shei_additions)
        stats["added"] += len(shei_additions)
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


def clean_en_dicts(manifest: dict, ruleset: dict_rules.RuleSet, rule_hits: dict[str, int]) -> None:
    en_dir = DST_ROOT / "en_dicts"
    en_dir.mkdir(parents=True, exist_ok=True)

    # Per melt_eng.dict.yaml: en_ext is imported BEFORE en (to preserve alias ordering like PS -> Photoshop).
    # Therefore clean en_ext first, then deduplicate en against en_ext!
    ext_lines = (SRC_ROOT / "en_dicts/en_ext.dict.yaml").read_text(encoding="utf-8").splitlines()
    ext_out, ext_seen, ext_st = dict_rules.apply_en_overlay("en_dicts/en_ext.dict.yaml", ext_lines, ruleset, rule_hits)
    (en_dir / "en_ext.dict.yaml").write_text("\n".join(ext_out) + "\n", encoding="utf-8", newline="\n")
    manifest["files"]["en_dicts/en_ext.dict.yaml"] = ext_st

    en_lines = (SRC_ROOT / "en_dicts/en.dict.yaml").read_text(encoding="utf-8").splitlines()
    en_out, _, en_st = dict_rules.apply_en_overlay("en_dicts/en.dict.yaml", en_lines, ruleset, rule_hits, prior_seen=ext_seen)
    (en_dir / "en.dict.yaml").write_text("\n".join(en_out) + "\n", encoding="utf-8", newline="\n")
    manifest["files"]["en_dicts/en.dict.yaml"] = {
        "before": en_st["before"], "after": en_st["after"],
        "fixed": en_st["fixed"], "deleted": en_st["deleted"], "deduped_against_en_ext": en_st["deduped"],
    }

    build_cn_en.apply_cn_en_rules(
        SRC_ROOT,
        DST_ROOT,
        ruleset.rules_dir / "cn_en_source.tsv",
        manifest=manifest,
        rule_hits=rule_hits,
    )


def clean_opencc_texts(manifest: dict, ruleset: dict_rules.RuleSet, rule_hits: dict[str, int]) -> None:
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
        elif line == "亚硫酸钠\t亚硫酸钠 NaSO₃":
            line = "亚硫酸钠\t亚硫酸钠 Na₂SO₃"
        elif line == "蓝矾\t蓝矾 CuSO₄·₅H₂O":
            line = "蓝矾\t蓝矾 CuSO₄·5H₂O"
        elif line.startswith("V肤色\t") and line != "V肤色\tV肤色 🏻 🏼 🏽 🏾 🏿":
            line = "V肤色\tV肤色 🏻 🏼 🏽 🏾 🏿"
        elif line.startswith("V动物\t"):
            k, v = line.split("\t", 1)
            toks = v.split()
            vs16_bases = {t.replace("\ufe0f", "") for t in toks if "\ufe0f" in t}
            dedup_toks: list[str] = []
            seen_base: set[str] = set()
            for t in toks:
                base = t.replace("\ufe0f", "")
                if "\ufe0f" not in t and base in vs16_bases:
                    continue
                if base in seen_base:
                    continue
                seen_base.add(base)
                dedup_toks.append(t)
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
    out, ov_fixes = dict_rules.apply_opencc_overlay("opencc/others.txt", out, ruleset, rule_hits)
    fixes += ov_fixes
    (occ_dir / "others.txt").write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    manifest["files"]["opencc/others.txt"] = {"before": len(src_lines), "after": len(out), "fixed": fixes}

    # 2. opencc/chinese_english.txt
    ce_path = SRC_ROOT / "opencc/chinese_english.txt"
    if ce_path.exists():
        ce_lines = ce_path.read_text(encoding="utf-8").splitlines()
        ce_out = []
        ce_fixed = 0
        for line in ce_lines:
            orig = line
            line = line.rstrip(" ")
            if line == "黑人\t黑人 Ethiopian Negro negroid blackamoor black unregistered\u00a0person":
                line = "黑人\t黑人 black\u00a0person black unregistered\u00a0person"
            if line != orig:
                ce_fixed += 1
            ce_out.append(line)
        ce_out, ce_ov = dict_rules.apply_opencc_overlay("opencc/chinese_english.txt", ce_out, ruleset, rule_hits)
        ce_fixed += ce_ov
        (occ_dir / "chinese_english.txt").write_text("\n".join(ce_out) + "\n", encoding="utf-8", newline="\n")
        manifest["files"]["opencc/chinese_english.txt"] = {"before": len(ce_lines), "after": len(ce_out), "fixed": ce_fixed}

    # 3. opencc/english_chinese.txt
    ec_path = SRC_ROOT / "opencc/english_chinese.txt"
    if ec_path.exists():
        ec_lines = ec_path.read_text(encoding="utf-8").splitlines()
        ec_out = []
        ec_del = 0
        ec_norm = 0
        pos_re = re.compile(r"^[a-zA-Z]{1,6}(?:\.[a-zA-Z]{1,6})*\.")
        for line in ec_lines:
            if "\t" not in line:
                ec_out.append(line)
                continue
            k, v = line.split("\t", 1)
            if " " in k:
                ec_del += 1
                continue
            v2 = re.sub(r"(?:\s+NUM)+$", "", v)
            v2 = re.sub(r" {2,}", " ", v2).replace(" ;", ";")
            toks = v2.split(" ")
            merged = toks[:1]
            for t in toks[1:]:
                if len(merged) >= 2 and not pos_re.match(t):
                    merged[-1] += t
                else:
                    merged.append(t)
            deduped = list(dict.fromkeys(merged))
            new_line = f"{k}\t{' '.join(deduped)}"
            if new_line != line:
                ec_norm += 1
            ec_out.append(new_line)
        ec_out, ec_ov = dict_rules.apply_opencc_overlay("opencc/english_chinese.txt", ec_out, ruleset, rule_hits)
        (occ_dir / "english_chinese.txt").write_text("\n".join(ec_out) + "\n", encoding="utf-8", newline="\n")
        manifest["files"]["opencc/english_chinese.txt"] = {
            "before": len(ec_lines), "after": len(ec_out), "deleted": ec_del,
            "normalized": ec_norm, "overlay_fixed": ec_ov,
        }

    # 4. opencc/emoji.txt
    em_path = SRC_ROOT / "opencc/emoji.txt"
    if em_path.exists():
        em_lines = em_path.read_text(encoding="utf-8").splitlines()
        em_out, em_ov = dict_rules.apply_opencc_overlay("opencc/emoji.txt", em_lines, ruleset, rule_hits)
        (occ_dir / "emoji.txt").write_text("\n".join(em_out) + "\n", encoding="utf-8", newline="\n")
        manifest["files"]["opencc/emoji.txt"] = {"before": len(em_lines), "after": len(em_out), "overlay_fixed": em_ov}


# ---------------------------------------------------------------------------
# Deduplication & Orchestration
# ---------------------------------------------------------------------------


def _dedup_within_file(lines: list[str], stats: dict) -> list[str]:
    """Deduplicate identical (word, py) within a single file, preserving higher weight."""
    hdr, body = split_header_body(lines)
    best_wt: dict[tuple[str, str], int] = {}
    for l in body:
        p = parse_entry(l)
        if not p:
            continue
        k = (p[0], p[1])
        w_val = w_int(p[2])
        if k not in best_wt or w_val > best_wt[k]:
            best_wt[k] = w_val
    seen: set[tuple[str, str]] = set()
    dedup_body = []
    for l in body:
        p = parse_entry(l)
        if not p:
            dedup_body.append(l)
            continue
        k = (p[0], p[1])
        if k in seen:
            stats["dedup_within_file"] += 1
            continue
        seen.add(k)
        w, py, wt, extra = p
        if wt != "" and w_int(wt) < best_wt[k]:
            wt = str(best_wt[k])
        dedup_body.append(format_entry(w, py, wt, extra))
    return hdr + dedup_body


def main() -> None:
    global SRC_ROOT, DST_ROOT
    ap = argparse.ArgumentParser(description="Clean and deduplicate rime-chth1z dictionaries in place.")
    ap.add_argument("--src-dir", type=pathlib.Path, default=REPO_ROOT)
    ap.add_argument("--out-dir", type=pathlib.Path, default=None, help="Defaults to --src-dir (in-place)")
    ap.add_argument("--rules-dir", type=pathlib.Path, default=REPO_ROOT / "rules", help="Declarative rules/ directory")
    ap.add_argument("--manifest", type=pathlib.Path, default=None, help="Optional path to write JSON summary")
    args = ap.parse_args()

    SRC_ROOT = args.src_dir.resolve()
    DST_ROOT = (args.out_dir or args.src_dir).resolve()
    rules_dir = args.rules_dir.resolve()
    (DST_ROOT / "cn_dicts").mkdir(parents=True, exist_ok=True)
    (DST_ROOT / "cn_dicts_cell").mkdir(parents=True, exist_ok=True)

    ruleset = dict_rules.load_ruleset(rules_dir)
    if ruleset.errors:
        raise SystemExit("Declarative rules validation failed:\n  " + "\n  ".join(ruleset.errors))
    rule_hits: dict[str, int] = {rid: 0 for rid in ruleset.all_rule_ids()}

    manifest: dict = {"files": {}, "rules": {}, "summary": {}}

    # Ordered by global deduplication precedence
    cn_plan = [
        ("cn_dicts/8105.dict.yaml", clean_8105),
        ("cn_dicts/base.dict.yaml", clean_base),
        ("cn_dicts/ext.dict.yaml", clean_ext),
        ("cn_dicts/others.dict.yaml", clean_others),
        ("cn_dicts/corrections.dict.yaml", clean_corrections),
        ("cn_dicts_cell/literature.dict.yaml", clean_literature),
        ("cn_dicts_cell/idiom.dict.yaml", clean_strip_blanks),
        ("cn_dicts_cell/history.dict.yaml", clean_strip_blanks),
        ("cn_dicts_cell/geography.dict.yaml", clean_geography),
        ("cn_dicts_cell/place.dict.yaml", clean_place),
        ("cn_dicts_cell/shulihua.dict.yaml", clean_shulihua),
        ("cn_dicts_cell/medication.dict.yaml", clean_medication),
        ("cn_dicts_cell/industry_product.dict.yaml", clean_industry_product),
        ("cn_dicts_cell/sport.dict.yaml", clean_sport),
        ("cn_dicts_cell/animal.dict.yaml", clean_animal),
        ("cn_dicts_cell/chess.dict.yaml", clean_strip_blanks),
        ("cn_dicts_cell/chess2.dict.yaml", clean_chess2),
        ("cn_dicts_cell/music.dict.yaml", clean_strip_blanks),
        ("cn_dicts_cell/computer.dict.yaml", clean_strip_blanks),
        ("cn_dicts_cell/media.dict.yaml", clean_generic),
        ("cn_dicts_cell/inputmethod.dict.yaml", clean_strip_blanks),
        ("cn_dicts_cell/food.dict.yaml", clean_food),
        ("cn_dicts_cell/game.dict.yaml", clean_game),
        ("cn_dicts_cell/name.dict.yaml", clean_name),
        ("cn_dicts_cell/name2.dict.yaml", clean_name2),
        ("cn_dicts_cell/exthot.dict.yaml", clean_exthot),
        ("cn_dicts_cell/composite.dict.yaml", clean_composite),
        ("cn_dicts_cell/luna.dict.yaml", clean_strip_blanks),
    ]

    # Step 1: per-file structural cleaning + declarative rules/ overlay + post-generators + within-file dedup
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
        if rel != "cn_dicts/corrections.dict.yaml":
            out_lines = dict_rules.apply_cn_overlay(rel, out_lines, ruleset, rule_hits, st)
        if rel == "cn_dicts_cell/chess.dict.yaml":
            out_lines = post_chess_add_ju(out_lines, st, move_only=False)
        elif rel == "cn_dicts_cell/chess2.dict.yaml":
            out_lines = post_chess_add_ju(out_lines, st, move_only=True)
        elif rel in (
            "cn_dicts_cell/game.dict.yaml",
            "cn_dicts_cell/sport.dict.yaml",
            "cn_dicts_cell/name2.dict.yaml",
            "cn_dicts_cell/exthot.dict.yaml",
        ):
            out_lines = post_fix_non_shenme_shi(out_lines, st)
        cleaned_files[rel] = _dedup_within_file(out_lines, st)
        file_stats[rel] = st

    # Step 1.5: apply corrections/dual_readings declarative overlay with full knowledge of active CN keys
    active_keys: set[tuple[str, str]] = set()
    for rel, _ in cn_plan:
        if rel in ("cn_dicts/corrections.dict.yaml", "cn_dicts_cell/luna.dict.yaml"):
            continue
        _, body = split_header_body(cleaned_files[rel])
        for l in body:
            p = parse_entry(l)
            if p:
                active_keys.add((p[0], p[1]))
    corr_rel = "cn_dicts/corrections.dict.yaml"
    corr_updated = dict_rules.apply_corrections_overlay(
        cleaned_files[corr_rel], ruleset, active_keys, rule_hits, file_stats[corr_rel]
    )
    cleaned_files[corr_rel] = _dedup_within_file(corr_updated, file_stats[corr_rel])

    # Step 2: global cross-file deduplication
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

    # Step 3: ensure cn_dicts_cell/luna is disabled & modern alphanumeric combos exist in rime_frost.dict.yaml
    rf_lines = (SRC_ROOT / "rime_frost.dict.yaml").read_text(encoding="utf-8").splitlines()
    rf_existing = {l.strip() for l in rf_lines if l.strip() and not l.strip().startswith("#")}
    rf_missing = []
    for tok in ruleset.alphanum_additions:
        rule_hits[f"alphanum_additions.txt:{tok}"] += 1
        if tok not in rf_existing:
            rf_missing.append(tok)
    rf_out = []
    inserted_alphanum = False
    for l in rf_lines:
        if l.strip() == "- cn_dicts_cell/luna":
            rf_out.append("  # - cn_dicts_cell/luna  # 繁体异体与冗余词条较多，默认关闭")
        else:
            rf_out.append(l)
            if l.strip() == "M4A1" and rf_missing and not inserted_alphanum:
                rf_out.extend(rf_missing)
                inserted_alphanum = True
    (DST_ROOT / "rime_frost.dict.yaml").write_text("\n".join(rf_out) + "\n", encoding="utf-8", newline="\n")

    # Step 4: English & OpenCC
    clean_en_dicts(manifest, ruleset, rule_hits)
    clean_opencc_texts(manifest, ruleset, rule_hits)
    manifest["rules"] = dict_rules.summarize_rule_hits(ruleset, rule_hits)

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
