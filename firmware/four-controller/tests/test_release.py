import copy,hashlib,importlib.util,json,re,struct,tempfile,unittest
from pathlib import Path
FW=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,FW/'tools'/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
build=load('build_release');flash=load('flash_plan')

class ReleaseTests(unittest.TestCase):
    def test_default_profile_has_four_boards_and_unverified_scaling(self):
        profile=build.profile_read(FW/'release-profile.json')
        self.assertEqual(set(profile['boards']),{'1','2','3','4'})
        self.assertFalse(profile['common']['FAN_TACH_VERIFIED']);self.assertFalse(profile['common']['INA_CALIBRATION_VERIFIED'])
    def test_r010_scale_matches_confirmed_shunt_without_claiming_calibration(self):
        profile=build.profile_read(FW/'release-profile.json')
        for board in ('2','4'):
            values={**profile['common'],**profile['boards'][board]}
            self.assertEqual(values['INA_SHUNT_MICROOHMS'],10000)
            self.assertEqual(values['INA_CURRENT_LSB_UA'],100)
            self.assertEqual(5120000000//(values['INA_CURRENT_LSB_UA']*values['INA_SHUNT_MICROOHMS']),5120)
            self.assertEqual(values['INA_CALIBRATION_VERIFIED'],0)
    def test_invalid_and_unsubstantiated_profiles_are_rejected(self):
        original=json.loads((FW/'release-profile.json').read_text(encoding='utf-8'))
        for key,value in [('FAN_PULSES_PER_REV',0),('FAN_PWM_INVERTED',2),('INA_CURRENT_LSB_UA',0),('FAN_TACH_VERIFIED',1)]:
            data=copy.deepcopy(original);data['common'][key]=value
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'profile.json';p.write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaises(ValueError):build.profile_read(p)
    def test_stm32_vector_and_board_tag_are_both_required(self):
        data=struct.pack('<II',0x2000c000,0x08000009)+b'UT-IMAGE:STM32:CTRL-01:test:abc\0'
        build.check_stm32_image(data,1,'test','abc')
        for args in [(data,2,'test','abc'),(bytes(8)+data[8:],1,'test','abc'),(data,1,'test','wrong')]:
            with self.assertRaises(ValueError):build.check_stm32_image(*args)
    def test_ui_literals_have_actual_chinese_glyphs(self):
        glyphs={int(s,16) for s in re.findall(r'0x([0-9A-F]{4}),', (FW/'Core/Inc/ui_zh_font.h').read_text(encoding='utf-8'))}
        for filename in ('menu.c','screen.c'):
            text=(FW/'Core/Src'/filename).read_text(encoding='utf-8')
            literals=''.join(re.findall(r'"(?:[^"\\]|\\.)*"',text))
            self.assertFalse({ord(c) for c in literals if '\u4e00'<=c<='\u9fff'}-glyphs)
    def test_private_network_header_is_not_part_of_source_snapshot(self):
        self.assertFalse(any(p.name=='secrets.h' or '.pio' in p.parts for p in build.sources()))
    def packet(self,folder):
        m={'version':'test','buildId':'abc','targets':{},'files':{}}
        def add(name,data):
            p=folder/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_bytes(data);m['files'][name]={'sha256':hashlib.sha256(data).hexdigest()}
        for n in range(1,5):
            code=f'CTRL-0{n}';name=code+'/firmware.bin'
            add(name,struct.pack('<II',0x2000c000,0x08000009)+f'UT-IMAGE:STM32:{code}:test:abc'.encode())
            m['targets'][code]={'address':'0x08000000','image':name}
        images=[]
        for name,address in [('bootloader.bin','0x0'),('partitions.bin','0x8000'),('boot_app0.bin','0xe000'),('firmware.bin','0x10000')]:
            name='GW-01/'+name;add(name,b'UT-IMAGE:ESP32-S3:GW-01:test:abc');images.append({'file':name,'address':address})
        m['targets']['GW-01']={'images':images};return m
    def test_flash_plan_checks_manifest_mapping_and_nvs_layout(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);m=self.packet(p)
            def save(): (p/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
            save();flash.validate(p)
            m['targets']['CTRL-01']['image']='CTRL-04/firmware.bin';save()
            with self.assertRaises(ValueError):flash.validate(p)
            m['targets']['CTRL-01']['image']='CTRL-01/firmware.bin';m['targets']['GW-01']['images'][0]['address']='0x9000';save()
            with self.assertRaises(ValueError):flash.validate(p)
    def test_incomplete_and_corrupted_packages_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);m=self.packet(p);(p/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
            (p/'INCOMPLETE').write_text('pending')
            with self.assertRaises(ValueError):flash.validate(p)
            (p/'INCOMPLETE').unlink();(p/'CTRL-01/firmware.bin').write_bytes(b'bad')
            with self.assertRaises(ValueError):flash.validate(p)

if __name__=='__main__':unittest.main()
