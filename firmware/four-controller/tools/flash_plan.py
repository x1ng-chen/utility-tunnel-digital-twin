"""Verify a release and print target-specific flash commands. Does not execute them."""
import argparse,hashlib,json,struct
from pathlib import Path

def validate(folder,allow_incomplete=False):
    if not allow_incomplete and (folder/'INCOMPLETE').exists():raise ValueError('Incomplete release cannot be flashed.')
    m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if set(m['targets'])!={'CTRL-01','CTRL-02','CTRL-03','CTRL-04','GW-01'}:raise ValueError('Five business targets are required.')
    for name,item in m['files'].items():
        p=(folder/name).resolve()
        if not p.is_relative_to(folder.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('File integrity check failed: '+name)
    for board in range(1,5):
        code=f'CTRL-0{board}';t=m['targets'][code]
        if t['address']!='0x08000000' or t['image'] not in m['files']:raise ValueError('Invalid STM32 flash target.')
        data=(folder/t['image']).read_bytes()
        if not 8<=len(data)<=256*1024:raise ValueError('Invalid STM32 size.')
        sp,pc=struct.unpack('<II',data[:8])
        if not 0x20000000<sp<=0x2000c000 or sp%8 or not pc&1 or not 0x08000000<=(pc&~1)<0x08000000+len(data):raise ValueError('Invalid STM32 vector table.')
        if f'UT-IMAGE:STM32:{code}:{m["version"]}:{m["buildId"]}'.encode() not in data:raise ValueError('Board/firmware identity mismatch.')
    expected=[{'file':'GW-01/'+name,'address':address} for name,address in
        [('bootloader.bin','0x0'),('partitions.bin','0x8000'),('boot_app0.bin','0xe000'),('firmware.bin','0x10000')]]
    if m['targets']['GW-01']['images']!=expected or any(i['file'] not in m['files'] for i in expected):raise ValueError('Unexpected S3 layout; NVS preservation cannot be assumed.')
    if f'UT-IMAGE:ESP32-S3:GW-01:{m["version"]}:{m["buildId"]}'.encode() not in (folder/'GW-01/firmware.bin').read_bytes():raise ValueError('Gateway identity mismatch.')
    return m

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--target',choices=['CTRL-01','CTRL-02','CTRL-03','CTRL-04','GW-01'],required=True)
    p.add_argument('--port',help='Actual USB UART port; never auto-select the first port.')
    p.add_argument('--app-only',action='store_true',help='GW only: existing bootloader/partition layout must already match.')
    args=p.parse_args();folder=args.release.resolve();m=validate(folder);t=m['targets'][args.target]
    if args.target=='GW-01':
        port=args.port or 'COMx'
        commands=[['python','-m','esptool','--chip','esp32s3','--port',port,'read_flash','0x0','0x1000000','PRIVATE-original-16MB.bin']]
        command=['python','-m','esptool','--chip','esp32s3','--port',port,'write_flash','--flash_mode','keep','--flash_freq','keep','--flash_size','keep']
        for image in t['images']:
            if not args.app_only or image['file'].endswith('/firmware.bin'):command += [image['address'],str(folder/image['file'])]
        commands.append(command)
    else:
        commands=[['STM32_Programmer_CLI','-c','port=SWD','--upload','0x08000000','0x40000','PRIVATE-original-'+args.target+'.bin'],
            ['STM32_Programmer_CLI','-c','port=SWD','-w',str(folder/t['image']),'0x08000000','-v','-rst']]
    print(json.dumps({'mode':'PRINT_ONLY_NO_HARDWARE_ACCESS','target':args.target,'version':m['version'],'buildId':m['buildId'],
        'requires':'Verify physical board identity, back up original flash and check the wiring before executing.',
        'commands':commands},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
