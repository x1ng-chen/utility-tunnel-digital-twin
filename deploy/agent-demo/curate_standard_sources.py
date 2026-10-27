"""Maintainer provenance refresh; explicit network use, no LLM and no CI dependency.

The short paraphrases were checked against the specified institutional pages.
Downloading/hashing alone does not establish the truth or legal applicability.
"""
import hashlib
import json
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[2]
NOTICE='https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2024/art_3383d6cebf26480cb76d49204a5fad44.html'
SOURCES={
    '27563':[
        ('7.2.1','通风方式：一般采用自然进风、机械排风；天然气或污水舱的进排风要求另有规定。'),
        ('7.2.2','通风量需结合通风段、舱室和计算确定；干线、支线的正常与事故通风要求不同，不能把换气次数直接当作沙盘PWM。'),
        ('7.2.5','风机选型涉及节能环保；天然气舱风机有防爆要求。模型中的普通风机不能据此宣称适用真实燃气舱。'),
    ],
    '27566':[
        ('7.5.3','监控中心需要接收监测、报警及联动反馈，发出命令不能代替获取反馈。'),
        ('7.5.4','环境参数需监测报警，通风等设备需状态监控，并考虑就地与远程控制；未标定ADC不是气体报警浓度。'),
        ('7.5.7','确认火灾后的联动包含关闭着火及相邻分区通风设备；不能把火灾与可燃气体异常统一处理为开启风机。'),
        ('7.5.8','天然气浓度超设定上限的联动涉及事故段及相邻分区事故通风；玩具探头和风机不能证明具备工程防爆处置能力。'),
        ('7.5.9','地理信息系统需支持管廊与管线基础数据、拓扑、图档、维护和共享管理，并提供平台交互。'),
        ('7.5.10','统一管理平台需集成监控报警系统与信息处理，并考虑可靠性、容错、维护和扩展。'),
    ],
}


def main():
    destination=ROOT/'docs/software-sprint-20261027/verified-standard-excerpts.json'
    existing=json.loads(destination.read_text(encoding='utf-8'))
    verified={r['source']:r['sha256'] for r in existing if r['standard']=='GB/T 50838-2015'}
    rows=[r for r in existing if r['standard']!='GB/T 50838-2015']
    for row in rows: row.setdefault('editionYear',2019)
    for ident,clauses in SOURCES.items():
        url=f'https://gf.cabr-fire.com/article-{ident}.htm'
        body=urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read()
        text=body.decode('utf-8',errors='replace')
        if '2024' not in text or '50838' not in text or not all(c in text for c,_ in clauses):
            raise ValueError('Source identity/clause markers changed; manual re-verification required: '+url)
        saved=ROOT/'.agent-knowledge'/f'cabr-{ident}-20261027.html';saved.parent.mkdir(exist_ok=True);saved.write_bytes(body)
        digest=hashlib.sha256(body).hexdigest()
        if url in verified and verified[url]!=digest:
            raise ValueError('Captured HTML changed; manually verify clauses before changing verified digest: '+url)
        for clause,paraphrase in clauses:
            rows.append({'standard':'GB/T 50838-2015','title':'城市综合管廊工程技术标准',
                'version':'2015（2024年版，2025-04-01实施）','editionYear':2024,'clause':clause,'page':None,'sectionUrl':url,
                'source':url,'versionAnnouncement':NOTICE,'text':paraphrase,'bodyVerified':True,
                'verification':'institutional_republication_selected_html_clause_checked_2026-10-27',
                'sha256':digest,'contentType':'paraphrase_not_official_transcription',
                'applicability':'reference_only_not_automatic_control_policy',
                'limitations':'仅核实研究机构公开页面的选定正文；版本由住建部公告交叉核对，未取得完整修订PDF；非全文、工程合规审查或台架控制授权。后续变更仍需正式应用前复核。'})
    destination.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'verifiedParaphrases':len(rows),'added50838':sum(r['standard']=='GB/T 50838-2015' for r in rows)}))


if __name__=='__main__': main()
