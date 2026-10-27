from django.core.exceptions import ValidationError
from django.db import IntegrityError,OperationalError
from rest_framework.views import APIView
from rest_framework.response import Response
from .permissions import AuthenticatedRead
from . import agent_experience as experience


class ExperienceList(APIView):
    permission_classes=[AuthenticatedRead]
    def get(self,request):
        if experience.role(request.user)=='ingest': return Response(status=403)
        rows=experience.visible(request.user).order_by('-updated_at','id')
        state=request.query_params.get('status')
        if state:
            if state not in {'candidate','approved','rejected','retired'}: return Response(status=400)
            rows=rows.filter(status=state)
        # Cursor-free small management list; truncation is explicit, never a completeness claim.
        values=list(rows[:101])
        return Response({'items':[experience.serialize(r,request.user) for r in values[:100]],'truncated':len(values)>100})


class ExperienceDetail(APIView):
    permission_classes=[AuthenticatedRead]
    def get(self,request,pk):
        if experience.role(request.user)=='ingest': return Response(status=403)
        item=experience.visible(request.user).filter(pk=pk).first()
        return Response(experience.serialize(item,request.user)) if item else Response(status=404)
    def post(self,request,pk):
        if experience.role(request.user)=='ingest': return Response(status=403)
        try: return Response(experience.serialize(experience.transition(request.user,pk,request.data),request.user))
        except LookupError as exc: return Response({'message':str(exc)},status=404)
        except PermissionError as exc: return Response({'message':str(exc)},status=403)
        except RuntimeError as exc: return Response({'message':str(exc)},status=409)
        except IntegrityError: return Response({'message':'已有相同的已批准经验或并发版本变化，请刷新。'},status=409)
        except OperationalError as exc:
            if 'locked' not in str(exc).lower() and 'deadlock' not in str(exc).lower(): raise
            return Response({'message':'并发审核发生冲突，请刷新后重试。'},status=409)
        except (ValueError,ValidationError) as exc: return Response({'message':str(exc)},status=400)
