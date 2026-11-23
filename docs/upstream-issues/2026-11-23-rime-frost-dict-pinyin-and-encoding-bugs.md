# [Bug] 多份中文词库存在缺空格/非法音节、批量自动注音错误及 `lue/nue` 编码不统一

## 环境与版本
- **上游版本**：`gaboolic/rime-frost@ab64ecf`（`cn_dicts_cell/` 为白霜独有词库，`base.dict.yaml` 词条亦属白霜维护）
- **客户端与引擎**：Weasel `0.17.4` / `librime 1.17.0`
- **影响范围**：全拼与 6 套双拼方案（其中 `均订 junding` 缺空格导致 6 套双拼均无法打出该词）

## 实际影响
- **属于哪类问题**：词典编码损坏导致词条不可达 / 常用词注音错误导致首选被同音词顶替或错码污染 / 同词双拼写去重失效
- **实际影响说明**：
  1. `cn_dicts/base.dict.yaml:375851` 的 `均订\tjunding\t50` 缺失音节空格：全拼虽可作为单个未切分编码打出，但在**全部双拼方案中完全不可达**；`cn_dicts_cell/place.dict.yaml` 另含 **26 处**带数字或大写字母的不可输入音节（如 `T3 hang zhan lou`、`hong qiao 2 hao hang zhan lou`）。
  2. 自动化注音脚本引入多处成片客观错音：实测在默认全拼下输入 `mianfubingyi` 首选被错词 `面服兵役` 顶替、输入 `henanluohe` 首选被错词 `河南络合` 顶替（正确整词条被错注在 `wen fu bing yi` / `he nan ta he` 上）；`善于思考`、`马尾神经`、`存在哪些问题`、`残酷角斗士` 等整词词条也因错注而无法在标准读音下直接命中整词（只能回退到 `∞` 组句），反而在错码 `shanyusaikao`、`mayishenjing`、`cankujiaodoushi` 下作为直出首选弹出。
  3. 12 份活跃词库中另有 **569 条**词条混用 `lue`/`nue`（与 `8105.dict.yaml` 及主词库约定的 `lve`/`nve` 不一致）。虽然 7 套方案的拼写代数均兼容 `ue`/`ve`、不影响正常打字，但在 `ab64ecf` 中直接造成 **75 对跨文件完全重复词条无法去重**（如 `战略思维`、`任务攻略`、`暴虐`、`劫掠者`、`掠夺者` 同时存在 `lve` 与 `lue` 两条记录），并破坏基于 `8105` 音节表的静态校验。

## 复现步骤
1. 使用干净的 `gaboolic/rime-frost@ab64ecf` 默认配置（未叠加个人 `*.custom.yaml`）部署。
2. **双拼不可达（`均订`）**：在自然码双拼（`rime_frost_double_pinyin`）下输入 `jpdy`（或 `gkjpdy`）：
   - **实际结果**：候选依次为 `君鼎 | 均 | 君 | 军 | 郡 | 菌`（`gkjpdy` 为 `高军定 | 高军顶 | 高军丁`），**无「均订」**。
   - **预期结果**：`均订` 按正常双音节 `jun ding` 编码，自然码输入 `jpdy` 直接出「均订」。
3. **自动注音错误导致首选错位与错码直出**（默认全拼 `rime_frost` 实测）：
   - 输入 `mianfubingyi` → **第 1 候选**为错词 `面服兵役`（`∞`），`免服兵役` 掉到第 2；而输入错音 `wenfubingyi` 第 1 候选直出 `免服兵役`。
   - 输入 `henanluohe` → **第 1 候选**为错词 `河南络合`（`∞`），`河南漯河` 掉到第 2；而输入错音 `henantahe` 第 1、2 候选直出 `河南漯河`、`河南漯河市`。
   - 输入 `shanyusaikao` / `mayishenjing` / `cankujiaodoushi` → 分别直出 `善于思考`、`马尾神经`、`残酷角斗士`（标准读音 `shanyusikao` / `maweishenjing` / `cankujuedoushi` 均无整词词条，只能回退 `∞` 组句）。

## 原因位置
- **非法 / 缺空格音节（38 处）**：
  - `cn_dicts/base.dict.yaml:375851`：`均订\tjunding\t50`（缺空格）
  - `cn_dicts_cell/place.dict.yaml:311,312,385` 等 26 处：`T3 hang zhan lou`、`hong qiao 2 hao hang zhan lou` 等含数字/大写字母音节
  - `cn_dicts_cell/food.dict.yaml:137525-137527`（10 处）与 `cn_dicts_cell/literature.dict.yaml:30849`（1 处）：`zhei`（非 `8105` 标准音节）
- **批量自动注音错误**：
  - `cn_dicts_cell/composite.dict.yaml:25729` `善于思考`（`shan yu sai kao`，误套《左传》「于思」规则；同组含 `关于思念`、`懒于思考`、`ext` `于思洋`）
  - `cn_dicts_cell/composite.dict.yaml:113764` `免服兵役`（`wen fu bing yi`，误套古丧服「免服」规则；同组含 `免服务费`）
  - `cn_dicts_cell/composite.dict.yaml:368262` `河南漯河`（`he nan ta he`，误用古山东漯水音；同组 5 条河南漯河词条）
  - `cn_dicts_cell/composite.dict.yaml:562770` `马尾神经`（`ma yi shen jing`；同文件共 29 条「马尾」词条误注 `ma yi`）
  - `cn_dicts_cell/composite.dict.yaml:25661,26520` 等 52 条含「哪」短语（如 `哪个品牌好`、`存在哪些问题`）仅有 `nei` 而无 `na`
  - `cn_dicts_cell/game.dict.yaml:23220,35452` 等 475 条「角斗士」词条误注 `jiao dou shi`（规范 `jue dou shi`；其中 `L57506` 等 3 条「角斗士的长刺」兼误注 `zhang ci`）
  - `cn_dicts_cell/shulihua.dict.yaml:11088` 等 20 条台湾繁体「醯」化工词条（如 `丙烯醯胺 bing xi xi an`，而 `base:19923` 已有简体 `丙烯酰胺 bing xi xian an`）及 26 条简体「酰」误注 `xi`（应为 `xian`）
- **569 条 `lue/nue` 编码不统一**（12 份活跃词库：`game` 290、`idiom` 93、`medication` 75、`shulihua` 40、`literature` 30、`sport` 17、`history` 12、`chess2` 6、`name2` 3、`others` 1、`geography` 1、`exthot` 1），导致 75 对同词在词库中重复存在（如 `chess2:3194 战略思维`、`game:1580 任务攻略`、`game:21345 暴虐`、`game:35789 劫掠者`、`game:41456 掠夺者`）。

## 修改建议
- 词库入库 CI 增加校验：统一将 `\b([ln])ue\b` 规范为 `$1ve` 并重跑去重；禁止未在 `8105.dict.yaml` 中出现的音节；校验音节数等于汉字数（忽略间隔号 `·`）。
- 修正上述确定性编码与自动注音错误（`junding -> jun ding`、清理 `place` 含数字/大写字母不可输入条目、修正 `于思`/`免服`/河南`漯河`/`马尾`/`composite` 缺失 `na` 的 `nei` 词条/`角斗士`/`shulihua` `醯/酰 xi -> xian`）。
- 同步在 `cn_dicts/8105.dict.yaml` 补齐《现代汉语词典》第 7 版常用缺失单字音（如 `珩 hang`、`鲗 ze`、`适 kuo`、`宕 tan`、`括 gua`、`溱 zhen`、`芥 gai` 等 37 项），便于后续自动化校对。
