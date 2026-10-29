"""Offline demonstrator restore check; preserves both the requested and displaced states."""
import hashlib
import argparse
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import zipfile
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('demo_manager',HERE/'manage_demo.py')
manager=importlib.util.module_from_spec(spec);spec.loader.exec_module(manager)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--profile',choices=['capabilities','demo'],default='capabilities')
manager.configure(parser.parse_args().profile)
manager.offline()
db=manager.STATE/'db.sqlite3'
with closing(sqlite3.connect(db)) as connection: original=connection.execute('SELECT phase FROM operations_demosession WHERE id=1').fetchone()[0]
source=manager.backup();source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
changed=(original+1)%4
with closing(sqlite3.connect(db)) as connection:
    connection.execute('UPDATE operations_demosession SET phase=? WHERE id=1',(changed,)); connection.commit()
before=set((manager.STATE/'backups').glob('*.zip'))
manager.restore(source)
after=set((manager.STATE/'backups').glob('*.zip'))
assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
assert len(after-before)==1
with closing(sqlite3.connect(db)) as connection: assert connection.execute('SELECT phase FROM operations_demosession WHERE id=1').fetchone()[0]==original
displaced=(after-before).pop()
with zipfile.ZipFile(displaced) as archive:
    memory=sqlite3.connect(':memory:');memory.deserialize(archive.read('db.sqlite3'))
    assert memory.execute('SELECT phase FROM operations_demosession WHERE id=1').fetchone()[0]==changed
    memory.close()
result={'status':'passed','source':'SIMULATED_TEST','originalArchiveUnchanged':True,
    'restoredRequestedState':True,'displacedStatePreservedSeparately':True,'sameSecondUniqueArchives':True,
    'businessAndEvaluationDatabasesSelected':False}
(manager.STATE/'backup-restore.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('Backup and restore passed; both distinct states retained.')
