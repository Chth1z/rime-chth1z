# [Bug] 多份中文词库存在 `lue/nue` 不可达拼写、非法音节及批量自动注音错误

## 环境与版本
- **上游版本**：`gaboolic/rime-frost@ab64ecf`（`cn_dicts_cell/` 为白霜独有词库，`base.dict.yaml` 词条亦属白霜维护）
- **客户端与引擎**：Weasel `0.17.4` / `librime 1.17.0`
- **影响范围**：全拼与 6 套双拼方案（其中 `lue/nue` 与缺空格音节在双拼下完全不可达）

## 实际影响
- **属于哪类问题**：词典编码损坏导致词条不可达 / 高频常用词注音错误
- **实际影响说明**：
  1. 12 份活跃词库中共有 **569 条**词条使用 `lue`/`nue`，而 `cn_dicts/8105.dict.yaml` 及白霜拼写代数统一使用 `lve`/`nve`，导致双拼用户无法命中这些词条。
  2. `cn_dicts/base.dict.yaml:375851` 的 `均订\tjunding` 缺失音节空格，双拼与全拼正常切分均无法命中；`cn_dicts_cell/place.dict.yaml` 含 **26 条**带数字或大写字母的不可输入音节（如 `T3 hang zhan lou`、`hong qiao 2 hao hang zhan lou`）。
  3. 自动化注音脚本导致多处成片客观错误，直接影响高频词输入（如「善于思考」「免服兵役」「河南漯河」「马尾神经」「角斗士」「哪些/哪个」）。

## 复现步骤
1. 使用上游 `gaboolic/rime-frost@ab64ecf` 默认配置（自然码双拼或全拼）。
2. 输入以下高频词的标准拼音：
   - 「均订」(`jpdy` / `junding`)：词库中 `junding` 缺空格，无法作为正常双音节词匹配。
   - 「善于思考」(`shanyusikao`)、`免服兵役`(`mianfubingyi`)、`河南漯河`(`henanluohe`)、`马尾神经`(`maweishenjing`)、`存在哪些问题`(`cun zai na xie wen ti`)：词库对应条目标注为 `sai kao`、`wen fu`、`ta he`、`ma yi`、`nei xie`（且全库无正确 `na` 对应项），标准读音无法直出。
   - 「残酷角斗士」等 475 条「角斗士」词条（`game.dict.yaml`）：全部误注 `jiao dou shi`，按现行规范 `jue dou shi` 无法命中。

## 原因位置
- **569 条 `lue/nue` 拼写**（12 份活跃词库：`game` 290、`idiom` 93、`medication` 75、`shulihua` 40、`literature` 30、`sport` 17、`history` 12、`chess2` 6、`name2` 3、`others` 1、`geography` 1、`exthot` 1）。
- **非法音节（38 处）**：
  - `cn_dicts/base.dict.yaml:375851`：`均订\tjunding\t1`（缺空格）
  - `cn_dicts_cell/place.dict.yaml:311,312,385` 等 26 处：`T3 hang zhan lou`、`hong qiao 2 hao hang zhan lou` 等含数字/大写字母音节
  - `cn_dicts_cell/food.dict.yaml:137525-137527`（10 处）与 `cn_dicts_cell/literature.dict.yaml:30849`（1 处）：`zhei`（非 `8105` 标准音节）
- **批量自动注音错误**：
  - `cn_dicts_cell/composite.dict.yaml:25729` `善于思考`（`shan yu sai kao`，误套《左传》「于思」规则；同组含 `关于思念`、`懒于思考`、`ext` `于思洋`）
  - `cn_dicts_cell/composite.dict.yaml:113764` `免服兵役`（`wen fu bing yi`，误套古丧服「免服」规则；同组含 `免服务费`）
  - `cn_dicts_cell/composite.dict.yaml:368262` `河南漯河`（`he nan ta he`，误用古山东漯水音；同组 5 条河南漯河词条）
  - `cn_dicts_cell/composite.dict.yaml:562770` `马尾神经`（`ma yi shen jing`；同文件共 29 条「马尾」词条误注 `ma yi`）
  - `cn_dicts_cell/composite.dict.yaml` 52 条含「哪」短语（如 `存在哪些问题`、`哪个品牌好`）仅有 `nei` 而无 `na`
  - `cn_dicts_cell/game.dict.yaml:23220` 等 475 条「角斗士」词条误注 `jiao dou shi`（规范 `jue dou shi`；其中 3 条「角斗士的长刺」兼误注 `zhang ci`）
  - `cn_dicts_cell/shulihua.dict.yaml:11088` 等 20 条台湾繁体化工词条（如 `丙烯醯胺 bing xi xi an`）繁简未统一且「酰」误注 `xi`（应为 `xian`）

## 修改建议
- 词库入库 CI 增加正则校验：禁止 `\b[ln]ue\b`、禁止未在 `8105.dict.yaml` 中出现的音节、校验音节数等于汉字数（忽略间隔号 `·`）。
- 批量修正上述确定性自动注音错误（`junding -> jun ding`、`于思` 现代词 `sai -> si`、`免服` 现代词 `wen -> mian`、河南 `漯河 ta -> luo`、`马尾 yi -> wei`、`composite` 缺失 `na` 词条 `nei -> na`、`角斗士 jiao -> jue`、`shulihua` 化工词 `醯/酰 xi -> xian`）。
- 同步在 `cn_dicts/8105.dict.yaml` 补齐《现代汉语词典》第 7 版常用缺失单字音（如 `珩 hang`、`鲗 ze`、`适 kuo`、`宕 tan`、`括 gua`、`溱 zhen`、`芥 gai` 等 37 项），减少后续校对误报。
