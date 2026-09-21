# data/raw — 主语料来源与许可说明

本目录为 **Kanripo（漢籍リポジトリ）** 公版古籍数字化语料的逐书子目录
（`KR1a0001`…），每部书一个文件夹，内含 `KRxxxxx_NNN.txt` 正文单元。

## 来源

- 上游仓库：`https://github.com/kanripo/KR<id>`（manifest 逐书记
  `source_url` 为 codeload zip 链接 + `zip_sha256` 供对验）
- 清单：`data/catalog/corpus_manifest.json`（每书单元数/哈希/来源）

## 许可口径（R230n·R26-P2 登记）

Kanripo 所收为公版古籍文本（经文/注疏均数百年前的公版内容）。
上游仓库本身未随附独立 LICENSE 文件（`licence_status: none-stated`），
按「公版内容 + 参考用途」口径使用：本项目仅作**本地检索与研究引用**，
不做二次分发。若日后要把语料打进对外发行物（exe/镜像），先复核
对应 Kanripo 仓库的最新条款。

## 结构

```
data/raw/KR<id>/KR<id>_<NNN>.txt   # 第 NNN 节正文（构建索引的输入）
```
索引产物 `data/index/corpus.db` 由 `scripts/build_index.py` 从这些
txt 重建（5 秒级，可随时重跑），不入库。
