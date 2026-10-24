# -*- coding: utf-8 -*-
# 底图回写同步(两模式一套, 同26d9a3b做法脚本化):
#   1) base 站名标注组 := codes终版 labels_inner (徽标/牌布局定稿文字一致)
#   2) base 徽标 transform := codes终版 41枚 translate(scale保留base值)
#   3) _network-audit.json badges/viewBox 随底图更新(verify-badges-pixel数据源)
import io, os, re, sys, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES_DIR = os.path.join(ROOT, 'assets', 'lines')
BASE = os.path.join(LINES_DIR, 'network-全网.svg')
CODES = os.path.join(LINES_DIR, 'network-全网.codes.svg')
AUDIT = os.path.join(ROOT, 'data', '_network-audit.json')
FIN = os.path.join(ROOT, 'data', 'codes-final-pins.json')

base = open(BASE, encoding='utf-8').read()
codes = open(CODES, encoding='utf-8').read()
fin = json.load(open(FIN, encoding='utf-8'))

# 1) 站名组回写
m_c = re.search(r'<g id="站名标注"[^>]*>(.*?)</g>', codes, re.S)
assert m_c and m_c.group(1) == fin.get('labels_inner'), 'codes站名组与锚表不一致'
m_b = re.search(r'(<g id="站名标注"[^>]*>).*?(</g>)', base, re.S)
base = base[:m_b.start(1) + len(m_b.group(1))] + fin['labels_inner'] + base[m_b.start(2):]

# 2) 徽标transform回写(按文档序, base/codes徽标同序; 锚串=translate(x y), scale保留)
trs = fin['badges']
assert len(trs) == len(re.findall(r'<g data-badge="header"', codes)), '锚表数与codes徽标数不一致'
_it = [0]
def _rw(mm):
    i = _it[0]; _it[0] += 1
    return mm.group(1) + '"' + trs[i] + mm.group(2) + '"'
base = re.sub(r'(<g data-badge="header" transform=)"translate\([-\d.]+ [-\d.]+\)([^>]*)"', _rw, base)
assert _it[0] == len(trs), '回写数不符: %d' % _it[0]

open(BASE, 'w', encoding='utf-8').write(base)

# 3) audit同步: badges=(线名, x, y)+viewBox
# 徽标文字=卡上线路名: 数字('1'..'22')/APM/广佛线(注意: 广佛线不以"号线"结尾!)
_LNAMES = {'1号线', '2号线', '3号线', '4号线', '5号线', '6号线', '7号线', '8号线',
           '9号线', '10号线', '11号线', '12号线', '13号线', '14号线', '18号线',
           '21号线', '22号线', '广佛线', 'APM线'}
KEY2LN = {'GF': '广佛线', 'APM': 'APM线'}
bad_list = []
for mm in re.finditer(r'<g data-badge="header" transform="translate\([-\d.]+ [-\d.]+\)[^>]*>(.*?)</g>', base, re.S):
    tr = re.search(r'translate\(([-\d.]+) ([-\d.]+)\)', mm.group(0))
    inner = mm.group(1)
    ts = re.findall(r'>([^<>]+)</text>', inner)
    key = ts[0].strip() if ts else '?'
    nm = key if key in _LNAMES else (KEY2LN.get(key) or (key + '号线' if key.isdigit() else '?'))
    bad_list.append([nm, round(float(tr.group(1)), 1), round(float(tr.group(2)), 1)])
vb = [float(v) for v in re.search(r'viewBox="([-\d. ]+)"', base).group(1).split()]
aud = json.load(open(AUDIT, encoding='utf-8'))
aud['badges'] = bad_list
aud['viewBox'] = [round(v, 2) for v in vb]
json.dump(aud, open(AUDIT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('底图回写完成: 徽标%d枚 站名组=%d字 viewBox=%s' % (len(bad_list), len(fin['labels_inner']), vb))
