"""Offline launcher tests; no server, paid model or real process stop."""
import importlib.util
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SPEC = importlib.util.spec_from_file_location('demo_manager_under_test', Path(__file__).with_name('manage_demo.py'))
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


class SoftwareLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.saved = {key: getattr(manager, key) for key in ('ROOT','BACKEND','PROFILE','STATE','PYTHON','EXTERNAL_PYTHON')}
        manager.ROOT = self.root
        manager.BACKEND = self.root / 'backend'
        manager.configure('capabilities')
        manager.STATE.mkdir()

    def tearDown(self):
        for key, value in self.saved.items(): setattr(manager, key, value)
        self.temp.cleanup()

    def database(self, marker='before'):
        with closing(sqlite3.connect(manager.STATE / 'db.sqlite3')) as db:
            db.execute('CREATE TABLE IF NOT EXISTS operations_agentrun (status TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS marker (value TEXT)')
            db.execute('DELETE FROM marker');db.execute('INSERT INTO marker VALUES (?)',(marker,))
            db.commit()

    def archive(self, names=None, profile='capabilities', manifest=True):
        self.database()
        path = self.root / 'input.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.write(manager.STATE/'db.sqlite3','db.sqlite3')
            if manifest:
                z.writestr('backup-manifest.json',json.dumps({'profile':profile,'settings':manager.PROFILES[profile][1]}))
            for name in names or []:
                info=zipfile.ZipInfo('placeholder');info.filename=name;z.writestr(info,'untrusted')
        return path

    def test_profile_selection_cannot_select_hardware_or_external_state(self):
        manager.configure('demo'); self.assertEqual(manager.STATE,self.root/'.agent-demo')
        self.assertEqual(manager.PROFILES[manager.PROFILE][1],'config.agent_demo_settings')
        manager.configure('capabilities'); self.assertEqual(manager.STATE,self.root/'.agent-capabilities')
        with self.assertRaises(ValueError):manager.configure('hardware-live')
        manager.STATE=self.root/'.hardware-live'
        with self.assertRaises(SystemExit):manager.guard_state()

    def test_docker_static_package_copies_exact_v24_and_excludes_private_runtime(self):
        source_root=Path(__file__).resolve().parents[2]
        docker=(source_root/'deploy/agent-demo/Dockerfile.api').read_text(encoding='utf-8')
        self.assertIn('COPY frontend/public/models/utility-tunnel-v24.glb /app/frontend/public/models/utility-tunnel-v24.glb',docker)
        ignore=(source_root/'.dockerignore').read_text(encoding='utf-8').splitlines()
        for name in ('.agent-capabilities','.hardware-live'):
            self.assertIn(name,ignore)

    def test_environment_clears_inherited_paid_key_and_router_by_default(self):
        (manager.STATE/'.env').write_text('DEEPSEEK_API_KEY=private-test-value\nANYJEV_TOKEN=private-router-value\nDJANGO_SETTINGS_MODULE=config.hardware_live_settings\nDATABASE_URL=sqlite:///business\n')
        with patch.dict(manager.os.environ,{'DEEPSEEK_API_KEY':'inherited-test-value','ANYJEV_ENABLED':'true','ANYJEV_TOKEN':'inherited-router'}):
            env=manager.environment()
        self.assertEqual(env['DEEPSEEK_API_KEY'],'')
        self.assertEqual(env['ANYJEV_ENABLED'],'false');self.assertEqual(env['ANYJEV_TOKEN'],'')
        self.assertEqual(env['DJANGO_SETTINGS_MODULE'],'config.agent_capability_settings')
        self.assertNotEqual(env.get('DATABASE_URL'),'sqlite:///business')

    def test_explicit_paid_keyfile_reads_only_model_key(self):
        source=self.root/'private.env';source.write_text('DEEPSEEK_API_KEY=test-authorized\nDEEPSEEK_MODEL=test-model-id\nDJANGO_INGEST_API_KEY=never-import\n')
        env=manager.environment(allow_paid_model=True,key_env_file=source)
        self.assertEqual(env['DEEPSEEK_API_KEY'],'test-authorized')
        self.assertEqual(env['DEEPSEEK_MODEL'],'test-model-id')
        self.assertNotEqual(env.get('DJANGO_INGEST_API_KEY'),'never-import')
        env=manager.environment(allow_paid_model=True,no_paid_model=True,key_env_file=source)
        self.assertEqual(env['DEEPSEEK_API_KEY'],'')

    def test_router_is_independent_explicit_switch(self):
        (manager.STATE/'.env').write_text('ANYJEV_TOKEN=test-local-router-token\nANYJEV_URL=http://127.0.0.1:8110\n')
        env=manager.environment(enable_router=True)
        self.assertEqual(env['ANYJEV_ENABLED'],'true');self.assertEqual(env['ANYJEV_TOKEN'],'test-local-router-token')
        self.assertEqual(env['DEEPSEEK_API_KEY'],'')

    def test_external_setup_never_installs_into_existing_python(self):
        manager.configure('capabilities',python=self.root/'existing-python')
        template=self.root/'deploy/agent-demo';template.mkdir(parents=True);(template/'.env.example').write_text('DEEPSEEK_API_KEY=\n')
        with patch.object(manager,'checked') as run:
            manager.setup()
        self.assertEqual(run.call_count,1)
        self.assertNotIn('pip',run.call_args.args[0])
        with self.assertRaises(SystemExit): manager.setup(rag=True)

    def test_identity_requires_birth_time_command_hash_and_owned_root(self):
        identity={'startMarker':'123','commandHash':'abc','owned':True}
        record={'pid':42,'identity':identity}
        self.assertTrue(manager.identity_matches(record,dict(identity)))
        for field,value in [('startMarker','124'),('commandHash','other'),('owned',False)]:
            with self.subTest(field=field):
                self.assertFalse(manager.identity_matches(record,{**identity,field:value}))
        self.assertFalse(manager.identity_matches({'pid':42},identity))

    def test_stop_keeps_foreign_pid_registry_and_never_calls_kill(self):
        manager.write_registry([{'name':'api','pid':42,'identity':{'startMarker':'123','commandHash':'abc','owned':True}}])
        with patch.object(manager,'process_identity',return_value={'startMarker':'999','commandHash':'abc','owned':True}),patch.object(manager,'checked') as kill:
            with self.assertRaises(SystemExit):manager.stop()
            kill.assert_not_called()
        self.assertTrue((manager.STATE/'processes.json').exists())

    def test_stop_refuses_legacy_and_other_profile_registry(self):
        for registry in ([{'pid':42}],{'schemaVersion':2,'profile':'demo','processes':[]}):
            (manager.STATE/'processes.json').write_text(json.dumps(registry))
            with patch.object(manager,'terminate_record') as terminate:
                with self.assertRaises(SystemExit):manager.stop()
                terminate.assert_not_called()

    def test_dead_process_record_is_removed_without_killing_anything(self):
        manager.write_registry([{'name':'api','pid':42,'identity':{'startMarker':'123','commandHash':'abc','owned':True}}])
        with patch.object(manager,'process_identity',return_value=None),patch.object(manager,'checked') as kill:
            manager.stop();kill.assert_not_called()
        self.assertFalse((manager.STATE/'processes.json').exists())

    def test_failed_start_terminates_only_its_own_child_and_removes_registry(self):
        executable=self.root/'python.exe';executable.write_text('existing');manager.PYTHON=executable
        vite=self.root/'frontend/node_modules/vite/bin/vite.js';vite.parent.mkdir(parents=True);vite.write_text('')
        child=unittest.mock.Mock();child.pid=42;child.poll.return_value=None
        connection=unittest.mock.MagicMock();connection.__enter__.return_value.connect_ex.return_value=1
        with patch.object(manager.socket,'socket',return_value=connection),patch.object(manager,'checked'),patch.object(manager.shutil,'which',return_value='node'),\
             patch.object(manager.subprocess,'Popen',return_value=child),\
             patch.object(manager,'process_identity',return_value=None):
            with self.assertRaises(SystemExit): manager.start()
        child.terminate.assert_called_once();child.wait.assert_called_once()
        self.assertFalse((manager.STATE/'processes.json').exists())

    def test_backup_and_restore_preserve_displaced_state_and_exclude_secrets(self):
        self.database();(manager.STATE/'users.json').write_text('{"operator":"private-password"}')
        (manager.STATE/'.env').write_text('DEEPSEEK_API_KEY=never-export')
        (manager.STATE/'secret.key').write_text('never-export')
        source=manager.backup()
        with zipfile.ZipFile(source) as z:
            self.assertNotIn('.env',z.namelist());self.assertNotIn('secret.key',z.namelist())
            self.assertEqual(json.loads(z.read('backup-manifest.json'))['profile'],'capabilities')
        self.database('changed');before=set((manager.STATE/'backups').glob('*.zip'))
        manager.restore(source)
        after=set((manager.STATE/'backups').glob('*.zip'));self.assertEqual(len(after-before),1)
        with closing(sqlite3.connect(manager.STATE/'db.sqlite3')) as db:self.assertEqual(db.execute('SELECT value FROM marker').fetchone()[0],'before')
        self.assertEqual((manager.STATE/'.env').read_text(),'DEEPSEEK_API_KEY=never-export')

    def test_backup_snapshots_committed_wal_content(self):
        self.database()
        db=sqlite3.connect(manager.STATE/'db.sqlite3')
        try:
            db.execute('PRAGMA journal_mode=WAL');db.execute("UPDATE marker SET value='wal-value'");db.commit()
            backup=manager.backup()
            with zipfile.ZipFile(backup) as z,closing(sqlite3.connect(':memory:')) as memory:
                memory.deserialize(z.read('db.sqlite3'));self.assertEqual(memory.execute('SELECT value FROM marker').fetchone()[0],'wal-value')
        finally:db.close()

    def test_restore_rejects_traversal_scripts_and_profile_changes(self):
        for member in ('../business.sqlite3','media/../../outside','media\\outside','C:/outside','secret.key','backend/settings.py'):
            with self.subTest(member=member),zipfile.ZipFile(self.archive([member])) as z:
                with self.assertRaises(SystemExit):manager.validate_archive(z)
        with zipfile.ZipFile(self.archive(profile='demo')) as z:
            with self.assertRaises(SystemExit):manager.validate_archive(z)
        with zipfile.ZipFile(self.archive(manifest=False)) as z:
            with self.assertRaises(SystemExit):manager.validate_archive(z)

    def test_restore_rejects_duplicate_members_and_symlinks(self):
        p=self.archive()
        with zipfile.ZipFile(p,'a') as z:
            item=zipfile.ZipInfo('media/link');item.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(item,'../../outside')
        with zipfile.ZipFile(p) as z:
            with self.assertRaises(SystemExit):manager.validate_archive(z)

    def test_offline_backup_refuses_active_tasks_and_running_launcher(self):
        self.database()
        with closing(sqlite3.connect(manager.STATE/'db.sqlite3')) as db:
            db.execute("INSERT INTO operations_agentrun VALUES ('running')");db.commit()
        with self.assertRaises(SystemExit):manager.backup()
        with closing(sqlite3.connect(manager.STATE/'db.sqlite3')) as db:
            db.execute('DELETE FROM operations_agentrun');db.commit()
        manager.write_registry([])
        with self.assertRaises(SystemExit):manager.backup()


if __name__=='__main__':unittest.main()
