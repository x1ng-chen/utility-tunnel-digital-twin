"""Removable enclosure panels. Inspection hiding is explicit, not missing geometry."""
import bpy,math

def build_enclosure(mat):
    names=[]
    def sector(name,outer,inner,a,b,z0,z1):
        N=12;vs=[];faces=[]
        for z in [z0,z1]:
            for rx,ry in [outer,inner]:
                vs.extend([(rx*math.cos(a+(b-a)*i/N),ry*math.sin(a+(b-a)*i/N),z) for i in range(N+1)])
        K=N+1
        for i in range(N):
            j=i+1
            faces.extend([(i,j,2*K+j,2*K+i),(K+i,3*K+i,3*K+j,K+j),(i,K+i,K+j,j),(2*K+i,2*K+j,3*K+j,3*K+i)])
        faces.extend([(0,2*K,3*K,K),(N,K+N,3*K+N,2*K+N)])
        me=bpy.data.meshes.new(name);me.from_pydata(vs,[],faces);me.update()
        o=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(o);me.materials.append(mat)
        o['assembly']='可拆围护';o['dimension_status']='展示尺寸/非施工设计';names.append(name)
        return o
    for i in range(24):
        a=2*math.pi*i/24;b=2*math.pi*(i+1)/24
        # 0.4 mm assembly seams between manufactured panel envelopes.
        a+=.0004;b-=.0004
        sector(f'围护-外墙-{i:02}',(.896,.596),(.892,.592),a,b,.03,.404)
        sector(f'围护-内墙-{i:02}',(.430,.180),(.426,.176),a,b,.03,.404)
        sector(f'围护-屋面-{i:02}',(.896,.596),(.426,.176),a,b,.404,.410)
    return names

def set_inspection_view(enabled):
    for o in bpy.data.objects:
        if o.name.startswith('屋面通风附件-'):
            o.hide_render=enabled;o.hide_set(enabled)
        if o.name.startswith('围护-'):
            i=int(o.name.rsplit('-',1)[1])
            hidden=enabled and ('屋面' in o.name or '内墙' in o.name or i>=12)
            o.hide_render=hidden
            o.hide_set(hidden)
