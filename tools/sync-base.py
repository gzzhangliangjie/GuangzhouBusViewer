# -*- coding: utf-8 -*-
# 底图回写同步(两模式一套):
#   1) base 站名标注组 := codes SVG 站名组(自锚定, 文字唯一真源=codes SVG)
#   2) base 徽标 transform := codes SVG 徽标 transform(文档序, gen.badge_elements解析)
#   3) _network-audit.json badges/viewBox 随底图更新(verify-badges-pixel数据源)
import io, os, re, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES_DIR = os.path.join(ROOT, 'assets', 'lines')
BASE = os.path.join(LINES_DIR, 'network-全网.svg')
CODES = os.path.join(LINES_DIR, 'network-全网.codes.svg')
AUDIT = os.path.join(ROOT, 'data', '_network-audit.json')

# 底层统一逻辑(徽标解析/线名归一)从 gen-codes-cards 导入
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('gen', os.path.join(ROOT, 'tools', 'gen-codes-cards.py'))
gen = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(gen)

base = open(BASE, encoding='utf-8').read()
codes = open(CODES, encoding='utf-8').read()

# 1) 站名组回写(文字唯一真源=codes SVG)
m_c = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', codes, re.S)
assert m_c, 'codes缺站名标注组'
labels_src = m_c.group(1)
m_b = re.search(r'(<g id="站名标注"[^>]*>).*?(</g>)', base, re.S)
# 1.5) 定制钉位标签回写规则(通用机制, 无站名特判): build-network定制策略给底图标签打
#      data-pin-base="1"(东带贴线2026-10-28), 该位=引擎定制位; codes站名组自锚定=上一版codes
#      (含编号牌避让偏移, 且gen_network锚替换使戳不经过codes)——凡底图带此戳的元素保留底图
#      自身坐标, 其余照常吃codes。定制方只管打戳, 本层只认戳。
_base_lbl = gen.text_elements(m_b.group(0))
_pin_nm = {t['nm'] for t in _base_lbl if 'data-pin-base' in t['attrs']}
_base_map = {t['nm']: t['el'] for t in _base_lbl}
_kept = []
for _t in gen.text_elements(m_c.group(0)):
    if _t['nm'] in _pin_nm and _t['nm'] in _base_map:
        _kept.append(_base_map[_t['nm']])
    else:
        _kept.append(_t['el'])
labels_src = ''.join(_kept)
base = base[:m_b.start(1) + len(m_b.group(1))] + labels_src + base[m_b.start(2):]

# 2) 徽标transform回写(自锚定: transform源=codes SVG, 文档序一一对应)
#    整值替换: 旧实现只吃掉base侧translate、把codes的translate+scale拼在链头、旧scale链
#    尾巴保留——每轮sync叠一层, 入库版曾达16连scale(乘积≈6e-9, 底图徽标整体渲染不可见,
#    像素门禁vacuous pass)。codes tr_attr就是完整transform值, 必须整体替换。
seq = [e['tr_attr'] for e in gen.badge_elements(codes)]
_it = [0]
def _rw(mm):
    i = _it[0]; _it[0] += 1
    if i < len(seq):
        return mm.group(1) + '"' + seq[i] + '"' + mm.group(2)
    return mm.group(0)
base = re.sub(r'(<g data-badge="header"[^>]*? transform=)"[^"]*"(>)', _rw, base)
assert _it[0] == len(seq), '徽标回写数不符: %d/%d' % (_it[0], len(seq))

open(BASE, 'w', encoding='utf-8').write(base)

# 3) audit同步: badges=(线名, x, y)+viewBox (线名统一走 gen.badge_elements.key)
bad_list = [[e['key'], round(e['x'], 1), round(e['y'], 1)]
            for e in gen.badge_elements(base)]
vb = [float(v) for v in re.search(r'viewBox="([-\d. ]+)"', base).group(1).split()]
aud = json.load(open(AUDIT, encoding='utf-8'))
aud['badges'] = bad_list
aud['viewBox'] = [round(v, 2) for v in vb]
json.dump(aud, open(AUDIT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('底图回写完成: 徽标%d枚 站名组=%d字 viewBox=%s' % (len(bad_list), len(labels_src), vb))
