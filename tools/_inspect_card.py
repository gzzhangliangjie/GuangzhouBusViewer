# -*- coding: utf-8 -*-
import sys,io,json,re
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
import xml.etree.ElementTree as ET
NS='http://www.w3.org/2000/svg'
fn=sys.argv[1]
t=ET.parse(fn).getroot()
for c in t.iter('{%s}circle'%NS):
    if c.get('data-nm'):
        print('%-8s (%s,%s)'%(c.get('data-nm'),c.get('cx'),c.get('cy')))
