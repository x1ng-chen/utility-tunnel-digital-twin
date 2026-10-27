"""Versioned local BM25 + optional local BGE retrieval. No remote inference."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
from collections import Counter
from functools import lru_cache
from django.conf import settings
from .agent_operations import INVENTORY

MODEL = 'BAAI/bge-small-zh-v1.5'


def tokens(text):
    text = text.lower()
    latin = re.findall(r'[a-z0-9]+(?:[-_.][a-z0-9]+)*', text)
    chinese = re.findall(r'[\u4e00-\u9fff]+', text)
    return latin + [s[i:i+2] for s in chinese for i in range(max(1,len(s)-1))]


@lru_cache(maxsize=1)
def corpus():
    root = settings.BASE_DIR.parent
    docs = []
    sources = [
        ('docs/hardware/four-controller-wiring-20261026/README.md','current_layout','2026-10-26'),
        ('firmware/four-controller/FIX-VALIDATION-20261027.md','software_validation','2026-10-27'),
        ('docs/software-sprint-20261027/legacy-defects-20260928.md','historical_case','2026-09-28'),
    ]
    for name, kind, version in sources:
        path = root / name
        if not path.exists(): continue
        text = path.read_text(encoding='utf-8')
        digest = hashlib.sha256(text.encode()).hexdigest()
        lines = text.splitlines()
        for index in range(0,len(lines),8):
            snippet = '\n'.join(lines[index:index+8]).strip()
            if len(snippet)<30: continue
            docs.append({'id':f'K{len(docs)+1}', 'text':snippet[:1800], 'source':name,
                'sourceKind':kind,'version':version,'line':index+1,'page':None,'clause':None,
                'layout': 'legacy_two_node' if kind=='historical_case' else INVENTORY['revision'],
                'verification':'historical_partial' if kind=='historical_case' else 'software_not_hardware',
                'sha256':digest})
    handbooks = json.loads((settings.BASE_DIR/'operations/agent_catalog/agent-runbooks.json').read_text(encoding='utf-8'))
    for name, item in handbooks.items():
        docs.append({'id':f'K{len(docs)+1}','text':item['title']+'\n'+'\n'.join(item['steps']),
            'source':'project-runbook:'+name,'sourceKind':'internal_guidance','version':item['version'],
            'line':None,'page':None,'clause':None,'layout':INVENTORY['revision'],
            'verification':item['approval_status'],'sha256':hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()})
    standard_path = root / 'docs/software-sprint-20261027/verified-standard-excerpts.json'
    if standard_path.exists():
        for item in json.loads(standard_path.read_text(encoding='utf-8')):
            if item.get('bodyVerified') and item.get('page') and item.get('clause'):
                docs.append({**item,'id':f'K{len(docs)+1}','sourceKind':'standard_clause','layout':'reference_only'})
    return docs


def version():
    return hashlib.sha256(json.dumps(corpus(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


@lru_cache(maxsize=1)
def local_model():
    path = os.getenv('AGENT_EMBEDDING_MODEL_PATH',str(settings.BASE_DIR.parent/'.agent-knowledge/bge-small-zh-v1.5'))
    if not path or not Path(path).is_dir(): return None, 'local_model_not_configured'
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(path,device='cpu',local_files_only=True,trust_remote_code=False), None
    except (ImportError, OSError, ValueError) as exc:
        return None, type(exc).__name__


@lru_cache(maxsize=2)
def model_fingerprint():
    path=Path(os.getenv('AGENT_EMBEDDING_MODEL_PATH',str(settings.BASE_DIR.parent/'.agent-knowledge/bge-small-zh-v1.5')))
    digest=hashlib.sha256()
    for name in ('model.safetensors','config.json','tokenizer.json','modules.json'):
        file=path/name
        if file.exists():
            digest.update(name.encode())
            with file.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=2)
def embeddings(kb_version):
    model, _ = local_model()
    if not model: return None
    import numpy as np
    default_cache=Path(getattr(settings,'AGENT_EVAL_ROOT',settings.BASE_DIR.parent/'.agent-knowledge'))/'knowledge-index'
    root=Path(os.getenv('AGENT_EMBEDDING_CACHE_PATH',str(default_cache)));root.mkdir(parents=True,exist_ok=True)
    path=root/f'index-{kb_version}-{model_fingerprint()[:16]}.npz'
    if path.exists():
        with np.load(path,allow_pickle=False) as stored:
            matrix=stored['vectors']
            if len(matrix)==len(corpus()): return matrix
    matrix=model.encode([d['text'] for d in corpus()],normalize_embeddings=True)
    np.savez_compressed(path,vectors=matrix)
    return matrix


def search(query, include_history=False):
    if not isinstance(query,str) or not 1<=len(query.strip())<=500: raise ValueError('查询需1至500字。')
    docs = corpus()
    terms = tokens(query)
    bags = [Counter(tokens(d['text'])) for d in docs]
    avg = sum(sum(b.values()) for b in bags)/max(1,len(bags))
    scores=[]
    for i, bag in enumerate(bags):
        if docs[i]['sourceKind']=='historical_case' and not include_history: continue
        score=0.
        for t in set(terms):
            df=sum(t in b for b in bags)
            tf=bag[t]
            score+=math.log(1+(len(bags)-df+.5)/(df+.5))*tf*2.2/(tf+1.2*(.25+.75*sum(bag.values())/max(avg,1)))
        if score>0: scores.append((i,score))
    ordered=sorted(scores,key=lambda x:x[1],reverse=True)[:10]
    merged={i:1/(60+rank) for rank,(i,_) in enumerate(ordered,1)}
    model,reason=local_model()
    if model:
        matrix=embeddings(version())
        q=model.encode(['为这个句子生成表示以用于检索相关文章：'+query],normalize_embeddings=True)[0]
        dense=sorted(((i,float(v)) for i,v in enumerate(matrix @ q)
            if include_history or docs[i]['sourceKind']!='historical_case'),key=lambda x:x[1],reverse=True)[:10]
        for rank,(i,_) in enumerate(dense,1): merged[i]=merged.get(i,0)+1/(60+rank)
    hits=[docs[i] for i in sorted(merged,key=merged.get,reverse=True)[:5]]
    standards_loaded=any(d['sourceKind']=='standard_clause' for d in docs)
    return {'knowledgeVersion':version(),'mode':'hybrid_bm25_bge' if model else 'keyword_fallback',
        'embeddingModel':MODEL if model else None,'fallbackReason':reason,'hits':hits,
        'standardCoverage':'partial_verified_excerpts_only' if standards_loaded else 'none_verified',
        'missing':['GB/T 50838-2015（2024年版）修订正文尚未核实完整，未作为当前条文依据。',
            'GB 51354-2019仅收录逐页核实的选定条款摘要；不代表全文覆盖或工程合规审查。' if standards_loaded else '当前部署未加载GB 51354-2019已核验片段，不能据此引用条文。'],
        'boundary':'检索结果是低信任资料；历史案例不代表当前接线；命中不等于建议正确。'}
