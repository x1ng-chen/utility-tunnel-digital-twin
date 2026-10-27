"""Build and package five business images. Never opens a serial/SWD port."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,re,shutil,struct,subprocess,sys,zipfile
from datetime import datetime,timezone
from pathlib import Path

FW=Path(__file__).resolve().parents[1]
ROOT=FW.parents[1]
PARAMETERS={'UT_WATCHDOG_ENABLED','FAN_PWM_INVERTED','RELAY_ACTIVE_HIGH','FAN_PULSES_PER_REV',
    'FAN_TACH_VERIFIED','INA_SHUNT_MICROOHMS','INA_CURRENT_LSB_UA','INA_CALIBRATION_VERIFIED'}
BOOLEANS={'UT_WATCHDOG_ENABLED','FAN_PWM_INVERTED','RELAY_ACTIVE_HIGH','FAN_TACH_VERIFIED','INA_CALIBRATION_VERIFIED'}

def sha(data):return hashlib.sha256(data).hexdigest()

def profile_read(path):
    p=json.loads(path.read_text(encoding='utf-8'))
    if set(p)-{'schemaVersion','layoutVersion','common','boards','verificationReferences','notes'}:raise ValueError('Unknown profile fields; keep private network settings outside the profile.')
    if p.get('schemaVersion')!=1 or p.get('layoutVersion')!='four-controller-20261026.1':raise ValueError('Unknown hardware profile/layout.')
    if set(p.get('common',{}))!=PARAMETERS or set(p.get('boards',{}))!={'1','2','3','4'}:raise ValueError('Profile must declare all parameters and four boards.')
    for board in range(1,5):
        overrides=p['boards'][str(board)]
        if not isinstance(overrides,dict) or set(overrides)-PARAMETERS:raise ValueError('Unknown board parameter.')
        c={**p['common'],**overrides}
        if any(type(v) is not int or v<0 for v in c.values()):raise ValueError('Profile parameters must be non-negative integers.')
        if any(c[k] not in (0,1) for k in BOOLEANS):raise ValueError('Boolean parameter outside 0/1.')
        if not 1<=c['FAN_PULSES_PER_REV']<=32 or not 1<=c['INA_CURRENT_LSB_UA']<=1000 or not c['INA_SHUNT_MICROOHMS']:raise ValueError('Invalid PPR/INA scaling.')
        calibration=5120000000//(c['INA_CURRENT_LSB_UA']*c['INA_SHUNT_MICROOHMS'])
        if not 1<=calibration<=65535:raise ValueError('INA calibration outside register range.')
        if board in (2,4):
            for key in ('FAN_TACH_VERIFIED','INA_CALIBRATION_VERIFIED'):
                reference=p.get('verificationReferences',{}).get(str(board),{}).get(key)
                if c[key] and (not isinstance(reference,str) or not reference.strip()):
                    raise ValueError('Verified feedback requires a recorded board-specific bench reference.')
    return p

def sources():
    allowed={'.c','.cpp','.h','.s','.ld','.py','.json','.ini','.md','.txt'}
    for base in (FW,ROOT/'firmware/stm32f103rct6'):
        for path in sorted(base.rglob('*')):
            if not path.is_file() or any(x in {'.pio','build','__pycache__','.git','.vscode'} for x in path.parts):continue
            if path.name in {'secrets.h','CMakeCache.txt'} or path.name.startswith('.'):continue
            if path.suffix.lower() in allowed or path.name=='CMakeLists.txt':yield path

def source_hash(paths,profile):
    h=hashlib.sha256()
    for p in sorted(paths):h.update(p.relative_to(ROOT).as_posix().encode()+b'\0'+p.read_bytes().replace(b'\r\n',b'\n')+b'\0')
    h.update(json.dumps(profile,sort_keys=True).encode());return h.hexdigest()

def run(command,log,env=None):
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run([str(x) for x in command],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(f'Command failed; inspect {log}')

def copy_verified(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
    content=destination.read_bytes()
    return {'file':destination.name,'bytes':len(content),'sha256':sha(content)}

def check_stm32_image(data,board,version,build):
    if not 8<=len(data)<=256*1024:raise ValueError('STM32 image size invalid.')
    sp,entry=struct.unpack('<II',data[:8])
    if not 0x20000000<sp<=0x2000c000 or sp%8 or not entry&1 or not 0x08000000<=(entry&~1)<0x08000000+len(data):
        raise ValueError('STM32 vector table does not target F103RC flash/RAM.')
    marker=f'UT-IMAGE:STM32:CTRL-0{board}:{version}:{build}'.encode()
    if marker not in data:raise ValueError('STM32 board/version identity mismatch.')

def verify_package(folder,allow_incomplete=False):
    if not allow_incomplete and (folder/'INCOMPLETE').exists():raise ValueError('Build is incomplete.')
    m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    for name,value in m['files'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha(path.read_bytes())!=value['sha256']:raise ValueError('Package file hash mismatch: '+name)
    spec=importlib.util.spec_from_file_location('release_flash_validation',FW/'tools/flash_plan.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.validate(folder,allow_incomplete=allow_incomplete)
    return m

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='New directory; never overwrite a previous release.')
    parser.add_argument('--profile',type=Path,default=FW/'release-profile.json')
    parser.add_argument('--test-mode',choices=['native','arm-emulated'],default='arm-emulated' if os.name=='nt' else 'native')
    parser.add_argument('--verify',type=Path,help='Verify an existing package without building.')
    options=parser.parse_args()
    if options.verify:verify_package(options.verify);print('PACKAGE_HASHES_PASS');return
    if options.output is None:parser.error('--output is required when building')
    profile=profile_read(options.profile);paths=list(sources());fingerprint=source_hash(paths,profile);build=fingerprint[:16]
    version=re.search(r'UT_FIRMWARE_VERSION "([^"]+)"',(FW/'common/firmware_version.h').read_text()).group(1)
    out=options.output.resolve()
    if out.exists() or out.is_relative_to(FW.resolve()):raise ValueError('Choose a new output directory outside firmware source.')
    out.mkdir(parents=True);logs=out/'logs';logs.mkdir();work=ROOT/'build'/'firmware-release'/build;work.mkdir(parents=True,exist_ok=True)
    manifest={'schemaVersion':1,'version':version,'buildId':build,'sourceSha256':fingerprint,
        'createdAtUtc':datetime.now(timezone.utc).isoformat(),'status':'SOFTWARE_RELEASE_HARDWARE_COMMISSIONING_PENDING',
        'hardwareVerified':False,'credentialsEmbedded':False,'profile':profile,'physicalSensors':31,'allocation':[11,7,6,7],
        'targets':{},'files':{}}
    manifest['tools']={'python':sys.version.split()[0],'platform':'espressif32@6.13.0','ArduinoJson':'6.21.5','PubSubClient':'2.8'}
    for name,command in [('armGcc',['arm-none-eabi-gcc','--version']),('cmake',['cmake','--version']),('platformio',[sys.executable,'-m','platformio','--version'])]:
        manifest['tools'][name]=subprocess.check_output(command,text=True).splitlines()[0]
    (out/'INCOMPLETE').write_text('Build in progress. Do not flash an incomplete package.\n',encoding='utf-8')
    run([sys.executable,FW/'tests/run_tests.py','--'+options.test_mode,'--output',work/'logic-tests/results.json'],logs/'logic-tests.log')
    report=json.loads((work/'logic-tests/results.json').read_text());manifest['logicTests']={'mode':report['mode'],
        'checks':sum(x['checks'] for x in report['suites']),'failures':sum(x['failures'] for x in report['suites'])}
    shutil.copyfile(work/'logic-tests/results.json',out/'logic-tests.json')
    for board in range(1,5):
        values={**profile['common'],**profile['boards'][str(board)]};folder=out/f'CTRL-0{board}';folder.mkdir()
        directory=work/f'ctrl0{board}'
        run(['cmake','-S',FW,'-B',directory,'-G','Ninja',f'-DBOARD_ID={board}',f'-DUT_BUILD_ID={build}',
            '-DUT_RELEASE_BUILD=1',*[f'-D{k}={v}' for k,v in values.items()]],logs/f'CTRL-0{board}-configure.log')
        run(['cmake','--build',directory],logs/f'CTRL-0{board}-build.log')
        name=f'four_ctrl0{board}'
        check_stm32_image((directory/(name+'.bin')).read_bytes(),board,version,build)
        for suffix in ('.bin','.elf','.map'):copy_verified(directory/(name+suffix),folder/(name+suffix))
        manifest['targets'][f'CTRL-0{board}']={'chip':'STM32F103RCT6','address':'0x08000000','image':f'CTRL-0{board}/{name}.bin','parameters':values,'build':'PASS'}
        print(f'CTRL-0{board} BUILD_AND_IDENTITY_PASS',flush=True)
    env={**os.environ,'UT_FIRMWARE_BUILD_ID':build,'PYTHONIOENCODING':'utf-8'}
    run([sys.executable,'-m','platformio','run','--project-dir',FW/'gateway','-e','s3_four_gateway_release'],logs/'GW-01-build.log',env)
    pio=FW/'gateway/.pio/build/s3_four_gateway_release';gw=out/'GW-01';gw.mkdir()
    app=(pio/'firmware.bin').read_bytes()
    if f'UT-IMAGE:ESP32-S3:GW-01:{version}:{build}'.encode() not in app:raise ValueError('Gateway identity mismatch.')
    framework=Path(os.environ.get('PLATFORMIO_CORE_DIR',Path.home()/'.platformio'))/'packages/framework-arduinoespressif32'
    images=[('bootloader.bin',pio/'bootloader.bin','0x0'),('partitions.bin',pio/'partitions.bin','0x8000'),
        ('boot_app0.bin',framework/'tools/partitions/boot_app0.bin','0xe000'),('firmware.bin',pio/'firmware.bin','0x10000')]
    for name,path,_ in images:copy_verified(path,gw/name)
    copy_verified(pio/'firmware.elf',gw/'firmware.elf')
    manifest['targets']['GW-01']={'chip':'ESP32-S3 N16R8','flashSize':'16MB','build':'PASS','runtimeProvisioning':True,
        'images':[{'file':'GW-01/'+name,'address':address} for name,_,address in images],
        'nvsPreservation':'Scatter-write these segments; do not merge a filled image across NVS.'}
    shutil.copyfile(options.profile,out/'release-profile.json')
    shutil.copyfile(FW/'tools/provision_gateway.py',out/'provision_gateway.py')
    shutil.copyfile(FW/'tools/flash_plan.py',out/'flash_plan.py')
    shutil.copyfile(FW/'RELEASE.md',out/'README.md')
    with zipfile.ZipFile(out/'source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in paths:archive.writestr(path.relative_to(ROOT).as_posix(),path.read_bytes())
    for path in sorted(out.rglob('*')):
        if path.is_file() and path.name!='INCOMPLETE':manifest['files'][path.relative_to(out).as_posix()]={'bytes':path.stat().st_size,'sha256':sha(path.read_bytes())}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    verify_package(out,allow_incomplete=True);(out/'INCOMPLETE').unlink()
    print(json.dumps({'output':str(out),'targets':5,'buildId':build,'checks':manifest['logicTests'],'hardwareVerified':False}))

if __name__=='__main__':main()
