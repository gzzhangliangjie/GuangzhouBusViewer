# -*- coding: utf-8 -*-
"""飞翔公园/三元里 下移+文字右置(用户: 挤成一坨 往下挪挪 文字放右边):
钉沿2号线走廊下移(飞翔公园+19->779.5, 三元里+18.5->819.5), 走廊线不动;
飞翔公园胶囊归中路线x=1336.5(修不在路线中央); 文字右侧垂直居中于站钉。
三处同步: 卡片钉 / codes胶囊 / codes文字(base由sync拷贝)。"""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 2) codes胶囊(归中+随钉)
t = open('assets/lines/network-全网.codes.svg', encoding='utf-8').read()
chip_edits = [
    ('<rect x="1335.75" y="756.00" width="20.5" height="9.0" rx="4.5" fill="#FFFFFF" stroke="#1E88E5"',
     '<rect x="1326.25" y="775.00" width="20.5" height="9.0" rx="4.5" fill="#FFFFFF" stroke="#1E88E5"'),
    ('<rect x="1326.25" y="796.50" width="20.5" height="9.0" rx="4.5" fill="#FFFFFF" stroke="#1E88E5"',
     '<rect x="1326.25" y="815.00" width="20.5" height="9.0" rx="4.5" fill="#FFFFFF" stroke="#1E88E5"'),
]
applied = 0
for o, n in chip_edits:
    if o in t:
        t = t.replace(o, n)
        applied += 1
print('胶囊编辑命中:', applied, '/2 (飞翔公园旧位可能带历史偏移, 未命中则按实际再修)')

# 3) codes文字
text_edits = [
    ('<text x="1373.25" y="758.70" font-size="7.5" text-anchor="middle">飞翔公园</text>',
     '<text x="1373.25" y="782.20" font-size="7.5" text-anchor="middle">飞翔公园</text>'),
    ('<text x="1313.00" y="799.20" font-size="7.5" text-anchor="middle">三元里</text>',
     '<text x="1361.50" y="822.20" font-size="7.5" text-anchor="middle">三元里</text>'),
]
for o, n in text_edits:
    if o in t:
        t = t.replace(o, n)
        print('文字命中:', o[8:30])
    else:
        mm = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*>' + o.split('>')[1].split('<')[0] + r'</text>', t)
        print('!! 文字未命中, 现状:', mm.group(0) if mm else '?')
open('assets/lines/network-全网.codes.svg', 'w', encoding='utf-8').write(t)
