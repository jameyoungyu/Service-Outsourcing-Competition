# 知识产权材料

按团队要求：**软著登记材料优先，专利只准备技术交底书**。知识产权工作不阻塞主线开发，
本目录下的内容全部是可以并行推进的文档准备，不涉及代码改动。

## 目录

| 文件 | 用途 | 状态 |
|---|---|---|
| [`software-copyright/登记申请信息.md`](software-copyright/登记申请信息.md) | 软著登记申请表所需的全部字段 | 已整理，**含 `【待填】` 项需人工确认** |
| [`software-copyright/源程序.txt`](software-copyright/源程序.txt) | 前 30 页 + 后 30 页源程序，每页 50 行 | 已生成，**提交前须人工翻阅** |
| [`../manual/用户手册.md`](../manual/用户手册.md) | 软著登记所需的软件文档，同时也是竞赛交付的产品使用手册 | 已完成 |
| [`patent/技术交底书.md`](patent/技术交底书.md) | 供专利代理人判断与撰写的技术交底 | 草稿，**未做检索** |

## 重新生成源程序清单

代码改动后需要重新生成，并重新统计行数填入申请表：

```bash
cd backend
python scripts/build_copyright_listing.py
```

脚本会先扫描疑似敏感内容（密钥、口令、连接串、私钥），检出即拒绝写出，
确认为误报后可加 `--allow-suspicious` 重跑。

统计源程序量：

```bash
cd backend && python - <<'PY'
from pathlib import Path
b = {str(f): sum(1 for _ in f.open(encoding="utf-8"))
     for p in ("app/**/*.py","algorithms/**/*.py","alembic/**/*.py","scripts/*.py","tests/*.py")
     for f in Path(".").glob(p)}
fe = Path("../frontend/src")
f = {str(x): sum(1 for _ in x.open(encoding="utf-8"))
     for p in ("**/*.ts","**/*.vue") for x in fe.glob(p)}
print(f"后端 {len(b)} 文件 {sum(b.values())} 行；前端 {len(f)} 文件 {sum(f.values())} 行；"
      f"合计 {len(b)+len(f)} 文件 {sum(b.values())+sum(f.values())} 行")
PY
```

## 三条不要越过的线

1. **不要把 D-最优、CELF、矩阵行列式引理写成本项目原创的算法。** 三者均为既有技术，
   这样写会在实质审查中被直接打掉，也会损害整份申请的可信度。理由与正确写法见技术交底书第 0 节。
2. **不要在任何材料里省略不利的实测结果。** 交底书第 4 节列出了三条对本方案不利的测量，
   隐瞒它们会在审查或后续无效程序中造成更大的问题。
3. **本目录的文件不构成法律意见。** 权利归属、日期承诺、开源依赖的许可证合规，
   须由团队与代理机构自行确认。
